"""Catalog lookups, search, and collection listings."""

import unittest
from types import SimpleNamespace
from unittest import mock

from tidal_dl.enums import Type
from tidal_dl.runtime import job_context
from tidal_dl.tidal import TidalAPI, TidalApiError

from fixtures import CatalogFixtures, ProfileFixture, TransferFixture


class CollectionWarningTests(TransferFixture, unittest.TestCase):
    def test_unavailable_collection_entries_reach_warning_summary(self):
        api = TidalAPI()
        warnings = []
        data = [{'type': 'track', 'item': {'id': 1, 'title': 'Unavailable', 'streamReady': False}}]
        with job_context(warning=warnings.append), mock.patch.object(api, '_getItems', return_value=data):
            self.assertEqual(api.getItems(1, Type.Album), ([], []))
        self.assertEqual(warnings, ['Skipped unavailable track: Unavailable'])


class PaginationTests(ProfileFixture, unittest.TestCase):
    def test_catalog_full_last_page_does_not_request_an_extra_page(self):
        api = TidalAPI()
        self.addCleanup(api.session.close)
        rows = list(range(50))
        with mock.patch.object(api, '_get', return_value={'totalNumberOfItems': 50, 'items': rows}) as get:
            self.assertEqual(api._getItems('albums'), rows)
            get.assert_called_once()


