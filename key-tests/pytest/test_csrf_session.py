from unittest.mock import patch

from tests import BaseTestCase


class TestCSRFForLoggedInUser(BaseTestCase):
    def setUp(self):
        # Same switch tests/test_csrf.py uses: CSRF enforcement is wired up at create_app().
        with patch("redash.settings.ENFORCE_CSRF", True):
            super().setUp()

    def test_anonymous_post_is_rejected(self):
        # control: enforcement is really on
        rv = self.post_request("/login", data={"email": "a@example.com", "password": "x"}, org=self.factory.org)
        self.assertEqual(rv.status_code, 400)

    def test_session_user_post_without_token_is_rejected(self):
        # A browser session (cookie) user posts a state-changing request without any CSRF token.
        ds = self.factory.create_data_source()
        rv = self.make_request(
            "post",
            "/api/queries",
            data={"name": "csrf", "query": "select 1", "data_source_id": ds.id, "schedule": None},
        )
        self.assertEqual(rv.status_code, 400, rv.get_data(as_text=True)[:200])
