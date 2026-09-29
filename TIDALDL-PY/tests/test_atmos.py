import base64
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from tidal_dl import download, events
from tidal_dl.enums import AudioQuality, Type
from tidal_dl.tidal import TidalAPI

from fixtures import CatalogFixtures

ATMOS_MPD = """<?xml version='1.0' encoding='UTF-8'?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
  <Period>
    <AdaptationSet contentType="audio">
      <Representation codecs="ec-3">
        <SegmentTemplate
          initialization="https://audio.example/init.mp4"
          media="https://audio.example/$Number$.mp4"
          startNumber="1">
          <SegmentTimeline>
            <S d="48000" r="1" />
          </SegmentTimeline>
        </SegmentTemplate>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>
"""


def data_uri(xml):
    encoded = base64.b64encode(xml.encode("utf-8")).decode("ascii")
    return f"data:application/dash+xml;base64,{encoded}"


class AtmosTests(unittest.TestCase):
    def test_atmos_quality_uses_openapi_eac3_manifest(self):
        api = TidalAPI()

        with mock.patch.object(
            api,
            "_getOpenApiTrackManifest",
            return_value={"formats": ["EAC3_JOC"], "uri": data_uri(ATMOS_MPD)},
        ):
            stream = api.getStreamUrl(409406350, AudioQuality.Atmos)

        self.assertEqual(stream.soundQuality, "DOLBY_ATMOS")
        self.assertEqual(stream.codec, "ec-3")
        self.assertEqual(stream.manifestMimeType, "application/dash+xml")
        self.assertEqual(stream.container, "mp4")
        self.assertEqual(stream.urls, [
            "https://audio.example/init.mp4",
            "https://audio.example/1.mp4",
            "https://audio.example/2.mp4",
        ])

    def test_atmos_quality_falls_back_when_manifest_is_not_atmos(self):
        api = TidalAPI()
        manifest = base64.b64encode(json.dumps({
            "codecs": "flac",
            "urls": ["https://audio.example/fallback.flac"],
            "mimeType": "audio/flac",
        }).encode("utf-8")).decode("utf-8")

        with mock.patch.object(
            api,
            "_getOpenApiTrackManifest",
            return_value={"formats": ["AACLC"], "uri": data_uri(ATMOS_MPD)},
        ), mock.patch.object(api, "_getPlaybackData", return_value={
            "trackid": 560060,
            "audioQuality": "HI_RES_LOSSLESS",
            "manifestMimeType": "application/vnd.tidal.bt",
            "manifest": manifest,
        }):
            stream = api.getStreamUrl(560060, AudioQuality.Atmos)

        self.assertEqual(stream.soundQuality, "HI_RES_LOSSLESS")
        self.assertEqual(stream.url, "https://audio.example/fallback.flac")
        self.assertEqual(stream.requestedQuality, "Dolby Atmos")
        self.assertEqual(stream.fallbackQuality, "Max")
        self.assertEqual(stream.fallbackReason, "requested format is unavailable")


