import functools
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tidal_dl import download


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


class DownloadBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = self.root / "source"
        self.source.mkdir()
        handler = functools.partial(QuietHandler, directory=str(self.source))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp_dir.cleanup()

    def test_single_url_download(self):
        source_file = self.source / "track.bin"
        source_file.write_bytes(b"track-bytes" * 2048)
        output_file = self.root / "track.out"

        ok, msg = download.__downloadUrls__([f"{self.base_url}/track.bin"], str(output_file), threadNum=1)

        self.assertTrue(ok, msg)
        self.assertEqual(output_file.read_bytes(), source_file.read_bytes())

    def test_multi_url_download_preserves_order(self):
        (self.source / "000.bin").write_bytes(b"first-")
        (self.source / "001.bin").write_bytes(b"second-")
        (self.source / "002.bin").write_bytes(b"third")
        output_file = self.root / "joined.out"

        ok, msg = download.__downloadUrls__([
            f"{self.base_url}/000.bin",
            f"{self.base_url}/001.bin",
            f"{self.base_url}/002.bin",
        ], str(output_file), threadNum=3)

        self.assertTrue(ok, msg)
        self.assertEqual(output_file.read_bytes(), b"first-second-third")

    def test_multi_url_sequential_download_preserves_order(self):
        (self.source / "000.bin").write_bytes(b"init")
        (self.source / "001.bin").write_bytes(b"media-one")
        (self.source / "002.bin").write_bytes(b"media-two")
        output_file = self.root / "joined-sequential.out"

        ok, msg = download.__downloadUrls__([
            f"{self.base_url}/000.bin",
            f"{self.base_url}/001.bin",
            f"{self.base_url}/002.bin",
        ], str(output_file), threadNum=1)

        self.assertTrue(ok, msg)
        self.assertEqual(output_file.read_bytes(), b"initmedia-onemedia-two")

    def test_failed_download_preserves_existing_output_file(self):
        output_file = self.root / "existing.out"
        output_file.write_bytes(b"known-good")

        ok, msg = download.__downloadUrls__([f"{self.base_url}/missing.bin"], str(output_file), threadNum=1)

        self.assertFalse(ok)
        self.assertIn("404", msg)
        self.assertEqual(output_file.read_bytes(), b"known-good")

    def test_single_url_download_resumes_existing_partial_file(self):
        output_file = self.root / "resumed.out"
        partial_file = Path(str(output_file) + ".download")
        partial_file.write_bytes(b"first-")

        class FakeResponse:
            status_code = 206
            headers = {"Content-Range": "bytes 6-11/12"}

            def iter_content(self, chunk_size):
                yield b"second"

            def close(self):
                pass

        with mock.patch.object(download, "__httpRequest__", return_value=FakeResponse()) as request:
            ok, msg = download.__downloadUrls__(
                ["https://example.invalid/media.bin"],
                str(output_file),
                threadNum=1,
                probeSize=False,
            )

        self.assertTrue(ok, msg)
        self.assertEqual(output_file.read_bytes(), b"first-second")
        self.assertFalse(partial_file.exists())
        self.assertEqual(request.call_args.kwargs["headers"], {"Range": "bytes=6-"})

    def test_flac_export_without_ffmpeg_falls_back_to_m4a_container(self):
        old_value = download.SETTINGS.saveAsFlac
        source = self.root / "track.flac"
        source.write_bytes(b"mp4-container")
        stream = SimpleNamespace(codec="flac", container="mp4", manifestMimeType="application/dash+xml")
        try:
            download.SETTINGS.saveAsFlac = True
            with mock.patch.object(download.shutil, "which", return_value=None):
                final_path = download.__exportFlacFromContainer__(str(source), stream)
        finally:
            download.SETTINGS.saveAsFlac = old_value

        fallback = self.root / "track.m4a"
        self.assertEqual(final_path, str(fallback))
        self.assertFalse(source.exists())
        self.assertEqual(fallback.read_bytes(), b"mp4-container")

    def test_flac_export_uses_ffmpeg_flac_muxer(self):
        old_value = download.SETTINGS.saveAsFlac
        source = self.root / "track.flac"
        source.write_bytes(b"mp4-container")
        stream = SimpleNamespace(codec="flac", container="mp4", manifestMimeType="application/dash+xml")

        def fake_run(command, **kwargs):
            Path(command[-1]).write_bytes(b"raw-flac")
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        try:
            download.SETTINGS.saveAsFlac = True
            with mock.patch.object(download.shutil, "which", return_value="/usr/bin/ffmpeg"), \
                 mock.patch.object(download.subprocess, "run", side_effect=fake_run) as run:
                final_path = download.__exportFlacFromContainer__(str(source), stream)
        finally:
            download.SETTINGS.saveAsFlac = old_value

        self.assertEqual(final_path, str(source))
        self.assertEqual(source.read_bytes(), b"raw-flac")
        self.assertIn("-f", run.call_args.args[0])
        self.assertIn("flac", run.call_args.args[0])

    def test_save_as_flac_skip_accepts_existing_remuxed_file(self):
        old_values = {
            "saveAsFlac": download.SETTINGS.saveAsFlac,
            "checkExist": download.SETTINGS.checkExist,
        }
        existing = self.root / "track.flac"
        existing.write_bytes(b"raw-flac")
        stream = SimpleNamespace(
            urls=["https://example.invalid/init.mp4"],
            codec="flac",
            container="mp4",
            manifestMimeType="application/dash+xml",
        )
        try:
            download.SETTINGS.saveAsFlac = True
            download.SETTINGS.checkExist = True
            with mock.patch.object(download, "__remoteSize__", return_value=-1):
                self.assertEqual(download.__skipPath__(str(existing), stream), str(existing))
        finally:
            for key, value in old_values.items():
                setattr(download.SETTINGS, key, value)


if __name__ == "__main__":
    unittest.main()
