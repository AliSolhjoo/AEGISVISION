"""Deterministic unit tests for live camera tracking and rule evaluation.

These tests do not need a physical RTSP camera, GPU, network access or a model
checkpoint. They exercise the stateful logic used by the live worker.
"""
from types import SimpleNamespace
import unittest

from apps.organizations.cameras.live_rule_engine import LiveRuleEvaluator
from apps.organizations.cameras.sort_tracker import LiveSORTTracker


class LiveCameraIntelligenceTests(unittest.TestCase):
    @staticmethod
    def make_detection(box, track_number=1, label="person", class_id=1, confidence=0.95):
        return {
            "track_number": track_number,
            "label": label,
            "class_id": class_id,
            "confidence": confidence,
            "bounding_box": box,
        }

    @staticmethod
    def make_rule(
        *,
        rule_id=1,
        rule_type="zone_intrusion",
        geometry=None,
        labels=None,
        confidence=0.5,
        dwell_seconds=10.0,
        direction="both",
        is_active=True,
    ):
        return SimpleNamespace(
            pk=rule_id,
            name=f"Test rule {rule_id}",
            rule_type=rule_type,
            geometry=geometry or {},
            labels=labels or ["person"],
            minimum_confidence=confidence,
            dwell_seconds=dwell_seconds,
            direction=direction,
            is_active=is_active,
        )

    def test_live_sort_keeps_fast_moving_person_id(self):
        boxes = [
            [519, 324, 581, 429],
            [541, 257, 598, 355],
            [587, 204, 642, 297],
            [643, 169, 697, 252],
            [697, 128, 748, 209],
        ]
        tracker = LiveSORTTracker(iou_threshold=0.30, max_gap_frames=8)
        observed_ids = []
        for frame_number, box in enumerate(boxes, start=1):
            result = tracker.update(
                [self.make_detection(box)],
                frame_number=frame_number,
                timestamp_seconds=float(frame_number),
            )
            self.assertEqual(len(result), 1)
            observed_ids.append(result[0]["track_number"])
        self.assertEqual(observed_ids, [1, 1, 1, 1, 1])

    def test_live_sort_does_not_match_different_classes(self):
        tracker = LiveSORTTracker()
        first = tracker.update(
            [self.make_detection([10, 10, 60, 80], label="person", class_id=1)],
            1,
            1.0,
        )
        second = tracker.update(
            [self.make_detection([10, 10, 60, 80], label="car", class_id=3)],
            2,
            2.0,
        )
        self.assertNotEqual(first[0]["track_number"], second[0]["track_number"])

    def test_zone_intrusion_emits_once_per_entry(self):
        rule = self.make_rule(
            geometry={"polygon": [[0.4, 0.4], [0.8, 0.4], [0.8, 0.9], [0.4, 0.9]]}
        )
        evaluator = LiveRuleEvaluator([rule])
        inside = self.make_detection([45, 45, 55, 80])
        outside = self.make_detection([10, 10, 20, 20])

        first = evaluator.evaluate([inside], 100, 100, 1.0, 1)
        second = evaluator.evaluate([inside], 100, 100, 2.0, 2)
        third = evaluator.evaluate([outside], 100, 100, 3.0, 3)
        fourth = evaluator.evaluate([inside], 100, 100, 4.0, 4)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(len(third), 0)
        self.assertEqual(len(fourth), 1)
        self.assertEqual(fourth[0]["event_type"], "zone_intrusion")

    def test_line_crossing_emits_on_side_change(self):
        rule = self.make_rule(
            rule_type="line_crossing",
            geometry={"line": [[0.5, 0.1], [0.5, 0.9]]},
        )
        evaluator = LiveRuleEvaluator([rule])
        left = self.make_detection([30, 30, 40, 80])
        right = self.make_detection([60, 30, 70, 80])

        self.assertEqual(evaluator.evaluate([left], 100, 100, 1.0, 1), [])
        events = evaluator.evaluate([right], 100, 100, 2.0, 2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "line_crossing")
        self.assertIn(events[0]["details"]["direction"], {
            "negative_to_positive", "positive_to_negative"
        })

    def test_loitering_emits_after_dwell_threshold_once(self):
        rule = self.make_rule(
            rule_type="loitering",
            geometry={"polygon": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.9], [0.2, 0.9]]},
            dwell_seconds=5.0,
        )
        evaluator = LiveRuleEvaluator([rule])
        inside = self.make_detection([45, 45, 55, 80])

        self.assertEqual(evaluator.evaluate([inside], 100, 100, 0.0, 1), [])
        self.assertEqual(evaluator.evaluate([inside], 100, 100, 2.0, 2), [])
        event = evaluator.evaluate([inside], 100, 100, 5.0, 3)
        repeated = evaluator.evaluate([inside], 100, 100, 7.0, 4)

        self.assertEqual(len(event), 1)
        self.assertEqual(event[0]["event_type"], "loitering")
        self.assertEqual(event[0]["details"]["dwell_seconds"], 5.0)
        self.assertEqual(repeated, [])

    def test_inactive_rule_and_low_confidence_are_ignored(self):
        inactive = self.make_rule(
            is_active=False,
            geometry={"polygon": [[0.4, 0.4], [0.8, 0.4], [0.8, 0.9], [0.4, 0.9]]},
        )
        low_confidence = self.make_rule(
            rule_id=2,
            confidence=0.8,
            geometry={"polygon": [[0.4, 0.4], [0.8, 0.4], [0.8, 0.9], [0.4, 0.9]]},
        )
        evaluator = LiveRuleEvaluator([inactive, low_confidence])
        detection = self.make_detection([45, 45, 55, 80], confidence=0.6)
        events = evaluator.evaluate([detection], 100, 100, 1.0, 1)
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
