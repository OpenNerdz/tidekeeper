"""Sign-in, saved sessions, token refresh, and logout."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import requests

from tidal_dl import events
from tidal_dl.enums import AudioQuality
from tidal_dl.gui_app.backend import TidekeeperBackend
from tidal_dl.settings import SETTINGS, TOKEN, TokenSettings
from tidal_dl.tidal import API_BASE_PRIMARY, TIDAL_API, TidalAPI, TidalApiError

from fixtures import (
    ApiFixture,
    CatalogFixtures,
    DownloadFolderApiFixture,
    FakeResponse,
    ProfileFixture,
    TransferFixture,
    response,
)


class TokenPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(TOKEN.__dict__)
        self.addCleanup(lambda: (TOKEN.__dict__.clear(), TOKEN.__dict__.update(self.saved)))

    def test_save_key_to_token_writes_every_session_field(self):
        api = TidalAPI()
        api.apiKey = {"clientId": "client-a"}
        api.key.userId, api.key.countryCode = 42, "NL"
        api.key.accessToken, api.key.refreshToken = "access", "refresh"
        with mock.patch.object(TOKEN, "save") as save:
            api.saveKeyToToken(123.0)
        save.assert_called_once_with()
        self.assertEqual(
            (TOKEN.userid, TOKEN.countryCode, TOKEN.clientId, TOKEN.accessToken, TOKEN.refreshToken,
             TOKEN.expiresAfter),
            (42, "NL", "client-a", "access", "refresh", 123.0),
        )

    def test_manual_token_login_persists_session(self):
        api = TidalAPI()
        api.apiKey = {"clientId": "client-b"}

        def login(token, userid=None):
            api.key.userId, api.key.countryCode, api.key.accessToken = 9, "US", token

        with mock.patch.object(events, "TIDAL_API", api), \
                mock.patch.object(api, "loginByAccessToken", side_effect=login), \
                mock.patch.object(events.Printf, "enterSecret", side_effect=["pasted-access", "pasted-refresh"]), \
                mock.patch.object(TOKEN, "save"):
            events.loginByAccessToken()
        self.assertEqual(
            (TOKEN.userid, TOKEN.countryCode, TOKEN.clientId, TOKEN.accessToken, TOKEN.refreshToken,
             TOKEN.expiresAfter),
            (9, "US", "client-b", "pasted-access", "pasted-refresh", 0),
        )

    def test_oauth_data_includes_secret_only_when_configured(self):
        api = TidalAPI()
        api.apiKey = {"clientId": "id", "clientSecret": "secret"}
        self.assertEqual(api._oauthData(grant_type="refresh_token"), {
            "client_id": "id", "grant_type": "refresh_token", "scope": "r_usr w_usr w_sub",
            "client_secret": "secret",
        })
        api.apiKey = {"clientId": "id", "clientSecret": ""}
        self.assertNotIn("client_secret", api._oauthData())


class SessionLifecycleTests(TransferFixture, unittest.TestCase):
    def test_manual_login_preserves_supplied_refresh_token(self):
        backend = TidekeeperBackend()
        with mock.patch.dict(TOKEN.__dict__, {'refreshToken': 'old-refresh'}), \
             mock.patch.object(TIDAL_API, 'loginByAccessToken'), mock.patch.object(TOKEN, 'save'), \
             mock.patch.object(TIDAL_API, 'key', SimpleNamespace(userId=1, countryCode='US', accessToken='access', refreshToken=None)):
            backend.login_by_access_token('access', 'new-refresh')
            self.assertEqual(TOKEN.refreshToken, 'new-refresh')

    def test_verification_distinguishes_server_failure_from_bad_credentials(self):
        api = TidalAPI()
        server_error = FakeResponse(status=503, body={'error': 'Unavailable'})
        with mock.patch.object(api.session, 'get', return_value=server_error), self.assertRaises(TidalApiError):
            api.verifyAccessToken('dummy')
        self.assertTrue(server_error.closed)
        with mock.patch.object(api.session, 'get', return_value=FakeResponse(status=401)):
            self.assertFalse(api.verifyAccessToken('dummy'))
        with mock.patch.object(api.session, 'get', return_value=FakeResponse(body={'userId': 1, 'countryCode': 'US'})):
            self.assertTrue(api.verifyAccessToken('dummy'))

    def test_logout_invalidates_inflight_device_login_and_caches(self):
        api = TidalAPI()
        api.apiKey = {'clientId': 'dummy'}
        api._streamCache['old'] = 'stream'
        api._artistAlbumsCache['old'] = 'album'
        api._playbackBlockedParams['HIGH'] = float('inf')
        def complete_after_logout(*args):
            api.clearSession()
            return {'user': {'userId': 1, 'countryCode': 'US'}, 'access_token': 'access',
                    'refresh_token': 'refresh', 'expires_in': 3600}
        with mock.patch.object(api, '_post', side_effect=complete_after_logout):
            self.assertFalse(api.checkAuthStatus())
        self.assertFalse(api.key.accessToken)
        self.assertFalse(api._streamCache)
        self.assertFalse(api._artistAlbumsCache)
        self.assertFalse(api._playbackBlockedParams)

    def test_logout_clears_local_session_before_remote_revocation(self):
        api = TidalAPI()
        self.addCleanup(api.session.close)
        api.key.accessToken = 'private-access'
        result = FakeResponse(status=204)

        def revoke(*args, **kwargs):
            self.assertFalse(api.key.accessToken)
            return result

        with mock.patch.object(api.session, 'post', side_effect=revoke) as post, \
                mock.patch.object(api, 'clearSavedSession', side_effect=api.clearSession) as clear:
            self.assertTrue(api.logoutSavedSession())
        self.assertEqual(post.call_args.args[0], 'https://api.tidal.com/v1/logout')
        self.assertEqual(post.call_args.kwargs['headers']['authorization'], 'Bearer private-access')
        self.assertTrue(result.closed)
        clear.assert_called_once_with()

    def test_delayed_revocation_cannot_clear_a_new_login(self):
        api = TidalAPI()
        self.addCleanup(api.session.close)
        api.key.accessToken = 'old-access'
        pending = []
        with mock.patch.object(api, 'clearSavedSession', side_effect=api.clearSession) as clear, \
                mock.patch.object(api.session, 'post', return_value=FakeResponse(status=204)) as post:
            api.logoutSavedSession(revoke=pending.append)
            self.assertFalse(api.key.accessToken)
            post.assert_not_called()
            self.assertEqual(pending, ['old-access'])
            api.key.accessToken = 'new-access'
            self.assertTrue(api.revokeSession(pending.pop()))
            self.assertEqual(api.key.accessToken, 'new-access')
            clear.assert_called_once_with()
        self.assertEqual(post.call_args.kwargs['headers']['authorization'], 'Bearer old-access')

    def test_remote_logout_failure_keeps_local_session_cleared(self):
        api = TidalAPI()
        self.addCleanup(api.session.close)
        api.key.accessToken = 'private-access'
        with mock.patch.object(api, 'clearSavedSession', side_effect=api.clearSession), \
                mock.patch.object(api.session, 'post', side_effect=requests.Timeout):
            self.assertFalse(api.logoutSavedSession())
        self.assertFalse(api.key.accessToken)


class SavedLoginTests(ProfileFixture, unittest.TestCase):
    def test_token_reread_drops_previous_credentials(self):
        token = TokenSettings()
        path = self.root / 'token.json'
        path.write_text(json.dumps({'accessToken': 'old-token', 'userid': 7}))
        token.read(str(path))
        self.assertEqual(token.accessToken, 'old-token')
        path.write_text('{broken')
        token.read(str(path))
        self.assertIsNone(token.accessToken)
        self.assertIsNone(token.userid)
        path.unlink()
        token.accessToken = 'stale'
        token.read(str(path))
        self.assertIsNone(token.accessToken)

    def test_numeric_tokens_are_rejected_but_numeric_user_ids_work(self):
        path = self.root / 'token.json'
        path.write_text(json.dumps({'accessToken': 123, 'refreshToken': True, 'countryCode': 4, 'userid': 7}))
        token = TokenSettings()
        token.read(str(path))
        self.assertEqual(token.userid, 7)
        self.assertIsNone(token.accessToken)
        self.assertIsNone(token.refreshToken)
        self.assertIsNone(token.countryCode)

    def test_token_file_preserves_originating_client(self):
        path = self.root / 'token.json'
        token = TokenSettings()
        token.read(str(path))
        token.userid = 7
        token.clientId = 'client-one'
        token.accessToken = 'saved-token'
        token.save()

        loaded = TokenSettings()
        loaded.read(str(path))

        self.assertEqual(loaded.clientId, 'client-one')
        self.assertEqual(loaded.accessToken, 'saved-token')

    def test_client_change_clears_legacy_or_mismatched_session(self):
        api = TidalAPI()
        api.apiKey = {'clientId': 'current-client'}
        TOKEN.userid = 7
        TOKEN.countryCode = 'US'
        TOKEN.clientId = None
        TOKEN.accessToken = 'legacy-token'
        TOKEN.refreshToken = 'legacy-refresh'

        revoked = mock.Mock(status_code=204, close=mock.Mock())
        with mock.patch.object(TOKEN, 'save') as save, mock.patch.object(api.session, 'post', return_value=revoked):
            self.assertTrue(api.clearSavedSessionIfClientChanged())

        self.assertIsNone(TOKEN.accessToken)
        self.assertIsNone(TOKEN.refreshToken)
        self.assertIsNone(TOKEN.clientId)
        save.assert_called_once_with()

        TOKEN.clientId = 'current-client'
        TOKEN.accessToken = 'current-token'
        with mock.patch.object(TOKEN, 'save') as save:
            self.assertFalse(api.clearSavedSessionIfClientChanged())
        self.assertEqual(TOKEN.accessToken, 'current-token')
        save.assert_not_called()

    def test_gui_manual_login_does_not_reuse_old_refresh_token(self):
        TOKEN.refreshToken = 'previous-session'
        key = SimpleNamespace(userId=7, countryCode='US', accessToken='new', refreshToken='previous-session')
        with mock.patch.object(TIDAL_API, 'key', key), mock.patch.object(TIDAL_API, 'loginByAccessToken'), \
             mock.patch.object(TOKEN, 'save'):
            TidekeeperBackend().login_by_access_token('new')
            self.assertIsNone(TOKEN.refreshToken)
            self.assertIsNone(key.refreshToken)

    def test_cli_manual_login_does_not_reuse_old_refresh_token(self):
        TOKEN.refreshToken = 'previous-session'
        key = SimpleNamespace(userId=7, countryCode='US', accessToken='new', refreshToken='previous-session')
        with mock.patch.object(TIDAL_API, 'key', key), mock.patch.object(TIDAL_API, 'loginByAccessToken'), \
             mock.patch.object(events.Printf, 'enterSecret', side_effect=['new', '0']), mock.patch.object(TOKEN, 'save'):
            events.loginByAccessToken()
            self.assertIsNone(TOKEN.refreshToken)
            self.assertIsNone(key.refreshToken)


class DeviceLoginTests(ApiFixture, unittest.TestCase):
    def test_oauth_requests_do_not_follow_redirects(self):
        result = response(status=302)
        with mock.patch.object(self.api.session, 'post', return_value=result) as post, \
                self.assertRaises(TidalApiError):
            self.api._post('/token', {'grant_type': 'device'})
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        result.close.assert_called_once()

    def test_sign_in_address_accepts_bare_host_and_https(self):
        for uri in ('link.tidal.com', 'https://link.tidal.com'):
            grant = {'deviceCode': 'device', 'userCode': 'AB-CD', 'verificationUri': uri,
                     'expiresIn': 300, 'interval': 5}
            with self.subTest(uri=uri), mock.patch.object(self.api, '_post', return_value=grant):
                self.assertEqual(self.api.getDeviceCode(), 'https://link.tidal.com/AB-CD')

    def test_sign_in_address_requires_expected_provider(self):
        grant = {'deviceCode': 'device', 'userCode': 'AB-CD', 'verificationUri': 'https://example.com',
                 'expiresIn': 300, 'interval': 5}
        with mock.patch.object(self.api, '_post', return_value=grant), self.assertRaises(TidalApiError):
            self.api.getDeviceCode()

    def test_cancelled_device_request_cannot_install_a_late_challenge(self):
        def grant(*args):
            self.api.clearSession()
            return {'deviceCode': 'device', 'userCode': 'AB-CD', 'verificationUri': 'link.tidal.com',
                    'expiresIn': 300, 'interval': 5}
        with mock.patch.object(self.api, '_post', side_effect=grant), self.assertRaises(TidalApiError):
            self.api.getDeviceCode()
        self.assertIsNone(self.api.key.deviceCode)

    def test_device_slow_down_increases_poll_interval(self):
        self.api.key.authCheckInterval = 5
        with mock.patch.object(self.api, '_post', return_value={'error': 'slow_down'}):
            self.assertFalse(self.api.checkAuthStatus())
            self.assertEqual(self.api.key.authCheckInterval, 10)


class DeviceLoginCancellationTests(DownloadFolderApiFixture, unittest.TestCase):
    def test_cancel_device_login_does_not_invalidate_a_token_refresh(self):
        self.api.key.accessToken = 'saved-access'
        original_generation = self.api._sessionGeneration
        grant = {'user': {'userId': 'test-user', 'countryCode': 'US'},
                 'access_token': 'renewed-access', 'refresh_token': 'renewed-refresh', 'expires_in': 60}
        def refresh(*args):
            self.api.cancelDeviceLogin()
            return grant
        with mock.patch.object(self.api, '_post', side_effect=refresh):
            self.assertTrue(self.api.refreshAccessToken('saved-refresh'))
        self.assertEqual(self.api.key.accessToken, 'renewed-access')
        self.assertEqual(self.api._sessionGeneration, original_generation)

    def test_cancel_device_login_preserves_search_and_playback_session(self):
        self.api.key.accessToken = 'saved-access'
        old_key = self.api._streamCacheKey('1', [AudioQuality.High])
        def search(*args, **kwargs):
            self.api.cancelDeviceLogin()
            return response(json.dumps({'tracks': {'items': []}}).encode())
        with mock.patch.object(self.api.session, 'get', side_effect=search):
            self.assertEqual(self.api._getOnce('search'), {'tracks': {'items': []}})
        self.assertEqual(self.api.key.accessToken, 'saved-access')
        self.assertEqual(self.api._streamCacheKey('1', [AudioQuality.High]), old_key)

    def test_cancelled_device_grant_cannot_replace_saved_login(self):
        self.api.key.accessToken = 'saved-access'
        def late_grant(*args):
            self.api.cancelDeviceLogin()
            return {'user': {'userId': 'late-user', 'countryCode': 'US'},
                    'access_token': 'late-access', 'refresh_token': 'late-refresh', 'expires_in': 60}
        with mock.patch.object(self.api, '_post', side_effect=late_grant):
            self.assertFalse(self.api.checkAuthStatus())
        self.assertEqual(self.api.key.accessToken, 'saved-access')

    def test_cancelled_device_request_cannot_install_challenge_or_backoff(self):
        for result, method in (
            ({'deviceCode': 'device', 'userCode': 'code', 'verificationUri': 'link.tidal.com',
              'expiresIn': 60, 'interval': 5}, self.api.getDeviceCode),
            ({'error': 'slow_down'}, self.api.checkAuthStatus),
        ):
            def cancel(*args):
                self.api.cancelDeviceLogin()
                return result
            self.api.key.authCheckInterval = 5
            with mock.patch.object(self.api, '_post', side_effect=cancel):
                if method == self.api.getDeviceCode:
                    with self.assertRaisesRegex(Exception, 'cancelled'):
                        method()
                else:
                    self.assertFalse(method())
            self.assertIsNone(self.api.key.deviceCode)
            self.assertEqual(self.api.key.authCheckInterval, 5)


class TokenRefreshTests(CatalogFixtures, unittest.TestCase):
    def test_device_auth_pending_without_status_keeps_waiting(self):
        api = TidalAPI()
        api.key.deviceCode = "device-code"

        with mock.patch.object(api, "_post", return_value={"error": "authorization_pending"}):
            self.assertFalse(api.checkAuthStatus())

    def test_manual_access_token_login_persists_userid(self):
        old_values = {
            "userid": events.TOKEN.userid,
            "countryCode": events.TOKEN.countryCode,
            "clientId": events.TOKEN.clientId,
            "accessToken": events.TOKEN.accessToken,
            "refreshToken": events.TOKEN.refreshToken,
            "expiresAfter": events.TOKEN.expiresAfter,
        }
        try:
            events.TOKEN.userid = None
            events.TOKEN.countryCode = None
            events.TOKEN.accessToken = None
            events.TOKEN.refreshToken = "old-refresh"
            events.TOKEN.expiresAfter = 0

            def fake_login(access_token, userid=None):
                events.TIDAL_API.key.userId = "user-123"
                events.TIDAL_API.key.countryCode = "GB"
                events.TIDAL_API.key.accessToken = access_token

            with mock.patch.object(events.Printf, "enterSecret", side_effect=["access-token", "0"]), \
                 mock.patch.object(events.TIDAL_API, "loginByAccessToken", fake_login), \
                 mock.patch.object(events.TOKEN, "save"):
                events.loginByAccessToken()

            self.assertEqual(events.TOKEN.userid, "user-123")
            self.assertEqual(events.TOKEN.countryCode, "GB")
        finally:
            for key, value in old_values.items():
                setattr(events.TOKEN, key, value)

    def test_refresh_access_token_preserves_rotated_refresh_token(self):
        api = TidalAPI()
        result = {
            "user": {"userId": "user-123", "countryCode": "GB"},
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        }

        with mock.patch.object(api, "_post", return_value=result):
            self.assertTrue(api.refreshAccessToken("old-refresh"))

        self.assertEqual(api.key.refreshToken, "new-refresh")

    def test_login_by_config_persists_rotated_refresh_token(self):
        old_values = {
            "userid": events.TOKEN.userid,
            "countryCode": events.TOKEN.countryCode,
            "clientId": events.TOKEN.clientId,
            "accessToken": events.TOKEN.accessToken,
            "refreshToken": events.TOKEN.refreshToken,
            "expiresAfter": events.TOKEN.expiresAfter,
        }
        try:
            events.TOKEN.userid = "user-123"
            events.TOKEN.countryCode = "GB"
            events.TOKEN.accessToken = "expired-access"
            events.TOKEN.refreshToken = "old-refresh"
            events.TOKEN.expiresAfter = 0

            def fake_refresh(refresh_token):
                events.TIDAL_API.key.userId = "user-123"
                events.TIDAL_API.key.countryCode = "GB"
                events.TIDAL_API.key.accessToken = "new-access"
                events.TIDAL_API.key.refreshToken = "new-refresh"
                events.TIDAL_API.key.expiresIn = 3600
                return True

            with mock.patch.object(events.TIDAL_API, "verifyAccessToken", return_value=False), \
                 mock.patch.object(events.TIDAL_API, "refreshAccessToken", fake_refresh), \
                 mock.patch.object(events.TOKEN, "save"):
                self.assertTrue(events.loginByConfig())

            self.assertEqual(events.TOKEN.refreshToken, "new-refresh")
        finally:
            for key, value in old_values.items():
                setattr(events.TOKEN, key, value)

    def test_api_get_refreshes_saved_token_after_unauthorized_response(self):
        api = TidalAPI()
        old_values = {
            "userid": events.TOKEN.userid,
            "countryCode": events.TOKEN.countryCode,
            "clientId": events.TOKEN.clientId,
            "accessToken": events.TOKEN.accessToken,
            "refreshToken": events.TOKEN.refreshToken,
            "expiresAfter": events.TOKEN.expiresAfter,
        }

        def fake_response(status, body):
            text = json.dumps(body)
            return SimpleNamespace(
                status_code=status,
                url="https://api.tidalhifi.com/v1/albums/123",
                text=text,
                json=lambda: body,
                close=mock.Mock(),
            )

        try:
            events.TOKEN.userid = "user-123"
            events.TOKEN.countryCode = "GB"
            events.TOKEN.accessToken = "expired-access"
            events.TOKEN.refreshToken = "refresh-token"
            events.TOKEN.expiresAfter = 0
            api.key.accessToken = "expired-access"
            api.key.countryCode = "GB"

            def fake_refresh(refresh_token):
                self.assertEqual(refresh_token, "refresh-token")
                api.key.userId = "user-123"
                api.key.countryCode = "GB"
                api.key.accessToken = "fresh-access"
                api.key.refreshToken = "fresh-refresh"
                api.key.expiresIn = 3600
                return True

            with mock.patch.object(api, "refreshAccessToken", side_effect=fake_refresh), \
                 mock.patch.object(events.TOKEN, "save") as save, \
                 mock.patch.object(api.session, "get", side_effect=[
                     fake_response(401, {"status": 401}),
                     fake_response(200, {"id": 123, "title": "Album"}),
                 ]) as get:
                data = api._get("albums/123")

            self.assertEqual(data["title"], "Album")
            self.assertEqual(events.TOKEN.accessToken, "fresh-access")
            self.assertEqual(events.TOKEN.refreshToken, "fresh-refresh")
            save.assert_called_once_with()
            self.assertEqual(get.call_args_list[0].kwargs["headers"]["authorization"], "Bearer expired-access")
            self.assertEqual(get.call_args_list[1].kwargs["headers"]["authorization"], "Bearer fresh-access")
        finally:
            for key, value in old_values.items():
                setattr(events.TOKEN, key, value)

    def test_invalid_token_file_is_treated_as_signed_out(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "token.json"
            token_path.write_text("not-base64-or-json", encoding="utf-8")

            token = TokenSettings()
            token.read(str(token_path))

        self.assertIsNone(token.accessToken)
        self.assertIsNone(token.refreshToken)

    @unittest.skipIf(sys.platform.startswith("win"), "POSIX file mode check")
    def test_token_save_restricts_file_permissions(self):
        token = TokenSettings()
        token.accessToken = "access"
        token.refreshToken = "refresh"
        with tempfile.TemporaryDirectory() as temp_dir:
            token.read(str(Path(temp_dir) / "token.json"))
            token.save()

            mode = Path(token._path_).stat().st_mode & 0o777

        self.assertEqual(mode, 0o600)

    def test_api_get_recovers_stale_client_404_by_refreshing_token(self):
        api = TidalAPI()
        api.key.accessToken = "stale-access"
        api.key.countryCode = "GB"

        stale_body = {
            "status": 404,
            "subStatus": 4022,
            "userMessage": "Client referenced in the request does not seem to exist.",
        }

        def fake_response(status, body):
            return SimpleNamespace(
                status_code=status,
                text=json.dumps(body),
                headers={},
                close=mock.Mock(),
                json=mock.Mock(return_value=body),
            )

        def fake_refresh():
            api.key.accessToken = "fresh-access"
            return True

        with mock.patch.object(api, "_refreshSavedAccessToken", side_effect=fake_refresh), \
             mock.patch.object(api.session, "get", side_effect=[
                 fake_response(404, stale_body),
                 fake_response(200, {"id": 123, "title": "Album"}),
             ]) as get:
            data = api._get("albums/123")

        self.assertEqual(data["title"], "Album")
        self.assertEqual(get.call_args_list[0].kwargs["headers"]["authorization"], "Bearer stale-access")
        self.assertEqual(get.call_args_list[1].kwargs["headers"]["authorization"], "Bearer fresh-access")

    def test_catalog_stale_client_404_raises_relogin_error_when_refresh_fails(self):
        api = TidalAPI()
        api.key.accessToken = "stale-access"
        api.key.countryCode = "GB"

        stale_body = {
            "status": 404,
            "subStatus": 4022,
            "userMessage": "Client referenced in the request does not seem to exist.",
        }
        response = SimpleNamespace(
            status_code=404,
            text=json.dumps(stale_body),
            headers={},
            close=mock.Mock(),
            json=mock.Mock(return_value=stale_body),
        )

        old_delay = events.SETTINGS.downloadDelay
        try:
            events.SETTINGS.downloadDelay = False
            with mock.patch.multiple(events.TOKEN, userid="user", countryCode="GB",
                                     accessToken="stale-access", refreshToken="stale-refresh",
                                     expiresAfter=123), \
                 mock.patch.object(events.TOKEN, "save") as save_token, \
                 mock.patch.object(api, "_refreshSavedAccessToken", return_value=False), \
                 mock.patch.object(api.session, "get", return_value=response) as get_mock:
                with self.assertRaises(TidalApiError) as ctx:
                    api._getOnce(
                        "tracks/456",
                        {},
                        API_BASE_PRIMARY,
                    )
                self.assertIsNone(events.TOKEN.accessToken)
                self.assertIsNone(events.TOKEN.refreshToken)
                self.assertIsNone(api.key.accessToken)
                save_token.assert_called_once()
        finally:
            events.SETTINGS.downloadDelay = old_delay

        self.assertIn("log in again", str(ctx.exception))
        self.assertIn("4022", ctx.exception.errorCodes)
        self.assertEqual(get_mock.call_count, 1)


class AuthRequestTests(unittest.TestCase):
    def test_auth_post_retries_server_error_using_retry_after(self):
        api = TidalAPI()
        failed = mock.Mock(status_code=503, text="busy", headers={"Retry-After": "2"})
        failed.json.return_value = {"status": 503}
        success = mock.Mock(status_code=200, text='{"access_token":"ok"}', headers={})
        success.json.return_value = {"access_token": "ok"}
        with mock.patch.object(api.session, "post", side_effect=[failed, success]), \
             mock.patch("tidal_dl.tidal.time.sleep") as sleep:
            result = api._post("/token", {})
        self.assertEqual(result, {"access_token": "ok"})
        sleep.assert_called_once_with(max(2.0, SETTINGS.requestIntervalSeconds))

    def test_auth_post_rejects_non_object_json(self):
        api = TidalAPI()
        response = mock.Mock(status_code=200, text="[]", headers={})
        response.json.return_value = []
        with mock.patch.object(api.session, "post", return_value=response):
            with self.assertRaises(TidalApiError):
                api._post("/token", {})

    def test_saved_token_refresh_reuses_refresh_from_other_worker(self):
        api = TidalAPI()
        api.key.accessToken = "expired"
        old_values = (TOKEN.accessToken, TOKEN.refreshToken, TOKEN.userid, TOKEN.countryCode)
        try:
            TOKEN.accessToken = "fresh"
            TOKEN.refreshToken = "refresh"
            TOKEN.userid = "user"
            TOKEN.countryCode = "US"
            with mock.patch.object(api, "refreshAccessToken") as refresh:
                self.assertTrue(api._refreshSavedAccessToken())
            refresh.assert_not_called()
            self.assertEqual(api.key.accessToken, "fresh")
        finally:
            TOKEN.accessToken, TOKEN.refreshToken, TOKEN.userid, TOKEN.countryCode = old_values


if __name__ == "__main__":
    unittest.main()
