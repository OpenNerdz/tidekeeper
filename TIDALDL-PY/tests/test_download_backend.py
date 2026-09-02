import functools
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests

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

        with mock.patch.object(download.time, "sleep") as sleep:
            ok, msg = download.__downloadUrls__([f"{self.base_url}/missing.bin"], str(output_file), threadNum=1)

        self.assertFalse(ok)
        self.assertIn("404", msg)
        self.assertEqual(output_file.read_bytes(), b"known-good")
        sleep.assert_not_called()

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

    def test_single_url_download_resumes_after_stream_failure(self):
        output_file = self.root / "retried.out"
        payload = b"first-second"

        class FakeResponse:
            status_code = 200
            headers = {}

            def __init__(self, chunks, error=None, status_code=200, headers=None):
                self.chunks = chunks
                self.error = error
                self.status_code = status_code
                self.headers = headers or {}

            def iter_content(self, chunk_size):
                yield from self.chunks
                if self.error:
                    raise self.error

            def close(self):
                pass

        responses = [
            FakeResponse([b"first-"], requests.ConnectionError("connection dropped")),
            FakeResponse([b"second"], status_code=206, headers={"Content-Range": "bytes 6-11/12"}),
        ]
        with mock.patch.object(download, "__httpRequest__", side_effect=responses) as request, \
             mock.patch.object(download.time, "sleep"):
            ok, msg = download.__downloadUrls__(
                ["https://example.invalid/media.bin"],
                str(output_file),
                threadNum=1,
                probeSize=False,
            )

        self.assertTrue(ok, msg)
        self.assertEqual(output_file.read_bytes(), payload)
        self.assertEqual(request.call_args_list[1].kwargs["headers"], {"Range": "bytes=6-"})

    def test_single_url_mismatched_partial_rerequests_full_body(self):
        """If a Range response is not a matching 206, do not write its body as complete."""
        output_file = self.root / "mismatch.out"
        partial_file = Path(str(output_file) + ".download")
        partial_file.write_bytes(b"partial")

        class FakeResponse:
            def __init__(self, status_code, headers, chunks):
                self.status_code = status_code
                self.headers = headers
                self.chunks = chunks
                self.closed = False

            def iter_content(self, chunk_size):
                yield from self.chunks

            def close(self):
                self.closed = True

        bad_partial = FakeResponse(206, {"Content-Range": "bytes 0-5/12"}, [b"WRONG!"])
        full_body = FakeResponse(200, {}, [b"complete-body"])
        with mock.patch.object(download, "__httpRequest__", side_effect=[bad_partial, full_body]) as request:
            ok, msg = download.__downloadUrls__(
                ["https://example.invalid/media.bin"],
                str(output_file),
                threadNum=1,
                probeSize=False,
            )

        self.assertTrue(ok, msg)
        self.assertEqual(output_file.read_bytes(), b"complete-body")
        self.assertTrue(bad_partial.closed)
        self.assertEqual(len(request.call_args_list), 2)
        self.assertEqual(request.call_args_list[0].kwargs.get("headers"), {"Range": "bytes=7-"})
        self.assertEqual(request.call_args_list[1].kwargs.get("headers", {}), {})

    def test_multi_url_sequential_resumes_individual_segments(self):
        (self.source / "000.bin").write_bytes(b"AAAA")
        (self.source / "001.bin").write_bytes(b"BBBBCCCC")
        output_file = self.root / "seg-resume.out"

        ok, msg = download.__downloadUrls__([
            f"{self.base_url}/000.bin",
            f"{self.base_url}/001.bin",
        ], str(output_file), threadNum=1, probeSize=False)

        self.assertTrue(ok, msg)
        self.assertEqual(output_file.read_bytes(), b"AAAABBBBCCCC")

    def test_incomplete_size_verification_fails_download(self):
        class FakeResponse:
            status_code = 200
            headers = {"Content-Length": "10"}

            def iter_content(self, chunk_size):
                yield b"short"

            def close(self):
                pass

        output_file = self.root / "short.out"
        with mock.patch.object(download, "__httpRequest__", return_value=FakeResponse()), \
             mock.patch.object(download.time, "sleep"):
            ok, msg = download.__downloadUrls__(
                ["https://example.invalid/media.bin"],
                str(output_file),
                threadNum=1,
                probeSize=False,
            )

        self.assertFalse(ok)
        self.assertIn("Incomplete", msg)
        self.assertFalse(output_file.exists())

    def test_reuses_complete_output_without_redownload(self):
        output_file = self.root / "cached.out"
        payload = b"already-downloaded-bytes"
        output_file.write_bytes(payload)

        with mock.patch.object(download, "__httpRequest__") as request, \
             mock.patch.object(download, "__remoteSize__", return_value=len(payload)):
            ok, msg = download.__downloadUrls__(
                ["https://example.invalid/media.bin"],
                str(output_file),
                threadNum=1,
                probeSize=True,
            )

        self.assertTrue(ok, msg)
        self.assertEqual(output_file.read_bytes(), payload)
        request.assert_not_called()

    def test_multi_url_failure_preserves_completed_segments(self):
        (self.source / "000.bin").write_bytes(b"KEEPME")
        output_file = self.root / "partial-join.out"
        parts_dir = Path(str(output_file) + ".parts")

        with mock.patch.object(download.time, "sleep") as sleep:
            ok, msg = download.__downloadUrls__([
                f"{self.base_url}/000.bin",
                f"{self.base_url}/missing.bin",
            ], str(output_file), threadNum=1, probeSize=False)

        self.assertFalse(ok)
        self.assertTrue(parts_dir.exists())
        self.assertEqual((parts_dir / "00000000.part").read_bytes(), b"KEEPME")
        self.assertFalse(output_file.exists())
        sleep.assert_not_called()

    def test_parallel_multi_url_uses_resumable_segments(self):
        (self.source / "000.bin").write_bytes(b"one-")
        (self.source / "001.bin").write_bytes(b"two-")
        (self.source / "002.bin").write_bytes(b"three")
        output_file = self.root / "parallel.out"

        ok, msg = download.__downloadUrls__([
            f"{self.base_url}/000.bin",
            f"{self.base_url}/001.bin",
            f"{self.base_url}/002.bin",
        ], str(output_file), threadNum=3, probeSize=False)

        self.assertTrue(ok, msg)
        self.assertEqual(output_file.read_bytes(), b"one-two-three")
        self.assertFalse(Path(str(output_file) + ".parts").exists())

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
        existing.write_bytes(b"fLaC" + b"\x00" * 2048)
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

    def test_save_as_flac_skip_rejects_tiny_or_invalid_file(self):
        old_values = {
            "saveAsFlac": download.SETTINGS.saveAsFlac,
            "checkExist": download.SETTINGS.checkExist,
        }
        existing = self.root / "track.flac"
        existing.write_bytes(b"nope")
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
                self.assertIsNone(download.__skipPath__(str(existing), stream))
        finally:
            for key, value in old_values.items():
                setattr(download.SETTINGS, key, value)


