import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class RuntimeEnvironmentTests(unittest.TestCase):
    def test_homebrew_tool_paths_are_available_to_subprocesses(self):
        path_parts = app.os.environ["PATH"].split(":")

        self.assertIn("/opt/homebrew/bin", path_parts)
        self.assertIn("/usr/local/bin", path_parts)


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

    def test_validate_params_defaults_encoder_to_libvips(self):
        params = valid_params()
        del params["encoder"]

        self.assertEqual(app.validate_params(params)["encoder"], "libvips")

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


def image_params(filenames, **overrides):
    images = [
        {"filename": fn, "content_type": "image/png", "data": b"x" * 10}
        for fn in filenames
    ]
    params = {"images": images, "fps": "1", "width": "640", "loop": "0", "transparent": "0"}
    params.update(overrides)
    return params


def build_multipart(boundary, fields):
    """fields: list of (name, filename_or_None, value_bytes)."""
    parts = []
    for name, filename, value in fields:
        head = f'Content-Disposition: form-data; name="{name}"'
        if filename is not None:
            head += f'; filename="{filename}"\r\nContent-Type: image/png'
        parts.append(
            ("--" + boundary + "\r\n" + head + "\r\n\r\n").encode() + value + b"\r\n"
        )
    parts.append(("--" + boundary + "--\r\n").encode())
    return b"".join(parts)


class MultipartParserTests(unittest.TestCase):
    def test_repeated_file_field_accumulates_in_order(self):
        boundary = "BOUND"
        body = build_multipart(boundary, [
            ("images", "a.png", b"AAA"),
            ("images", "b.png", b"BBB"),
            ("images", "c.png", b"CCC"),
            ("fps", None, b"1"),
        ])
        result = app.parse_multipart(body, f"multipart/form-data; boundary={boundary}")
        self.assertIsInstance(result["images"], list)
        self.assertEqual([i["filename"] for i in result["images"]], ["a.png", "b.png", "c.png"])
        self.assertEqual([i["data"] for i in result["images"]], [b"AAA", b"BBB", b"CCC"])
        self.assertEqual(result["fps"], "1")

    def test_single_file_field_stays_dict(self):
        boundary = "BOUND"
        body = build_multipart(boundary, [("video", "clip.mp4", b"VVV")])
        result = app.parse_multipart(body, f"multipart/form-data; boundary={boundary}")
        self.assertIsInstance(result["video"], dict)


class ImageModeValidationTests(unittest.TestCase):
    def test_images_mode_forces_gifski_and_sets_mode(self):
        params = app.validate_params(image_params(["a.png", "b.png"]))
        self.assertEqual(params["mode"], "images")
        self.assertEqual(params["encoder"], "gifski")
        self.assertEqual(len(params["images"]), 2)

    def test_seconds_per_photo_converts_to_inverse_fps(self):
        # 2s/photo -> 0.5 fps, 4s/photo -> 0.25 fps
        self.assertEqual(app.validate_params(image_params(["a.png"], seconds_per_photo="2"))["fps"], 0.5)
        self.assertEqual(app.validate_params(image_params(["a.png"], seconds_per_photo="4"))["fps"], 0.25)

    def test_seconds_per_photo_defaults_to_one_second(self):
        params = image_params(["a.png"])  # no seconds_per_photo provided
        self.assertEqual(app.validate_params(params)["fps"], 1.0)

    def test_seconds_per_photo_is_clamped(self):
        # below 0.25 -> 0.25 (fps 4); above 10 -> 10 (fps 0.1)
        self.assertEqual(app.validate_params(image_params(["a.png"], seconds_per_photo="0"))["fps"], 4.0)
        self.assertEqual(app.validate_params(image_params(["a.png"], seconds_per_photo="999"))["fps"], 0.1)

    def test_single_image_is_normalized_to_list(self):
        params = image_params(["only.png"])
        params["images"] = params["images"][0]  # parser yields a dict for one file
        result = app.validate_params(params)
        self.assertEqual(len(result["images"]), 1)

    def test_rejects_unsupported_image_type(self):
        with self.assertRaisesRegex(ValueError, "Unsupported image type"):
            app.validate_params(image_params(["a.png", "b.tiff"]))

    def test_rejects_both_video_and_images(self):
        params = image_params(["a.png"])
        params["video"] = {"filename": "c.mp4", "content_type": "video/mp4", "data": b"v"}
        with self.assertRaisesRegex(ValueError, "either one video or a series"):
            app.validate_params(params)

    def test_rejects_too_many_images(self):
        names = [f"f{i}.png" for i in range(app.MAX_OUTPUT_FRAMES + 1)]
        with self.assertRaisesRegex(ValueError, "Too many images"):
            app.validate_params(image_params(names))

    def test_canvas_defaults_to_first_and_passes_through(self):
        self.assertEqual(app.validate_params(image_params(["a.png"]))["canvas"], "first")
        self.assertEqual(
            app.validate_params(image_params(["a.png"], canvas="16:9"))["canvas"], "16:9"
        )

    def test_rejects_unsupported_canvas(self):
        with self.assertRaisesRegex(ValueError, "Unsupported canvas"):
            app.validate_params(image_params(["a.png"], canvas="hexagon"))


class CanvasDimsTests(unittest.TestCase):
    SIZES = [(640, 480), (540, 360), (200, 900)]

    def test_first_uses_first_photo(self):
        self.assertEqual(app._canvas_dims("first", self.SIZES), (640, 480))

    def test_bbox_uses_max_each_axis(self):
        self.assertEqual(app._canvas_dims("bbox", self.SIZES), (640, 900))

    def test_square_uses_longest_edge(self):
        self.assertEqual(app._canvas_dims("1:1", self.SIZES), (900, 900))

    def test_widescreen_and_vertical_ratios(self):
        self.assertEqual(app._canvas_dims("16:9", self.SIZES), (900, 506))
        self.assertEqual(app._canvas_dims("9:16", self.SIZES), (506, 900))


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
