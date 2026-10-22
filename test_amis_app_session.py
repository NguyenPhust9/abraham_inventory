import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from amis_app_session import AmisAppSession, REFRESH_URL


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "session.json"
        self.session = AmisAppSession("old-token", "company", "old-refresh", self.path)
        self.session.http = Mock()
        self.url = "https://amisapp.misa.vn/crm/g1/api/business/Stock/productLedger/latest-warehouse"

    def tearDown(self):
        self.temp.cleanup()

    def response(self, status, data=None):
        result = Mock(status_code=status)
        result.json.return_value = data
        return result

    def test_refresh_rotation_is_saved_and_request_retried(self):
        success = self.response(200)
        self.session.http.request.side_effect = [self.response(401), success]
        self.session.http.post.return_value = self.response(200, {
            "Success": True, "Data": {"token": "new-token", "refresh_token": "new-refresh"}})
        self.assertIs(self.session.request("GET", self.url), success)
        self.assertEqual(self.session.http.post.call_args.args[0], REFRESH_URL)
        self.assertEqual(self.session.http.post.call_args.kwargs["json"],
                         {"access_token": "old-token", "refresh_token": "old-refresh"})
        self.assertEqual(self.session.http.request.call_args.kwargs["headers"]["Authorization"], "Bearer new-token")
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved["refresh_token"], "new-refresh")
        self.assertEqual(AmisAppSession(state_path=self.path).state["token"], "new-token")

    def test_rejected_refresh_preserves_previous_state(self):
        self.session.save()
        previous = self.path.read_bytes()
        self.session.http.request.return_value = self.response(401)
        self.session.http.post.return_value = self.response(200, {"Success": False})
        with self.assertRaises(ValueError):
            self.session.request("GET", self.url)
        self.assertEqual(self.path.read_bytes(), previous)

    def test_missing_refresh_does_not_send_empty_credentials(self):
        self.session.state["refresh_token"] = ""
        self.session.http.request.return_value = self.response(401)
        with self.assertRaises(ValueError):
            self.session.request("GET", self.url)
        self.session.http.post.assert_not_called()

    def test_retry_is_bounded(self):
        self.session.http.request.return_value = self.response(401)
        self.session.http.post.return_value = self.response(200, {"Success": True, "Data": {"token": "new"}})
        with self.assertRaises(ValueError):
            self.session.request("GET", self.url)
        self.assertEqual(self.session.http.request.call_count, 2)
        self.assertEqual(self.session.http.post.call_count, 1)

    def test_does_not_send_credentials_to_another_host(self):
        with self.assertRaises(ValueError):
            self.session.request("GET", "https://example.com/")
        self.session.http.request.assert_not_called()

    def test_import_rejects_undefined_company(self):
        with self.assertRaises(ValueError):
            self.session.import_state({"token": "token", "refresh_token": "refresh", "companycode": "undefined"})
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