class DownloadRetryTests(unittest.TestCase):
    def test_http_request_does_not_retry_not_found(self):
        response = mock.Mock(status_code=404, headers={})
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
        session = mock.Mock()
        session.request.return_value = response
        with mock.patch.object(download, "__httpSession__", return_value=session), \
             mock.patch.object(download.time, "sleep") as sleep:
            with self.assertRaises(requests.HTTPError):
                download.__httpRequest__("GET", "http://example.invalid/missing")
        self.assertEqual(session.request.call_count, 1)
        sleep.assert_not_called()

    def test_http_request_retries_service_unavailable(self):
        failed = mock.Mock(status_code=503, headers={"Retry-After": "1"})
        success = mock.Mock(status_code=200, headers={})
        success.raise_for_status.return_value = None
        session = mock.Mock()
        session.request.side_effect = [failed, success]
        with mock.patch.object(download, "__httpSession__", return_value=session), \
             mock.patch.object(download.time, "sleep") as sleep:
            result = download.__httpRequest__("GET", "http://example.invalid/track")
        self.assertIs(result, success)
        self.assertEqual(session.request.call_count, 2)
        sleep.assert_called_once()

    def test_http_request_retries_connection_error(self):
        success = mock.Mock(status_code=200, headers={})
        success.raise_for_status.return_value = None
        session = mock.Mock()
        session.request.side_effect = [requests.ConnectionError("drop"), success]
        with mock.patch.object(download, "__httpSession__", return_value=session), \
             mock.patch.object(download.time, "sleep") as sleep:
            result = download.__httpRequest__("GET", "http://example.invalid/track")
        self.assertIs(result, success)
        self.assertEqual(session.request.call_count, 2)
        sleep.assert_called_once()

    def test_incomplete_write_still_retries_after_http_200(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "incomplete.out"
            with mock.patch.object(download, "__httpRequest__", side_effect=IOError("disk full")), \
                 mock.patch.object(download.time, "sleep") as sleep:
                with self.assertRaises(IOError):
                    download.__downloadSingleUrl__(
                        "http://example.invalid/track.bin",
                        str(output_file),
                    )
            self.assertEqual(sleep.call_count, download.DOWNLOAD_RETRIES - 1)


class GuiDownloadStatusTests(unittest.TestCase):
    def test_backend_download_raises_when_start_fails(self):
        from tidal_dl.enums import Type
        from tidal_dl.gui_app.backend import SearchItem, TidekeeperBackend

        backend = TidekeeperBackend()
        item = SearchItem(Type.Null, "Track", "", "", "456", "", "456")
        with mock.patch.object(backend, "_ensure_catalog_session"), \
             mock.patch("tidal_dl.gui_app.backend.start", return_value=False):
            with self.assertRaises(RuntimeError) as raised:
                backend.download(item)

        self.assertIn("Track", str(raised.exception))

    def test_backend_download_succeeds_when_start_ok(self):
        from tidal_dl.enums import Type
        from tidal_dl.gui_app.backend import SearchItem, TidekeeperBackend

        backend = TidekeeperBackend()
        item = SearchItem(Type.Track, "Track", "", "", "456", "", SimpleNamespace(id=456))
        with mock.patch.object(backend, "_ensure_catalog_session"), \
             mock.patch("tidal_dl.gui_app.backend.start_type", return_value=True) as start_type:
            backend.download(item)

        start_type.assert_called_once()

    def test_backend_download_forwards_progress(self):
        from tidal_dl.enums import Type
        from tidal_dl.gui_app.backend import SearchItem, TidekeeperBackend

        backend = TidekeeperBackend()
        item = SearchItem(Type.Track, "Track", "", "", "456", "", SimpleNamespace(id=456))
        progress = object()
        with mock.patch.object(backend, "_ensure_catalog_session"), \
             mock.patch("tidal_dl.gui_app.backend.start_type", return_value=True) as start_type:
            backend.download(item, progress=progress)

        start_type.assert_called_once_with(Type.Track, item.source, False, progress=progress)

    def test_download_urls_skips_probe_when_expected_size_given(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "sized.out"
            with mock.patch.object(download, "__remoteSize__") as probe, \
                 mock.patch.object(download, "__downloadSingleUrl__", return_value=12):
                ok, msg = download.__downloadUrls__(
                    ["http://example.invalid/track.bin"],
                    str(output_file),
                    threadNum=1,
                    probeSize=False,
                    expectedSize=12,
                )

        self.assertTrue(ok, msg)
        probe.assert_not_called()

    def test_download_urls_still_probes_without_expected_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "probed.out"
            with mock.patch.object(download, "__remoteSize__", return_value=8) as probe, \
                 mock.patch.object(download, "__downloadSingleUrl__", return_value=8):
                ok, msg = download.__downloadUrls__(
                    ["http://example.invalid/track.bin"],
                    str(output_file),
                    threadNum=1,
                )

        self.assertTrue(ok, msg)
        probe.assert_called_once()

    def test_download_track_passes_probed_size_without_second_probe(self):
        track = SimpleNamespace(
            id=1,
            title="Song",
            allowStreaming=True,
            streamReady=True,
            album=None,
            artist=None,
            artists=[],
        )
        stream = SimpleNamespace(
            urls=["http://example.invalid/song.bin"],
            url="http://example.invalid/song.bin",
            codec="aac",
            container="mp4",
            manifestMimeType="",
            encryptionKey="",
        )
        old_show = download.SETTINGS.showTrackInfo
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "song.m4a")
            download.SETTINGS.showTrackInfo = False
            try:
                with mock.patch.object(download, "__resolveTrackForAtmosDownload__", return_value=(track, None)), \
                     mock.patch.object(download, "__getTrackStream__", return_value=stream), \
                     mock.patch.object(download, "getTrackPath", return_value=path), \
                     mock.patch.object(download, "__skipPath__", return_value=None), \
                     mock.patch.object(download, "__remoteSize__", return_value=4096) as probe, \
                     mock.patch.object(download, "__isReusableAssembledFile__", return_value=False), \
                     mock.patch.object(download, "__localFileSize__", return_value=0), \
                     mock.patch.object(download, "__downloadUrls__", return_value=(True, "")) as downloaded, \
                     mock.patch.object(download, "__encrypted__"), \
                     mock.patch.object(download, "__removeDir__"), \
                     mock.patch.object(download, "__exportFlacFromContainer__", side_effect=lambda out, _stream: out), \
                     mock.patch.object(download.TIDAL_API, "getTrackContributors", return_value=None), \
                     mock.patch.object(download, "__saveLyricsForTrack__", return_value=""), \
                     mock.patch.object(download, "__setMetaData__"), \
                     mock.patch.object(download, "__ensureParentDir__"):
                    ok, err = download.downloadTrack(track)
            finally:
                download.SETTINGS.showTrackInfo = old_show

        self.assertTrue(ok, err)
        probe.assert_called_once_with(stream.urls)
        self.assertEqual(downloaded.call_args.args[6], False)
        self.assertEqual(downloaded.call_args.args[7], 4096)

    def test_download_tracks_reports_collection_progress(self):
        class Recorder:
            def __init__(self):
                self.events = []

            def begin_collection(self, total):
                self.events.append(("collection", total))

            def begin_entry(self, index, total, title=""):
                self.events.append(("begin", index, total, title))

            def finish_entry(self, index, total, ok=True):
                self.events.append(("finish", index, total, ok))

        old_multi = download.SETTINGS.multiThread
        progress = Recorder()
        track_one = SimpleNamespace(id=1, title="One", album=None)
        track_two = SimpleNamespace(id=2, title="Two", album=None)
        try:
            download.SETTINGS.multiThread = False
            with mock.patch.object(download, "downloadTrack", return_value=(True, "")):
                self.assertTrue(download.downloadTracks([track_one, track_two], album=object(), progress=progress))
        finally:
            download.SETTINGS.multiThread = old_multi

        self.assertEqual(progress.events[0], ("collection", 2))
        self.assertEqual(progress.events[1], ("begin", 1, 2, "One"))
        self.assertEqual(progress.events[2], ("finish", 1, 2, True))
        self.assertEqual(progress.events[3], ("begin", 2, 2, "Two"))
        self.assertEqual(progress.events[4], ("finish", 2, 2, True))


class DirectInputAndProgressTests(unittest.TestCase):
    def test_parse_direct_inputs_splits_lines_and_commas(self):
        from tidal_dl.gui_app.backend import parse_direct_inputs

        tokens = parse_direct_inputs(
            "https://tidal.com/browse/track/1\n"
            "70973230, 77798028\n"
            "# comment\n"
            "https://tidal.com/browse/track/3 https://tidal.com/browse/track/4\n"
        )
        self.assertEqual(tokens, [
            "https://tidal.com/browse/track/1",
            "70973230",
            "77798028",
            "https://tidal.com/browse/track/3",
            "https://tidal.com/browse/track/4",
        ])

    def test_parse_direct_inputs_expands_text_file(self):
        from tidal_dl.gui_app.backend import parse_direct_inputs

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "urls.txt"
            path.write_text(
                "# header\n"
                "https://tidal.com/browse/track/1\n"
                "https://tidal.com/browse/track/2\n",
                encoding="utf-8",
            )
            self.assertEqual(parse_direct_inputs(str(path)), [
                "https://tidal.com/browse/track/1",
                "https://tidal.com/browse/track/2",
            ])

    def test_queue_progress_helpers(self):
        from tidal_dl.gui_app.backend import format_queue_progress, queue_progress_percent

        album = {
            "completed": 3,
            "count": 12,
            "current": 4,
            "bytes": 2 * 1024 * 1024,
            "bytes_total": 4 * 1024 * 1024,
            "speed": 2 * 1024 * 1024,
            "eta": 12,
        }
        self.assertEqual(format_queue_progress(album), "4/12 · 2.0 MB/s · 12s")
        self.assertEqual(queue_progress_percent(album), 29)

        single = {
            "completed": 0,
            "count": 1,
            "current": 1,
            "bytes": 1024,
            "bytes_total": 4096,
            "speed": 1024,
            "eta": 3,
        }
        self.assertEqual(format_queue_progress(single), "1.0 KB/4.0 KB · 1.0 KB/s · 3s")
        self.assertEqual(queue_progress_percent(single), 25)

    def test_progress_sink_failures_are_logged_not_raised(self):
        broken = SimpleNamespace(addCurCount=mock.Mock(side_effect=RuntimeError("widget gone")))
        healthy = SimpleNamespace(addCurNum=mock.Mock())
        with self.assertLogs(level="DEBUG") as logs:
            download.__noteProgress__(broken, healthy, 512, threading.Lock())
        healthy.addCurNum.assert_called_once_with(512)
        self.assertTrue(any("addCurCount" in line and "widget gone" in line for line in logs.output))

    def test_progress_helpers_ignore_missing_sinks_and_zero_sizes(self):
        sink = SimpleNamespace(setMaxNum=mock.Mock(), addCurNum=mock.Mock())
        download.__setUserProgressMax__(None, 10)
        download.__setUserProgressMax__(sink, 0)
        download.__addUserProgress__(sink, -1)
        download.__noteProgress__(None, None, 10)
        sink.setMaxNum.assert_not_called()
        sink.addCurNum.assert_not_called()
        # Sinks missing a method are skipped rather than raising AttributeError.
        download.__noteProgress__(SimpleNamespace(), sink, 8)
        sink.addCurNum.assert_called_once_with(8)


if __name__ == "__main__":
    unittest.main()