class CatalogTests(CatalogFixtures, unittest.TestCase):
    def test_get_album_converts_each_artist_to_model(self):
        api = TidalAPI()
        payload = {
            "id": 123,
            "title": "Album",
            "artist": {"id": 123, "name": "Artist One"},
            "artists": [
                {"id": 123, "name": "Artist One"},
                {"id": 456, "name": "Artist Two"},
            ],
        }

        with mock.patch.object(api, "_get", return_value=payload):
            album = api.getAlbum(123)

        self.assertEqual([artist.id for artist in album.artists], [123, 456])
        self.assertEqual([artist.name for artist in album.artists], ["Artist One", "Artist Two"])

    def test_get_track_converts_each_artist_to_model(self):
        api = TidalAPI()
        payload = {
            "id": 456,
            "title": "Track",
            "artist": {"id": 123, "name": "Artist One"},
            "artists": [
                {"id": 123, "name": "Artist One"},
                {"id": 456, "name": "Artist Two"},
            ],
            "album": {"id": 1, "title": "Album"},
        }

        with mock.patch.object(api, "_get", return_value=payload):
            track = api.getTrack(456)

        self.assertEqual([artist.id for artist in track.artists], [123, 456])
        self.assertEqual([artist.name for artist in track.artists], ["Artist One", "Artist Two"])

    def test_artists_helpers_tolerate_none_and_missing_names(self):
        api = TidalAPI()
        self.assertEqual(api.getArtistsName(None), "")
        self.assertEqual(api.getArtistsID(None), "")
        self.assertEqual(api.getArtistsName([self._artist(None, 1), None]), "")
        self.assertEqual(api.getArtistsID([self._artist("A", None), self._artist("B", 2)]), "2")

    def test_search_result_items_default_to_empty_list(self):
        api = TidalAPI()
        result = SimpleNamespace(
            tracks=SimpleNamespace(items=None),
            videos=SimpleNamespace(items=None),
            albums=SimpleNamespace(items=None),
            artists=SimpleNamespace(items=None),
            playlists=SimpleNamespace(items=None),
        )
        self.assertEqual(api.getSearchResultItems(result, Type.Track), [])
        self.assertEqual(api.getSearchResultItems(None, Type.Album), [])

    def test_search_result_items_wrap_single_model(self):
        api = TidalAPI()
        album = self._album()
        result = SimpleNamespace(albums=SimpleNamespace(items=album))
        self.assertEqual(api.getSearchResultItems(result, Type.Album), [album])

    def test_get_by_string_surfaces_auth_errors(self):
        api = TidalAPI()
        with mock.patch.object(api, "getTypeData", side_effect=TidalApiError("auth failed", 401)):
            with self.assertRaises(TidalApiError) as raised:
                api.getByString("123456")
        self.assertEqual(raised.exception.statusCode, 401)

    def test_get_by_string_surfaces_forbidden_errors(self):
        api = TidalAPI()
        with mock.patch.object(api, "getTypeData", side_effect=TidalApiError("forbidden", 403)):
            with self.assertRaises(TidalApiError) as raised:
                api.getByString("123456")
        self.assertEqual(raised.exception.statusCode, 403)

    def test_get_by_string_surfaces_network_errors(self):
        import requests

        api = TidalAPI()
        with mock.patch.object(api, "getTypeData", side_effect=requests.ConnectionError("offline")):
            with self.assertRaises(requests.ConnectionError):
                api.getByString("123456")

    def test_album_items_include_tracks_when_stream_ready_missing(self):
        api = TidalAPI()
        api._getItems = lambda path: [
            {"type": "track", "item": {"id": 1, "title": "Legacy Ready"}},
            {"type": "track", "item": {"id": 2, "streamReady": False, "title": "Unavailable"}},
        ]

        tracks, videos = api.getItems("album-id", Type.Album)

        self.assertEqual([track.id for track in tracks], [1])
        self.assertEqual(videos, [])

    def test_album_items_skip_unstreamable_tracks_instead_of_treating_them_as_videos(self):
        api = TidalAPI()
        api._getItems = lambda path: [
            {"type": "track", "item": {"id": 1, "streamReady": True, "title": "Ready"}},
            {"type": "track", "item": {"id": 2, "streamReady": False, "title": "Unavailable"}},
            {"type": "video", "item": {"id": 3, "title": "Video"}},
        ]

        tracks, videos = api.getItems("album-id", Type.Album)

        self.assertEqual([track.id for track in tracks], [1])
        self.assertEqual([video.id for video in videos], [3])

    def test_artist_videos_fetches_artist_video_endpoint(self):
        api = TidalAPI()
        calls = []

        def fake_items(path, params=None):
            calls.append((path, params))
            return [
                {"id": 10, "title": "Video One"},
                {"type": "video", "item": {"id": 20, "title": "Video Two"}},
            ]

        api._getItems = fake_items

        videos = api.getArtistVideos(99)

        self.assertEqual(calls, [("artists/99/videos", None)])
        self.assertEqual([video.id for video in videos], [10, 20])
        self.assertEqual([video.title for video in videos], ["Video One", "Video Two"])

    def test_mix_lookup_returns_mix_object(self):
        api = TidalAPI()
        track = self._track()
        video = self._video()

        with mock.patch.object(api, "getItems", return_value=([track], [video])):
            mix = api.getMix("mix-id")

        self.assertEqual(mix.id, "mix-id")
        self.assertEqual(mix.tracks, [track])
        self.assertEqual(mix.videos, [video])

    def test_search_all_paginates_until_total(self):
        api = TidalAPI()
        pages = [
            SimpleNamespace(albums=SimpleNamespace(
                items=[SimpleNamespace(id=i, title=f"A{i}") for i in range(1, 51)],
                totalNumberOfItems=75,
            )),
            SimpleNamespace(albums=SimpleNamespace(
                items=[SimpleNamespace(id=i, title=f"A{i}") for i in range(51, 76)],
                totalNumberOfItems=75,
            )),
        ]

        with mock.patch.object(api, "search", side_effect=pages) as search:
            result = api.searchAll("O.S.T.R.", Type.Album)

        self.assertEqual(search.call_args_list[0].kwargs, {"offset": 0, "limit": 50})
        self.assertEqual(search.call_args_list[1].kwargs, {"offset": 50, "limit": 50})
        self.assertEqual(len(api.getSearchResultItems(result, Type.Album)), 75)
        self.assertEqual(search.call_count, 2)

    def test_search_all_stops_at_max_items(self):
        api = TidalAPI()
        page = SimpleNamespace(albums=SimpleNamespace(
            items=[SimpleNamespace(id=i) for i in range(50)],
            totalNumberOfItems=400,
        ))

        with mock.patch.object(api, "search", return_value=page) as search:
            result = api.searchAll("love", Type.Album, max_items=100)

        self.assertEqual(search.call_count, 2)
        self.assertEqual(len(api.getSearchResultItems(result, Type.Album)), 100)

    def test_find_matching_search_artists_normalizes_punctuation(self):
        api = TidalAPI()
        ostr = SimpleNamespace(id=4511654, name="O.S.T.R.")
        other = SimpleNamespace(id=1, name="ANOTR")
        matches = api.findMatchingSearchArtists("O.S.T.R.", [ostr, other])
        self.assertEqual(matches, [ostr])
        self.assertEqual(api.findMatchingSearchArtists("ostr", [ostr]), [ostr])
        self.assertEqual(api.findMatchingSearchArtists("love", [ostr, other]), [])

    def test_merge_matching_artist_albums_prepends_missing_discography(self):
        api = TidalAPI()
        artist = SimpleNamespace(id=4511654, name="O.S.T.R.")
        ranked = SimpleNamespace(id=1, title="W drodze po szczęście")
        buried = SimpleNamespace(id=2, title="Masz to jak w Banku")
        variant = SimpleNamespace(id=3, title="LTD.")

        with mock.patch.object(api, "getArtistAlbums", return_value=[buried, ranked, variant]) as discog:
            merged = api.mergeMatchingArtistAlbums(
                "O.S.T.R.",
                [ranked],
                [artist],
                includeEP=False,
            )

        discog.assert_called_once_with(4511654, includeEP=False)
        self.assertEqual([item.title for item in merged], [
            "Masz to jak w Banku",
            "W drodze po szczęście",
            "LTD.",
        ])

    def test_merge_matching_artist_albums_skips_unrelated_query(self):
        api = TidalAPI()
        ranked = SimpleNamespace(id=1, title="Album")
        with mock.patch.object(api, "getArtistAlbums") as discog:
            merged = api.mergeMatchingArtistAlbums(
                "masz to jak w banku",
                [ranked],
                [SimpleNamespace(id=4511654, name="O.S.T.R.")],
            )
        discog.assert_not_called()
        self.assertEqual(merged, [ranked])

    def test_search_albums_for_query_uses_discography_when_artist_matches(self):
        api = TidalAPI()
        artist = SimpleNamespace(id=4511654, name="O.S.T.R.")
        ranked = SimpleNamespace(id=1, title="404")
        buried = SimpleNamespace(id=2, title="Masz to jak w Banku")
        artist_page = SimpleNamespace(artists=SimpleNamespace(items=[artist]))
        album_page = SimpleNamespace(albums=SimpleNamespace(items=[ranked], totalNumberOfItems=125))

        def fake_search(text, etype, offset=0, limit=10):
            self.assertEqual(text, "O.S.T.R.")
            if etype == Type.Artist:
                return artist_page
            return album_page

        with mock.patch.object(api, "search", side_effect=fake_search) as search, \
             mock.patch.object(api, "searchAll") as search_all, \
             mock.patch.object(api, "getArtistAlbums", return_value=[buried, ranked]), \
             mock.patch.object(api, "preferAtmosSearchAlbums", side_effect=lambda albums: albums):
            albums = api.searchAlbumsForQuery("O.S.T.R.", includeEP=True)

        search_all.assert_not_called()
        self.assertEqual([call.args[1] for call in search.call_args_list], [Type.Artist, Type.Album])
        self.assertEqual(search.call_args_list[1].kwargs["limit"], 50)
        self.assertEqual([item.title for item in albums], ["Masz to jak w Banku", "404"])

    def test_search_albums_for_query_paginates_when_no_artist_match(self):
        api = TidalAPI()
        albums = [SimpleNamespace(id=i, title=f"Hit {i}") for i in range(1, 12)]
        artist_page = SimpleNamespace(artists=SimpleNamespace(items=[
            SimpleNamespace(id=1, name="Unrelated"),
        ]))
        paged = SimpleNamespace(albums=SimpleNamespace(items=albums))

        with mock.patch.object(api, "search", return_value=artist_page) as search, \
             mock.patch.object(api, "searchAll", return_value=paged) as search_all, \
             mock.patch.object(api, "getArtistAlbums") as discog, \
             mock.patch.object(api, "preferAtmosSearchAlbums", side_effect=lambda items: items):
            result = api.searchAlbumsForQuery("masz to jak w banku")

        search.assert_called_once()
        search_all.assert_called_once_with("masz to jak w banku", Type.Album)
        discog.assert_not_called()
        self.assertEqual(len(result), 11)

    def test_album_flag_handles_missing_audio_modes(self):
        album = SimpleNamespace(audioQuality="LOW", audioModes=None, explicit=False)
        self.assertEqual(TidalAPI().getFlag(album, Type.Album), "")


if __name__ == "__main__":
    unittest.main()
