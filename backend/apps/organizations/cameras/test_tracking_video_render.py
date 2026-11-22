from django.test import SimpleTestCase

from .tracking_video_render import (
    interpolate_track_observation,
    scale_box,
    track_color,
)


class InterpolateTrackObservationTests(SimpleTestCase):
    def setUp(self):
        self.points = [
            {
                "frame_number": 10,
                "timestamp_seconds": 1.0,
                "confidence": 0.8,
                "bounding_box": [0, 10, 20, 30],
            },
            {
                "frame_number": 11,
                "timestamp_seconds": 2.0,
                "confidence": 1.0,
                "bounding_box": [10, 20, 30, 40],
            },
        ]

    def test_interpolates_box_between_consecutive_observations(self):
        result = interpolate_track_observation(self.points, 1.5, 12.0, 2)
        self.assertIsNotNone(result)
        box, confidence = result
        self.assertEqual(box, [5.0, 15.0, 25.0, 35.0])
        self.assertAlmostEqual(confidence, 0.9)

    def test_does_not_interpolate_beyond_allowed_missing_sample_frames(self):
        points = [self.points[0], {**self.points[1], "frame_number": 14}]
        self.assertIsNone(interpolate_track_observation(points, 1.5, 12.0, 2))
        self.assertIsNotNone(interpolate_track_observation(points, 1.5, 12.0, 3))

    def test_single_observation_is_drawn_only_on_nearest_video_frame(self):
        point = [self.points[0]]
        self.assertIsNotNone(interpolate_track_observation(point, 1.0, 12.0, 2))
        self.assertIsNone(interpolate_track_observation(point, 1.2, 12.0, 2))

    def test_returns_exact_last_observation(self):
        result = interpolate_track_observation(self.points, 2.0, 12.0, 0)
        self.assertEqual(result[0], [10.0, 20.0, 30.0, 40.0])

    def test_invalid_or_empty_input_returns_none(self):
        self.assertIsNone(interpolate_track_observation([], 1.0, 12.0, 2))
        self.assertIsNone(interpolate_track_observation(self.points, 1.0, 0.0, 2))

    def test_scale_box_uses_independent_x_and_y_scale(self):
        self.assertEqual(scale_box([1, 2, 3, 4], 2, 3), [2.0, 6.0, 6.0, 12.0])

    def test_track_color_is_stable_and_valid_bgr(self):
        first = track_color(7)
        second = track_color(7)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)
        self.assertTrue(all(0 <= channel <= 255 for channel in first))
