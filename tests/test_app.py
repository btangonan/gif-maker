import unittest
import io
import sys
import tempfile
from unittest import mock
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

    def test_validate_params_accepts_one_fps(self):
        self.assertEqual(app.validate_params(valid_params(fps="1"))["fps"], 1)

    def test_validate_params_accepts_slowdown_option(self):
        for speed in ("2", "3", "4"):
            with self.subTest(speed=speed):
                params = app.validate_params(valid_params(speed=speed))

                self.assertEqual(params["speed_factor"], float(speed))

    def test_validate_params_rejects_unsupported_speed(self):
        with self.assertRaisesRegex(ValueError, "Unsupported speed"):
            app.validate_params(valid_params(speed="5"))

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

    def test_filename_with_semicolon_is_preserved(self):
        # A semicolon in the filename must not truncate it (which would drop
        # the extension and fail later type validation for the whole batch).
        boundary = "BOUND"
        tricky = "002_add_35mm_grain;_preserve_all.png"
        body = build_multipart(boundary, [("images", tricky, b"PNG")])
        result = app.parse_multipart(body, f"multipart/form-data; boundary={boundary}")
        self.assertEqual(result["images"]["filename"], tricky)

    def test_zero_byte_file_part_is_preserved(self):
        boundary = "BOUND"
        body = build_multipart(boundary, [("video", "empty.mp4", b"")])

        result = app.parse_multipart(body, f"multipart/form-data; boundary={boundary}")

        self.assertEqual(result["video"]["filename"], "empty.mp4")
        self.assertEqual(result["video"]["data"], b"")

    def test_missing_boundary_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "No boundary found"):
            app.parse_multipart(b"", "multipart/form-data")

    def test_malformed_content_disposition_part_is_ignored(self):
        boundary = "BOUND"
        body = (
            b"--BOUND\r\n"
            b"Content-Disposition: form-data; filename=\"clip.mp4\"\r\n"
            b"Content-Type: video/mp4\r\n\r\n"
            b"VVV\r\n"
            b"--BOUND--\r\n"
        )

        self.assertEqual(app.parse_multipart(body, f"multipart/form-data; boundary={boundary}"), {})


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

    def test_slowdown_doubles_seconds_per_photo(self):
        self.assertEqual(
            app.validate_params(image_params(["a.png"], seconds_per_photo="2", speed="2"))["fps"],
            0.25,
        )

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

    def test_rejects_oversize_image_series_total(self):
        with mock.patch.object(app, "MAX_UPLOAD_BYTES", 20), mock.patch.object(app, "MAX_UPLOAD_MB", 1):
            with self.assertRaisesRegex(ValueError, "Images too large"):
                app.validate_params(image_params(["a.png", "b.png", "c.png"]))

    def test_rejects_unsupported_image_content_type(self):
        params = image_params(["a.png"])
        params["images"][0]["content_type"] = "application/octet-stream"

        with self.assertRaisesRegex(ValueError, "Unsupported image content type"):
            app.validate_params(params)


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
    def test_enforce_clip_limits_allows_sixty_second_clip(self):
        clip_duration, estimated_frames = app.enforce_clip_limits(
            source_duration=60, start="", end="", fps=15
        )

        self.assertEqual(clip_duration, 60)
        self.assertEqual(estimated_frames, 900)

    def test_enforce_clip_limits_rejects_long_clip(self):
        with self.assertRaisesRegex(ValueError, "Clip is too long"):
            app.enforce_clip_limits(source_duration=61, start="", end="", fps=15)

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

    def test_enforce_clip_limits_rejects_start_beyond_duration(self):
        with self.assertRaisesRegex(ValueError, "Start time is beyond"):
            app.enforce_clip_limits(source_duration=10, start="10", end="", fps=15)

    def test_enforce_clip_limits_allows_end_after_source_by_clamping(self):
        clip_duration, estimated_frames = app.enforce_clip_limits(
            source_duration=2.2, start="1", end="99", fps=10
        )

        self.assertAlmostEqual(clip_duration, 1.2)
        self.assertEqual(estimated_frames, 12)


class TimingHelperTests(unittest.TestCase):
    def test_video_filter_adds_setpts_for_slowdown(self):
        self.assertEqual(
            app._video_filter(15, "640", 2.0),
            "fps=15,setpts=2.0*PTS,scale=640:-2:flags=lanczos",
        )

    def test_video_filter_omits_setpts_for_normal_speed(self):
        self.assertEqual(app._video_filter(15, "original"), "fps=15,scale=iw:ih")

    def test_frame_delay_scales_with_speed_factor(self):
        self.assertEqual(app._frame_delay_ms(15, 2.0), 133)
        self.assertEqual(app._frame_delay_ms(15, 4.0), 267)

    def test_playback_fps_scales_with_speed_factor(self):
        self.assertEqual(app._playback_fps(15, 2.0), 7.5)
        self.assertEqual(app._playback_fps(16, 4.0), 4.0)


