import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def valid_params(**overrides):
    params = {
        "video": {
            "filename": "clip.mp4",
            "content_type": "video/mp4",
            "data": b"not-real-video",
        },
        "fps": "15",
        "width": "640",
        "encoder": "ffmpeg-high",
        "loop": "0",
        "start": "",
        "end": "",
        "transparent": "0",
    }
    params.update(overrides)
    return params


class ValidationTests(unittest.TestCase):
    def test_validate_params_normalizes_known_good_values(self):
        params = app.validate_params(valid_params(fps="999", loop="2", start="1.5", end="3.0"))

        self.assertEqual(params["fps"], 30)
        self.assertEqual(params["loop"], 2)
        self.assertEqual(params["start"], "1.5")
        self.assertEqual(params["end"], "3.0")

    def test_validate_params_rejects_unsupported_width(self):
        with self.assertRaisesRegex(ValueError, "Unsupported width"):
            app.validate_params(valid_params(width="999;rm -rf /"))

    def test_validate_params_rejects_bad_time_range(self):
        with self.assertRaisesRegex(ValueError, "End time must be greater"):
            app.validate_params(valid_params(start="5", end="4"))

    def test_loop_values_match_ui_labels(self):
        self.assertEqual(app.loop_values(0), (0, 0))
        self.assertEqual(app.loop_values(1), (-1, -1))
        self.assertEqual(app.loop_values(2), (1, 1))


class ResourceLimitTests(unittest.TestCase):
    def test_enforce_clip_limits_rejects_long_clip(self):
        with self.assertRaisesRegex(ValueError, "Clip is too long"):
            app.enforce_clip_limits(source_duration=120, start="", end="", fps=15)

    def test_enforce_clip_limits_rejects_too_many_frames(self):
        with self.assertRaisesRegex(ValueError, "too many frames"):
            app.enforce_clip_limits(source_duration=30, start="", end="", fps=31)

    def test_conversion_slot_is_nonblocking(self):
        acquired = app.conversion_slots.acquire(blocking=False)
        self.assertTrue(acquired)
        try:
            self.assertFalse(app.conversion_slots.acquire(blocking=False))
        finally:
            app.conversion_slots.release()


if __name__ == "__main__":
    unittest.main()
