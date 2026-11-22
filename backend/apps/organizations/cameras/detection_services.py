from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .detection_models import DetectionFrame, DetectionRun, ObjectDetection
from .video_models import VideoAsset, VideoFrame, VideoProcessingJob


class DetectionProcessingError(Exception):
    """Raised when an object-detection run cannot be completed safely."""


MODEL_NAME = "fasterrcnn_mobilenet_v3_large_320_fpn"


def resolve_device(requested_device: str) -> str:
    try:
        import torch
    except ImportError as exc:
        raise DetectionProcessingError(
            "PyTorch is not installed. Install torch and torchvision before running detection."
        ) from exc

    if requested_device == "cpu":
        return "cpu"
    if requested_device == "cuda":
        if not torch.cuda.is_available():
            raise DetectionProcessingError(
                "CUDA was requested but is not available in this PyTorch installation."
            )
        return "cuda"
    if requested_device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    raise DetectionProcessingError("Unsupported inference device.")


@lru_cache(maxsize=2)
def load_detection_model(device: str):
    """Load the torchvision COCO-pretrained detector once per process/device."""
    try:
        import torch
        from torchvision.models.detection import (
            FasterRCNN_MobileNet_V3_Large_320_FPN_Weights,
            fasterrcnn_mobilenet_v3_large_320_fpn,
        )
    except Exception as exc:
        raise DetectionProcessingError(
            "Could not import the PyTorch/torchvision detection stack. Verify compatible versions."
        ) from exc

    try:
        weights = FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.DEFAULT
        model = fasterrcnn_mobilenet_v3_large_320_fpn(weights=weights)
        model.eval()
        model.to(torch.device(device))
    except Exception as exc:
        raise DetectionProcessingError(
            "Could not load the pretrained detection model. Check network access for the first model download and available memory."
        ) from exc

    categories = weights.meta["categories"]
    return model, categories


def select_frames(frames, max_frames: int):
    """Select up to max_frames evenly across an ordered frame collection."""
    frames = list(frames)
    if max_frames <= 0 or not frames:
        return []
    if len(frames) <= max_frames:
        return frames
    if max_frames == 1:
        return [frames[0]]

    indexes = [round(i * (len(frames) - 1) / (max_frames - 1)) for i in range(max_frames)]
    return [frames[index] for index in indexes]


