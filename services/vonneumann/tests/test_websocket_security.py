"""Real in-process WebSocket handshake and isolated event-delivery tests."""

from __future__ import annotations

import time
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import A1, A2, B1, USER_A, USER_B, ORIGIN, OfflineTestMixin, deny_network
from tests.test_http_security import HTTPTestBase, app_module

with deny_network():
    from fastapi import HTTPException
    from starlette.websockets import WebSocketDisconnect
    from vonneumann.core.types import EventType, ProbeEvent
    from vonneumann.server.auth import VerifiedUser
    from vonneumann.server import websocket as ws_module


class WebSocketSecurityTests(HTTPTestBase):
    def setUp(self):
        super().setUp()
        self.ws_manager = ws_module.ConnectionManager()
        self.offline_stack.enter_context(patch.object(app_module, "ws_manager", self.ws_manager))
        self.offline_stack.enter_context(patch.object(app_module, "VN_ALLOWED_ORIGINS", (ORIGIN,)))
        self.offline_stack.enter_context(patch.object(app_module.logging, "basicConfig"))

        async def verify(token):
            if token not in ("user-a-token", "user-b-token"):
                raise HTTPException(status_code=401, detail="Invalid access token")
            return VerifiedUser(USER_A if token == "user-a-token" else USER_B, int(time.time()) + 3600)

        self.verifier = self.offline_stack.enter_context(patch.object(
            app_module, "verify_access_token", new=AsyncMock(side_effect=verify)))
        self.offline_stack.enter_context(self.client)

    def connect(self, **kwargs):
        return self.client.websocket_connect("/ws", headers={"origin": ORIGIN}, **kwargs)

    def authenticate(self, ws, token="user-a-token", user_id=USER_A):
        ws.send_json({"type": "auth", "access_token": token})
        message = ws.receive_json()
        self.assertEqual(message["type"], "auth_ok")
        self.assertEqual(message["data"]["user_id"], user_id)
        self.assertGreater(message["data"]["expires_at"], time.time())

    def broadcast(self, user_id, message):
        self.client.portal.call(self.ws_manager.broadcast_to_user, user_id, message)

    def test_missing_and_untrusted_origin_rejected_before_verification(self):
        for headers in ({}, {"origin": "https://attacker.example"},
                        {"origin": ORIGIN + ".attacker.example"}):
            with self.subTest(headers=headers), self.assertRaises(WebSocketDisconnect) as caught:
                with self.client.websocket_connect("/ws", headers=headers):
                    self.fail("Untrusted origin was accepted")
            self.assertEqual(caught.exception.code, 4403)
        self.verifier.assert_not_awaited()
        self.assertEqual(self.ws_manager.client_count, 0)

    def test_invalid_auth_frames_never_register_or_invoke_provider(self):
        frames = ("not-json", "[]", "{}", '"string"',
                  '{"type":"command","data":{"action":"stop"}}',
                  '{"type":"auth","access_token":123}',
                  '{"type":"auth","access_token":"user-a-token","user_id":"spoof"}',
                  '{"type":"auth","type":"auth","access_token":"user-a-token"}',
                  '{"type":"auth","access_token":"user-a-token","access_token":"user-b-token"}',
                  "x" * (app_module.WS_AUTH_MAX_BYTES + 1))
        for frame in frames:
            with self.subTest(frame=frame[:30]):
                with self.connect() as ws:
                    ws.send_text(frame)
                    with self.assertRaises(WebSocketDisconnect) as caught:
                        ws.receive_json()
                    self.assertEqual(caught.exception.code, 4400)
        self.verifier.assert_not_awaited()
        self.assertEqual(self.ws_manager.client_count, 0)
        self.assert_no_controls()

    def test_binary_auth_frame_is_rejected(self):
        with self.connect() as ws:
            ws.send_bytes(b"binary-is-not-the-auth-protocol")
            with self.assertRaises(WebSocketDisconnect) as caught:
                ws.receive_json()
        self.assertEqual(caught.exception.code, 4400)
        self.verifier.assert_not_awaited()

    def test_auth_deadline_closes_unverified_connection(self):
        with patch.object(app_module, "WS_AUTH_TIMEOUT_SECONDS", 0.01):
            with self.connect() as ws:
                with self.assertRaises(WebSocketDisconnect) as caught:
                    ws.receive_json()
        self.assertEqual(caught.exception.code, 4408)
        self.assertEqual(self.ws_manager.client_count, 0)
        self.verifier.assert_not_awaited()

    def test_bad_token_and_provider_outage_have_distinct_close_codes(self):
        for status, close_code in ((401, 4401), (503, 1013)):
            with self.subTest(status=status):
                self.verifier.side_effect = HTTPException(status_code=status, detail="sanitized error")
                with self.connect() as ws:
                    ws.send_json({"type": "auth", "access_token": "invalid-token"})
                    with self.assertRaises(WebSocketDisconnect) as caught:
                        ws.receive_json()
                self.assertEqual(caught.exception.code, close_code)
                self.assertEqual(self.ws_manager.client_count, 0)

    def test_application_events_cannot_precede_authentication(self):
        with self.connect() as ws:
            self.assertEqual(self.ws_manager.client_count, 0)
            self.broadcast(USER_A, {"type": "probe_update", "colony_id": A1, "marker": "before-auth"})
            self.authenticate(ws)
            self.broadcast(USER_A, {"type": "probe_update", "colony_id": A1, "marker": "after-auth"})
            self.assertEqual(ws.receive_json()["marker"], "after-auth")
        self.assertEqual(self.ws_manager.client_count, 0)

    def test_two_users_receive_only_their_own_colony_events(self):
        with self.connect() as a_socket, self.connect() as b_socket:
            self.authenticate(a_socket)
            self.authenticate(b_socket, "user-b-token", USER_B)
            a_event = {"type": "probe_update", "colony_id": A2, "marker": "owner-a"}
            b_event = {"type": "probe_update", "colony_id": B1, "marker": "owner-b"}
            self.broadcast(USER_A, a_event)
            self.broadcast(USER_B, b_event)
            self.assertEqual(a_socket.receive_json(), a_event)
            self.assertEqual(b_socket.receive_json(), b_event)
        self.assertEqual(self.ws_manager.client_count, 0)

    def test_every_websocket_command_is_read_only_even_for_own_colony(self):
        with self.connect() as ws:
            self.authenticate(ws)
            for colony_id in (None, A1, A2, B1):
                for action in ("pause", "resume", "stop"):
                    with self.subTest(colony=colony_id, action=action):
                        ws.send_json({"type": "command", "data": {
                            "action": action, "colony_id": colony_id}})
                        reply = ws.receive_json()
                        self.assertEqual(reply["type"], "error")
                        self.assertEqual(reply["data"]["code"], "read_only")
        self.assert_no_controls()

    def test_connection_expires_without_waiting_for_another_message(self):
        self.verifier.side_effect = None
        self.verifier.return_value = VerifiedUser(USER_A, int(time.time()) + 1)
        with self.connect() as ws:
            self.authenticate(ws)
            with self.assertRaises(WebSocketDisconnect) as caught:
                ws.receive_json()
        self.assertEqual(caught.exception.code, 4401)
        self.assertEqual(self.ws_manager.client_count, 0)

    def test_already_expired_identity_is_not_acknowledged_or_registered(self):
        self.verifier.side_effect = None
        self.verifier.return_value = VerifiedUser(USER_A, int(time.time()) - 1)
        with self.connect() as ws:
            ws.send_json({"type": "auth", "access_token": "user-a-token"})
            with self.assertRaises(WebSocketDisconnect) as caught:
                ws.receive_json()
        self.assertEqual(caught.exception.code, 4401)
        self.assertEqual(self.ws_manager.client_count, 0)


