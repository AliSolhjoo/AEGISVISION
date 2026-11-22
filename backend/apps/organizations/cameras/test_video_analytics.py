import unittest

from .video_analytics import (
    AnalyticsConfigError,
    analyze_tracking_data,
    point_in_polygon,
    validate_config,
)


def observation(frame, time, center_x, bottom_y=0.5, confidence=0.95, label_box_width=0.04):
    width = label_box_width * 100
    center_px = center_x * 100
    bottom_px = bottom_y * 100
    return {
        "frame_number": frame,
        "timestamp_seconds": time,
        "confidence": confidence,
        "bounding_box": [center_px - width / 2, bottom_px - 20, center_px + width / 2, bottom_px],
        "width": 100,
        "height": 100,
    }


class VideoAnalyticsTests(unittest.TestCase):
    def test_point_in_polygon_inside_outside_and_boundary(self):
        polygon = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
        self.assertTrue(point_in_polygon((0.5, 0.5), polygon))
        self.assertFalse(point_in_polygon((0.1, 0.5), polygon))
        self.assertTrue(point_in_polygon((0.2, 0.5), polygon))

    def test_zone_intrusion_emits_only_on_entry(self):
        config = {
            "max_observation_gap_seconds": 2,
            "rules": [{
                "id": "zone", "type": "zone_intrusion", "polygon": [
                    [0.4, 0.4], [0.6, 0.4], [0.6, 0.7], [0.4, 0.7]
                ],
                "labels": ["person"],
            }],
        }
        tracks = [{
            "track_number": 1, "label": "person", "observations": [
                observation(1, 0, 0.2), observation(2, 1, 0.5),
                observation(3, 2, 0.55), observation(4, 3, 0.9),
                observation(5, 4, 0.5),
            ],
        }]
        report = analyze_tracking_data(tracks, config)
        self.assertEqual(report["event_summary"]["total_events"], 2)
        self.assertEqual([item["event_type"] for item in report["events"]], ["zone_intrusion"] * 2)

    def test_gap_resets_zone_presence_state(self):
        config = {
            "max_observation_gap_seconds": 2,
            "rules": [{
                "id": "zone", "type": "zone_intrusion", "polygon": [
                    [0.4, 0.4], [0.6, 0.4], [0.6, 0.7], [0.4, 0.7]
                ],
            }],
        }
        tracks = [{
            "track_number": 1, "label": "person", "observations": [
                observation(1, 0, 0.5), observation(2, 1, 0.5), observation(5, 8, 0.5),
            ],
        }]
        report = analyze_tracking_data(tracks, config)
        self.assertEqual(report["event_summary"]["total_events"], 2)

    def test_line_crossing_emits_direction_and_interpolated_time(self):
        config = {
            "max_observation_gap_seconds": 2,
            "rules": [{
                "id": "gate", "type": "line_crossing",
                "line": [[0.5, 0.1], [0.5, 0.9]],
                "direction": "both",
            }],
        }
        tracks = [{
            "track_number": 7, "label": "car", "observations": [
                observation(1, 0, 0.4), observation(2, 2, 0.6),
            ],
        }]
        report = analyze_tracking_data(tracks, config)
        self.assertEqual(report["event_summary"]["total_events"], 1)
        self.assertAlmostEqual(report["events"][0]["timestamp_seconds"], 1.0, places=3)
        self.assertEqual(report["events"][0]["event_type"], "line_crossing")
        self.assertIn(report["events"][0]["direction"], {"negative_to_positive", "positive_to_negative"})

    def test_line_crossing_ignores_large_sampling_gap(self):
        config = {
            "max_observation_gap_seconds": 1,
            "rules": [{
                "id": "gate", "type": "line_crossing", "line": [[0.5, 0.1], [0.5, 0.9]],
            }],
        }
        tracks = [{
            "track_number": 1, "label": "person", "observations": [
                observation(1, 0, 0.4), observation(10, 5, 0.6),
            ],
        }]
        self.assertEqual(analyze_tracking_data(tracks, config)["events"], [])

    def test_loitering_emits_once_after_dwell_threshold(self):
        config = {
            "max_observation_gap_seconds": 2,
            "rules": [{
                "id": "stay", "type": "loitering", "dwell_seconds": 5,
                "polygon": [[0.3, 0.3], [0.7, 0.3], [0.7, 0.8], [0.3, 0.8]],
            }],
        }
        tracks = [{
            "track_number": 2, "label": "person", "observations": [
                observation(frame, frame, 0.5) for frame in range(7)
            ],
        }]
        report = analyze_tracking_data(tracks, config)
        self.assertEqual(report["event_summary"]["total_events"], 1)
        self.assertEqual(report["events"][0]["event_type"], "loitering")
        self.assertEqual(report["events"][0]["timestamp_seconds"], 5.0)

    def test_loitering_resets_after_long_gap(self):
        config = {
            "max_observation_gap_seconds": 2,
            "rules": [{
                "id": "stay", "type": "loitering", "dwell_seconds": 5,
                "polygon": [[0.3, 0.3], [0.7, 0.3], [0.7, 0.8], [0.3, 0.8]],
            }],
        }
        tracks = [{
            "track_number": 2, "label": "person", "observations": [
                observation(1, 0, 0.5), observation(2, 1, 0.5), observation(3, 10, 0.5),
                observation(4, 11, 0.5), observation(5, 12, 0.5), observation(6, 13, 0.5),
                observation(7, 14, 0.5), observation(8, 15, 0.5),
            ],
        }]
        report = analyze_tracking_data(tracks, config)
        self.assertEqual(report["event_summary"]["total_events"], 1)
        self.assertEqual(report["events"][0]["timestamp_seconds"], 15.0)

    def test_label_and_confidence_filters(self):
        config = {
            "rules": [{
                "id": "people", "type": "zone_intrusion", "labels": ["person"],
                "minimum_confidence": 0.8,
                "polygon": [[0.3, 0.3], [0.7, 0.3], [0.7, 0.8], [0.3, 0.8]],
            }],
        }
        tracks = [
            {"track_number": 1, "label": "car", "observations": [observation(1, 0, 0.5)]},
            {"track_number": 2, "label": "person", "observations": [observation(1, 0, 0.5, confidence=0.6)]},
        ]
        self.assertEqual(analyze_tracking_data(tracks, config)["events"], [])

    def test_metrics_include_tracks_by_label_and_observed_span(self):
        tracks = [{
            "track_number": 5, "label": "car", "observations": [
                observation(1, 2, 0.3), observation(2, 4, 0.4),
            ],
        }]
        report = analyze_tracking_data(tracks, {"rules": []})
        self.assertEqual(report["summary"]["unique_tracks"], 1)
        self.assertEqual(report["summary"]["total_observations"], 2)
        self.assertEqual(report["summary"]["tracks_by_label"], {"car": 1})
        self.assertEqual(report["summary"]["track_details"][0]["observed_span_seconds"], 2.0)

    def test_invalid_duplicate_rule_ids_are_rejected(self):
        config = {"rules": [
            {"id": "same", "type": "zone_intrusion", "polygon": [[0, 0], [1, 0], [1, 1]]},
            {"id": "same", "type": "zone_intrusion", "polygon": [[0, 0], [1, 0], [1, 1]]},
        ]}
        with self.assertRaises(AnalyticsConfigError):
            validate_config(config)


if __name__ == "__main__":
    unittest.main()
