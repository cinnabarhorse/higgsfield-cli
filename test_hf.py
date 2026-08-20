import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import hf


class Response:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload or {}
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload


class HiggsFieldClientTests(unittest.TestCase):
    def test_clerk_post_uses_current_frontend_protocol(self):
        post = Mock(return_value=Response())
        client = object.__new__(hf.HiggsFieldClient)
        client.session = SimpleNamespace(post=post)

        client._clerk_post("/v1/client/sign_ins", {"identifier": "user@example.com"})

        post.assert_called_once_with(
            f"{hf.CLERK_BASE}/v1/client/sign_ins",
            data={"identifier": "user@example.com"},
            params=hf.CLERK_QUERY,
            timeout=10,
        )

    def test_login_ignores_string_cookie_iteration(self):
        class StringCookies:
            def __iter__(self):
                return iter(["__client"])

            def get(self, *_args, **_kwargs):
                return None

        completed = Response({
            "response": {"id": "sign_in", "status": "complete"},
            "client": {"sessions": [{"id": "session", "user": {"id": "user"}}]},
        })
        client = object.__new__(hf.HiggsFieldClient)
        client.session = SimpleNamespace(cookies=StringCookies())
        client.jwt = None
        client.session_id = None
        client.user_id = None
        client.email = None
        client._warmup_cloudflare = Mock()
        client._clerk_init_client = Mock()
        client._clerk_post = Mock(return_value=completed)
        client._refresh_jwt = Mock(side_effect=lambda: setattr(client, "jwt", "jwt") or True)
        client._save_session = Mock()

        self.assertTrue(client.login("user@example.com", "password"))
        client._clerk_post.assert_called_once_with(
            "/v1/client/sign_ins",
            {"identifier": "user@example.com"},
        )
        saved = client._save_session.call_args.args[0]
        self.assertEqual(saved["allCookies"], [])

    def test_upload_finalization_keeps_required_flags(self):
        post = Mock(return_value=Response())
        client = object.__new__(hf.HiggsFieldClient)
        client.session = SimpleNamespace(post=post)
        client.jwt = "jwt"

        self.assertTrue(client._finalize_media_upload("media", "frame.png"))
        self.assertEqual(
            post.call_args.kwargs["json"],
            {
                "filename": "frame.png",
                "force_nsfw_check": False,
                "force_ip_check": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