def infer_frame(image_path: str, confidence_threshold: float, device: str):
    """Return detections and an annotated JPEG for one extracted frame."""
    try:
        import cv2
        import numpy as np
        import torch
    except ImportError as exc:
        raise DetectionProcessingError(
            "OpenCV, NumPy and PyTorch are required for object detection."
        ) from exc

    image = cv2.imread(str(image_path))
    if image is None:
        raise DetectionProcessingError("An extracted frame could not be opened.")

    height, width = image.shape[:2]
    model, categories = load_detection_model(device)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1).float() / 255.0

    try:
        with torch.inference_mode():
            prediction = model([tensor.to(device)])[0]
    except Exception as exc:
        raise DetectionProcessingError(
            "The detection model failed while processing a frame."
        ) from exc

    boxes = prediction["boxes"].detach().cpu().tolist()
    labels = prediction["labels"].detach().cpu().tolist()
    scores = prediction["scores"].detach().cpu().tolist()

    results = []
    annotated = image.copy()
    for box, class_id, score in zip(boxes, labels, scores):
        score = float(score)
        if score < confidence_threshold:
            continue
        class_id = int(class_id)
        label = categories[class_id] if 0 <= class_id < len(categories) else f"class_{class_id}"
        x1, y1, x2, y2 = [int(round(value)) for value in box]
        x1 = max(0, min(width - 1, x1))
        x2 = max(0, min(width - 1, x2))
        y1 = max(0, min(height - 1, y1))
        y2 = max(0, min(height - 1, y2))
        if x2 <= x1 or y2 <= y1:
            continue

        results.append({
            "class_id": class_id,
            "label": str(label)[:80],
            "confidence": round(score, 5),
            "bounding_box": [x1, y1, x2, y2],
        })

        display = f"{label} {score:.2f}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (40, 220, 120), 2)
        text_y = max(18, y1 - 7)
        cv2.putText(
            annotated,
            display,
            (x1, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            (40, 220, 120),
            1,
            cv2.LINE_AA,
        )

    encoded_ok, encoded = cv2.imencode(
        ".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 88]
    )
    if not encoded_ok:
        raise DetectionProcessingError("Could not encode the annotated frame.")

    return results, encoded.tobytes()


def delete_detection_outputs(run):
    for detection_frame in run.frames.all():
        if detection_frame.annotated_image:
            detection_frame.annotated_image.delete(save=False)
        detection_frame.delete()


def mark_detection_failed(run, message: str):
    delete_detection_outputs(run)
    now = timezone.now()
    DetectionRun.objects.filter(pk=run.pk).update(
        status=DetectionRun.Status.FAILED,
        error_message=str(message)[:1000],
        finished_at=now,
        updated_at=now,
        frames_processed=0,
        detections_count=0,
    )
    run.refresh_from_db()
    return run


def process_detection_run(run_id: int):
    run = DetectionRun.objects.select_related("asset", "asset__organization").get(pk=run_id)
    if run.status not in {DetectionRun.Status.QUEUED, DetectionRun.Status.FAILED}:
        return run

    job = VideoProcessingJob.objects.filter(
        asset=run.asset,
        status=VideoProcessingJob.Status.COMPLETED,
    ).first()
    if job is None:
        return mark_detection_failed(run, "The source video has not completed frame extraction.")

    frames = list(
        VideoFrame.objects.filter(job=job).order_by("frame_number", "id")
    )
    selected_frames = select_frames(frames, run.max_frames)
    if not selected_frames:
        return mark_detection_failed(run, "No extracted frames are available for detection.")

    now = timezone.now()
    DetectionRun.objects.filter(pk=run.pk).update(
        status=DetectionRun.Status.PROCESSING,
        started_at=run.started_at or now,
        finished_at=None,
        error_message="",
        frames_processed=0,
        detections_count=0,
        updated_at=now,
    )
    run.refresh_from_db()
    delete_detection_outputs(run)

    total_detections = 0
    frames_processed = 0
    try:
        actual_device = resolve_device(run.requested_device)
        DetectionRun.objects.filter(pk=run.pk).update(actual_device=actual_device)

        for source_frame in selected_frames:
            try:
                source_path = Path(source_frame.image.path)
            except (AttributeError, NotImplementedError, ValueError) as exc:
                raise DetectionProcessingError(
                    "The configured frame storage does not expose a local file path."
                ) from exc
            if not source_path.is_file():
                raise DetectionProcessingError("An extracted frame file is missing.")

            detections, annotated_bytes = infer_frame(
                str(source_path), run.confidence_threshold, actual_device
            )

            detection_frame = DetectionFrame(
                run=run,
                source_frame=source_frame,
                detections_count=len(detections),
            )
            detection_frame.annotated_image.save(
                f"annotated_{source_frame.frame_number:05d}.jpg",
                ContentFile(annotated_bytes),
                save=True,
            )

            ObjectDetection.objects.bulk_create([
                ObjectDetection(
                    detection_frame=detection_frame,
                    class_id=item["class_id"],
                    label=item["label"],
                    confidence=item["confidence"],
                    bounding_box=item["bounding_box"],
                )
                for item in detections
            ])

            frames_processed += 1
            total_detections += len(detections)
            DetectionRun.objects.filter(pk=run.pk).update(
                frames_processed=frames_processed,
                detections_count=total_detections,
                updated_at=timezone.now(),
            )

        finished = timezone.now()
        DetectionRun.objects.filter(pk=run.pk).update(
            status=DetectionRun.Status.COMPLETED,
            frames_processed=frames_processed,
            detections_count=total_detections,
            error_message="",
            finished_at=finished,
            updated_at=finished,
        )
        run.refresh_from_db()
        return run

    except Exception as exc:
        safe_message = str(exc) if isinstance(exc, DetectionProcessingError) else (
            "Object detection failed due to an unexpected model, decoder or storage error."
        )
        return mark_detection_failed(run, safe_message)


def infer_live_image(image, confidence_threshold: float, device: str):
    """Run the shared COCO detector directly on an OpenCV BGR frame.

    Unlike ``infer_frame`` this helper does not touch video/image storage, so it
    can be used by the long-running RTSP worker for every sampled live frame.
    Returns pixel-coordinate detections for the supplied frame dimensions.
    """
    try:
        import cv2
        import numpy as np
        import torch
    except ImportError as exc:
        raise DetectionProcessingError(
            "OpenCV, NumPy and PyTorch are required for live object detection."
        ) from exc

    if image is None or not hasattr(image, "shape") or len(image.shape) < 2:
        raise DetectionProcessingError("The live camera returned an invalid frame.")

    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        raise DetectionProcessingError("The live camera frame has invalid dimensions.")

    model, categories = load_detection_model(device)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1).float() / 255.0
    try:
        with torch.inference_mode():
            prediction = model([tensor.to(device)])[0]
    except Exception as exc:
        raise DetectionProcessingError(
            "The detection model failed while processing a live camera frame."
        ) from exc

    boxes = prediction["boxes"].detach().cpu().tolist()
    labels = prediction["labels"].detach().cpu().tolist()
    scores = prediction["scores"].detach().cpu().tolist()
    results = []
    for box, class_id, score in zip(boxes, labels, scores):
        score = float(score)
        if score < float(confidence_threshold):
            continue
        class_id = int(class_id)
        label = categories[class_id] if 0 <= class_id < len(categories) else f"class_{class_id}"
        x1, y1, x2, y2 = [int(round(value)) for value in box]
        x1 = max(0, min(width - 1, x1))
        x2 = max(0, min(width - 1, x2))
        y1 = max(0, min(height - 1, y1))
        y2 = max(0, min(height - 1, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        results.append({
            "class_id": class_id,
            "label": str(label)[:80],
            "confidence": round(score, 5),
            "bounding_box": [x1, y1, x2, y2],
        })
    return results