class AtmosCatalogTests(CatalogFixtures, unittest.TestCase):
    def test_track_flag_detects_atmos_audio_modes(self):
        track = SimpleNamespace(audioQuality="LOW", audioModes=["DOLBY_ATMOS"], explicit=False)
        self.assertEqual(TidalAPI().getFlag(track, Type.Track, short=False), "Dolby Atmos")
        self.assertEqual(TidalAPI().getFlag(track, Type.Track, short=True), "A")

    def test_search_quality_label_includes_atmos_mode(self):
        from tidal_dl.gui_app.backend import _item_quality

        album = SimpleNamespace(audioQuality="LOW", audioModes=["DOLBY_ATMOS"], explicit=True)
        self.assertEqual(_item_quality(album, Type.Album), "Normal · Dolby Atmos · Explicit")

        stereo = SimpleNamespace(audioQuality="LOSSLESS", audioModes=["STEREO"], explicit=False)
        self.assertEqual(_item_quality(stereo, Type.Album), "HiFi")

    def test_find_atmos_album_variant_prefers_matching_title(self):
        api = TidalAPI()
        stereo = SimpleNamespace(
            id=100,
            title="Happier Than Ever",
            audioModes=["STEREO"],
            audioQuality="LOSSLESS",
            explicit=True,
            numberOfTracks=16,
            artist=SimpleNamespace(id=7, name="Billie"),
            artists=[SimpleNamespace(id=7, name="Billie")],
        )
        atmos = SimpleNamespace(
            id=200,
            title="Happier Than Ever",
            audioModes=["DOLBY_ATMOS"],
            audioQuality="LOW",
            explicit=True,
            numberOfTracks=16,
            artist=SimpleNamespace(id=7, name="Billie"),
            artists=[SimpleNamespace(id=7, name="Billie")],
        )
        other = SimpleNamespace(
            id=300,
            title="Other Album",
            audioModes=["DOLBY_ATMOS"],
            audioQuality="LOW",
            explicit=False,
            numberOfTracks=10,
            artist=SimpleNamespace(id=7, name="Billie"),
            artists=[SimpleNamespace(id=7, name="Billie")],
        )
        with mock.patch.object(api, "getArtistAlbums", return_value=[stereo, other, atmos]):
            found = api.findAtmosAlbumVariant(stereo)
        self.assertIs(found, atmos)

    def test_find_atmos_track_variant_matches_title_and_number(self):
        api = TidalAPI()
        stereo_track = SimpleNamespace(
            id=11,
            title="Getting Older",
            audioModes=["STEREO"],
            isrc="USUG121",
            trackNumber=1,
            volumeNumber=1,
            album=SimpleNamespace(id=100),
        )
        stereo_album = SimpleNamespace(
            id=100,
            title="Happier Than Ever",
            audioModes=["STEREO"],
            audioQuality="LOSSLESS",
            explicit=True,
            numberOfTracks=16,
            artist=SimpleNamespace(id=7, name="Billie"),
            artists=[SimpleNamespace(id=7, name="Billie")],
        )
        atmos_album = SimpleNamespace(
            id=200,
            title="Happier Than Ever",
            audioModes=["DOLBY_ATMOS"],
            audioQuality="LOW",
            explicit=True,
            numberOfTracks=16,
            artist=SimpleNamespace(id=7, name="Billie"),
            artists=[SimpleNamespace(id=7, name="Billie")],
        )
        atmos_track = SimpleNamespace(
            id=22,
            title="Getting Older",
            audioModes=["DOLBY_ATMOS"],
            isrc="USUG121",
            trackNumber=1,
            volumeNumber=1,
            album=atmos_album,
        )
        with mock.patch.object(api, "getAlbum", return_value=stereo_album), \
             mock.patch.object(api, "findAtmosAlbumVariant", return_value=atmos_album), \
             mock.patch.object(api, "getItems", return_value=([atmos_track], [])):
            found = api.findAtmosTrackVariant(stereo_track)
        self.assertIs(found, atmos_track)

    def test_album_download_switches_to_atmos_catalog_when_requested(self):
        stereo = SimpleNamespace(
            id=100,
            title="Album",
            audioModes=["STEREO"],
            audioQuality="LOSSLESS",
            cover=None,
        )
        atmos = SimpleNamespace(
            id=200,
            title="Album",
            audioModes=["DOLBY_ATMOS"],
            audioQuality="LOW",
            cover=None,
        )
        old_quality = events.SETTINGS.audioQuality
        old_priority = events.SETTINGS.audioQualityPriority
        try:
            events.SETTINGS.audioQuality = AudioQuality.Atmos
            events.SETTINGS.audioQualityPriority = []
            with mock.patch.object(events.TIDAL_API, "findAtmosAlbumVariant", return_value=atmos) as resolve, \
                 mock.patch.object(events.Printf, "album"), \
                 mock.patch.object(events.Printf, "info"), \
                 mock.patch.object(events.TIDAL_API, "getItems", return_value=([], [])) as get_items, \
                 mock.patch.object(events, "downloadTracks", return_value=True), \
                 mock.patch.object(events, "downloadVideos", return_value=True), \
                 mock.patch.object(events, "downloadAlbumInfo"), \
                 mock.patch.object(events, "downloadCover"):
                self.assertTrue(events.start_album(stereo))
            resolve.assert_called_once_with(stereo)
            get_items.assert_called_once_with(200, Type.Album)
        finally:
            events.SETTINGS.audioQuality = old_quality
            events.SETTINGS.audioQualityPriority = old_priority

    def test_download_track_resolves_atmos_for_playlist_path(self):
        stereo = SimpleNamespace(
            id=11,
            title="Track",
            version=None,
            audioModes=["STEREO"],
            album=SimpleNamespace(id=100, title="Album"),
            allowStreaming=True,
            streamReady=True,
            explicit=False,
            audioQuality="LOSSLESS",
        )
        atmos = SimpleNamespace(
            id=22,
            title="Track",
            version=None,
            audioModes=["DOLBY_ATMOS"],
            album=SimpleNamespace(id=200, title="Album"),
            allowStreaming=True,
            streamReady=True,
            explicit=False,
            audioQuality="LOW",
        )
        atmos_album = SimpleNamespace(id=200, title="Album", cover=None)
        stream = self._stream()
        stream.soundQuality = "DOLBY_ATMOS"
        stream.codec = "ec-3"
        stream.fallbackReason = None
        old_quality = download.SETTINGS.audioQuality
        old_priority = download.SETTINGS.audioQualityPriority
        old_show = download.SETTINGS.showTrackInfo
        try:
            download.SETTINGS.audioQuality = AudioQuality.Atmos
            download.SETTINGS.audioQualityPriority = []
            download.SETTINGS.showTrackInfo = False
            with mock.patch.object(download.TIDAL_API, "findAtmosTrackVariant", return_value=atmos) as resolve, \
                 mock.patch.object(download.TIDAL_API, "getAlbum", return_value=atmos_album), \
                 mock.patch.object(download, "_getTrackStream", return_value=stream) as get_stream, \
                 mock.patch.object(download, "getTrackPath", return_value="/tmp/track.m4a"), \
                 mock.patch.object(download, "_existingMediaState", return_value=("/tmp/track.m4a", True)), \
                 mock.patch.object(download, "_saveLyricsForTrack", return_value=None), \
                 mock.patch.object(download.Printf, "success"), \
                 mock.patch.object(download.Printf, "info"):
                ok, err = download.downloadTrack(stereo, album=None, playlist=SimpleNamespace(uuid="p", title="Playlist"))
            self.assertTrue(ok)
            self.assertEqual(err, "")
            resolve.assert_called_once_with(stereo)
            get_stream.assert_called_once_with(22)
        finally:
            download.SETTINGS.audioQuality = old_quality
            download.SETTINGS.audioQualityPriority = old_priority
            download.SETTINGS.showTrackInfo = old_show

    def test_prefer_atmos_search_albums_injects_missing_twin(self):
        api = TidalAPI()
        stereo = SimpleNamespace(
            id=100,
            title="Album",
            audioModes=["STEREO"],
            audioQuality="LOSSLESS",
            explicit=False,
            numberOfTracks=10,
            artist=SimpleNamespace(id=1),
            artists=[SimpleNamespace(id=1)],
        )
        atmos = SimpleNamespace(
            id=200,
            title="Album",
            audioModes=["DOLBY_ATMOS"],
            audioQuality="LOW",
            explicit=False,
            numberOfTracks=10,
            artist=SimpleNamespace(id=1),
            artists=[SimpleNamespace(id=1)],
        )
        with mock.patch.object(api, "findAtmosAlbumVariant", return_value=atmos):
            enriched = api.preferAtmosSearchAlbums([stereo])
        self.assertEqual([item.id for item in enriched], [100, 200])

    def test_artist_album_list_skips_stereo_when_atmos_twin_present(self):
        stereo = SimpleNamespace(id=100, title="Album", audioModes=["STEREO"])
        atmos = SimpleNamespace(id=200, title="Album", audioModes=["DOLBY_ATMOS"])
        other = SimpleNamespace(id=300, title="Other", audioModes=["STEREO"])
        old_quality = events.SETTINGS.audioQuality
        old_priority = events.SETTINGS.audioQualityPriority
        try:
            events.SETTINGS.audioQuality = AudioQuality.Atmos
            events.SETTINGS.audioQualityPriority = []
            preferred = events._preferAtmosAlbums([stereo, atmos, other])
            self.assertEqual([item.id for item in preferred], [200, 300])
        finally:
            events.SETTINGS.audioQuality = old_quality
            events.SETTINGS.audioQualityPriority = old_priority

if __name__ == "__main__":
    unittest.main()