class RecordingSocket:
    def __init__(self, fail=False):
        self.messages = []
        self.closes = []
        self.fail = fail

    async def send_text(self, data):
        if self.fail:
            raise RuntimeError("test transport failure")
        self.messages.append(data)

    async def close(self, code):
        self.closes.append(code)


class EventAuthorizationTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    async def test_dual_handler_uses_trusted_owner_and_colony_not_event_payload(self):
        manager = ws_module.ConnectionManager()
        a_socket, b_socket = RecordingSocket(), RecordingSocket()
        manager.register(a_socket, VerifiedUser(USER_A, int(time.time()) + 3600))
        manager.register(b_socket, VerifiedUser(USER_B, int(time.time()) + 3600))
        persister = AsyncMock()
        event = ProbeEvent(EventType.PROBE_UPDATE, "probe-1", {
            "user_id": USER_B, "colony_id": B1, "state": "OBSERVING"})
        with patch.object(app_module, "ws_manager", manager):
            handler = app_module._make_dual_handler(A1, USER_A, persister)
            await handler(event)
        persister.handle.assert_awaited_once_with(event)
        self.assertEqual(b_socket.messages, [])
        self.assertEqual(len(a_socket.messages), 1)
        import json
        self.assertEqual(json.loads(a_socket.messages[0])["colony_id"], A1)

    async def test_expired_connection_never_receives_broadcast(self):
        manager = ws_module.ConnectionManager()
        expired, active = RecordingSocket(), RecordingSocket()
        manager.register(expired, VerifiedUser(USER_A, int(time.time()) - 1))
        manager.register(active, VerifiedUser(USER_A, int(time.time()) + 3600))
        await manager.broadcast_to_user(USER_A, {"type": "probe_update", "colony_id": A1})
        self.assertEqual(expired.messages, [])
        self.assertEqual(expired.closes, [4401])
        self.assertEqual(len(active.messages), 1)
        self.assertEqual(manager.client_count, 1)

    async def test_failed_socket_does_not_prevent_other_owners_delivery(self):
        manager = ws_module.ConnectionManager()
        failed, active = RecordingSocket(fail=True), RecordingSocket()
        for socket in (failed, active):
            manager.register(socket, VerifiedUser(USER_A, int(time.time()) + 3600))
        await manager.broadcast_to_user(USER_A, {"type": "probe_update", "colony_id": A1})
        self.assertEqual(len(active.messages), 1)
        self.assertEqual(failed.closes, [1013])
        self.assertEqual(manager.client_count, 1)


if __name__ == "__main__":
    unittest.main()