class CleanupLoopTests(unittest.TestCase):
    def setUp(self):
        self._jobs = app.jobs
        app.jobs = {}

    def tearDown(self):
        app.jobs = self._jobs

    def test_cleanup_loop_removes_expired_gifs_and_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            expired = output_dir / "expired.gif"
            fresh = output_dir / "fresh.gif"
            expired.write_bytes(b"old")
            fresh.write_bytes(b"new")
            old_time = app.time.time() - 3700
            app.os.utime(expired, (old_time, old_time))

            app.jobs = {
                "expired": {"status": "done"},
                "fresh": {"status": "done"},
                "running": {"status": "running"},
            }

            with mock.patch.object(app, "OUTPUT_DIR", output_dir):
                with mock.patch.object(app.time, "sleep", side_effect=[None, RuntimeError("stop")]):
                    with self.assertRaisesRegex(RuntimeError, "stop"):
                        app._cleanup_loop()

            self.assertFalse(expired.exists())
            self.assertTrue(fresh.exists())
            self.assertNotIn("expired", app.jobs)
            self.assertIn("fresh", app.jobs)
            self.assertIn("running", app.jobs)


def call_handler_get(path):
    handler = object.__new__(app.Handler)
    handler.path = path
    handler.wfile = io.BytesIO()
    response = {"code": None, "headers": []}
    handler.send_response = lambda code: response.__setitem__("code", code)
    handler.send_header = lambda key, value: response["headers"].append((key, value))
    handler.end_headers = lambda: None

    app.Handler.do_GET(handler)

    response["body"] = handler.wfile.getvalue()
    return response


def call_handler_post(path, body, headers):
    handler = object.__new__(app.Handler)
    handler.path = path
    handler.headers = headers
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    response = {"code": None, "headers": []}
    handler.send_response = lambda code: response.__setitem__("code", code)
    handler.send_header = lambda key, value: response["headers"].append((key, value))
    handler.end_headers = lambda: None

    app.Handler.do_POST(handler)

    response["body"] = handler.wfile.getvalue()
    return response


class HandlerPathTests(unittest.TestCase):
    def test_output_download_serves_gif_with_attachment_headers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            gif = output_dir / "job123.gif"
            gif.write_bytes(b"GIF89a")

            with mock.patch.object(app, "OUTPUT_DIR", output_dir):
                response = call_handler_get("/output/job123.gif")

        self.assertEqual(response["code"], 200)
        self.assertEqual(response["body"], b"GIF89a")
        self.assertIn(("Content-Type", "image/gif"), response["headers"])
        self.assertIn(("Content-Length", "6"), response["headers"])
        self.assertIn(("Content-Disposition", 'attachment; filename="job123.gif"'), response["headers"])

    def test_output_download_rejects_non_gif_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "not-gif.txt").write_bytes(b"nope")

            with mock.patch.object(app, "OUTPUT_DIR", output_dir):
                response = call_handler_get("/output/not-gif.txt")

        self.assertEqual(response["code"], 404)
        self.assertEqual(response["body"], b"Not found")

    def test_convert_rejects_invalid_content_length(self):
        response = call_handler_post("/convert", b"", {"Content-Length": "abc"})

        self.assertEqual(response["code"], 400)
        self.assertIn(b"Invalid Content-Length", response["body"])

    def test_convert_rejects_oversize_content_length_before_reading_body(self):
        with mock.patch.object(app, "MAX_UPLOAD_BYTES", 10), mock.patch.object(app, "MAX_UPLOAD_MB", 1):
            response = call_handler_post("/convert", b"", {"Content-Length": "11"})

        self.assertEqual(response["code"], 413)
        self.assertIn(b"File too large", response["body"])

    def test_convert_returns_503_when_conversion_slot_is_exhausted(self):
        boundary = "BOUND"
        body = (
            b"--BOUND\r\n"
            b"Content-Disposition: form-data; name=\"video\"; filename=\"clip.mp4\"\r\n"
            b"Content-Type: video/mp4\r\n\r\n"
            b"VVV\r\n"
            b"--BOUND--\r\n"
        )
        headers = {
            "Content-Length": str(len(body)),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        acquired = app.conversion_slots.acquire(blocking=False)
        self.assertTrue(acquired)
        try:
            with mock.patch.object(app, "run_conversion") as run_conversion:
                response = call_handler_post("/convert", body, headers)
        finally:
            app.conversion_slots.release()

        self.assertEqual(response["code"], 503)
        self.assertIn(b"Another conversion is running", response["body"])
        run_conversion.assert_not_called()


if __name__ == "__main__":
    unittest.main()
