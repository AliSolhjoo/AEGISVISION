"""Focused regression tests for the SORT v1 association engine."""
import unittest

from apps.organizations.cameras.sort_tracker import associate_detections_sort


class SortTrackerV1Tests(unittest.TestCase):
    def make_frame(self, number, timestamp, detections=None):
        normalized = []
        for index, item in enumerate(detections or [], start=1):
            normalized.append(
                {
                    "detection_id": number * 100 + index,
                    "source_frame_id": number,
                    "class_id": item.get("class_id", 1),
                    "label": item.get("label", "person"),
                    "confidence": item.get("confidence", 0.95),
                    "bounding_box": item["box"],
                }
            )
        return {
            "source_frame_id": number,
            "frame_number": number,
            "timestamp_seconds": timestamp,
            "detections": normalized,
        }

    def test_fast_moving_person_keeps_one_track(self):
        boxes = [
            [519, 324, 581, 429],
            [541, 257, 598, 355],
            [587, 204, 642, 297],
            [643, 169, 697, 252],
            [697, 128, 748, 209],
        ]
        records = [
            self.make_frame(
                index + 1,
                float(index + 1),
                [{"box": box, "label": "person", "class_id": 1}],
            )
            for index, box in enumerate(boxes)
        ]

        result = associate_detections_sort(records, iou_threshold=0.30, max_gap_frames=2)

        self.assertEqual(result["tracks_count"], 1)
        self.assertEqual(result["observations_count"], 5)
        self.assertEqual(result["tracks"][0]["observations_count"], 5)

    def test_moving_car_keeps_one_track(self):
        boxes = [
            [91, 267, 288, 426],
            [122, 182, 270, 394],
            [64, 126, 236, 293],
            [0, 103, 160, 241],
            [0, 110, 65, 221],
        ]
        records = [
            self.make_frame(
                index + 1,
                float(index + 1),
                [{"box": box, "label": "car", "class_id": 3}],
            )
            for index, box in enumerate(boxes)
        ]

        result = associate_detections_sort(records, iou_threshold=0.30, max_gap_frames=2)

        self.assertEqual(result["tracks_count"], 1)
        self.assertEqual(result["observations_count"], 5)
        self.assertEqual(result["tracks"][0]["label"], "car")

    def test_class_mismatch_never_matches(self):
        records = [
            self.make_frame(1, 1.0, [{"box": [10, 10, 60, 80], "label": "person", "class_id": 1}]),
            self.make_frame(2, 2.0, [{"box": [10, 10, 60, 80], "label": "car", "class_id": 3}]),
        ]

        result = associate_detections_sort(records)

        self.assertEqual(result["tracks_count"], 2)
        self.assertEqual(
            [track["observations_count"] for track in result["tracks"]],
            [1, 1],
        )

    def test_track_survives_configured_two_frame_gap(self):
        records = [
            self.make_frame(1, 1.0, [{"box": [100, 100, 160, 180]}]),
            self.make_frame(2, 2.0),
            self.make_frame(3, 3.0),
            self.make_frame(4, 4.0, [{"box": [100, 100, 160, 180]}]),
        ]

        result = associate_detections_sort(records, max_gap_frames=2)

        self.assertEqual(result["tracks_count"], 1)
        self.assertEqual(result["tracks"][0]["observations_count"], 2)

    def test_track_is_recreated_after_gap_limit_is_exceeded(self):
        records = [
            self.make_frame(1, 1.0, [{"box": [100, 100, 160, 180]}]),
            self.make_frame(2, 2.0),
            self.make_frame(3, 3.0),
            self.make_frame(4, 4.0),
            self.make_frame(5, 5.0, [{"box": [100, 100, 160, 180]}]),
        ]

        result = associate_detections_sort(records, max_gap_frames=2)

        self.assertEqual(result["tracks_count"], 2)
        self.assertEqual(result["observations_count"], 2)

    def test_two_same_class_objects_get_distinct_tracks(self):
        records = [
            self.make_frame(
                1,
                1.0,
                [
                    {"box": [10, 10, 60, 80]},
                    {"box": [180, 10, 230, 80]},
                ],
            ),
            self.make_frame(
                2,
                2.0,
                [
                    {"box": [20, 10, 70, 80]},
                    {"box": [170, 10, 220, 80]},
                ],
            ),
        ]

        result = associate_detections_sort(records)

        self.assertEqual(result["tracks_count"], 2)
        self.assertEqual(result["observations_count"], 4)
        self.assertEqual(
            sorted(track["observations_count"] for track in result["tracks"]),
            [2, 2],
        )

    def test_invalid_boxes_are_ignored(self):
        records = [
            self.make_frame(
                1,
                1.0,
                [
                    {"box": [10, 10, 60, 80]},
                    {"box": [10, 10, 10, 80]},
                ],
            )
        ]

        result = associate_detections_sort(records)

        self.assertEqual(result["tracks_count"], 1)
        self.assertEqual(result["observations_count"], 1)
