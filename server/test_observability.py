import unittest
from unittest.mock import patch

import observability


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.events = []
        self.closed = False

    def capture(self, event, *, distinct_id=None, properties=None):
        self.events.append((distinct_id, event, dict(properties or {})))

    def shutdown(self):
        self.closed = True


class BrokenClient(FakeClient):
    def capture(self, *args, **kwargs):
        raise OSError("secret-bearing network error")


class ObservabilityTests(unittest.TestCase):
    def test_disabled_by_default(self):
        obs = observability.PortalObservability.from_env({}, build_id="B", environment="test",
                                                        client_factory=lambda **kw: self.fail("must stay off"))
        self.assertFalse(obs.enabled)
        self.assertFalse(obs.server_started())
        self.assertFalse(obs.request_result(method="GET", route="/api/ping", status=500, duration_ms=1))

    def test_host_allowlist_and_sdk_initialization_fail_quiet(self):
        env = {"PORTAL_POSTHOG_PROJECT_KEY": "phc_test", "PORTAL_POSTHOG_HOST": "https://example.invalid"}
        obs = observability.PortalObservability.from_env(env, client_factory=lambda **kw: self.fail("untrusted host"))
        self.assertFalse(obs.enabled)
        env["PORTAL_POSTHOG_HOST"] = "https://eu.i.posthog.com/path?secret=1"
        self.assertFalse(observability.PortalObservability.from_env(env, client_factory=FakeClient).enabled)
        env["PORTAL_POSTHOG_HOST"] = "https://eu.i.posthog.com"
        obs = observability.PortalObservability.from_env(env, client_factory=lambda **kw: (_ for _ in ()).throw(RuntimeError("secret")))
        self.assertFalse(obs.enabled)

    def test_uses_personless_service_events_and_official_sdk_options(self):
        made = []
        def factory(**kwargs):
            client = FakeClient(**kwargs)
            made.append(client)
            return client
        obs = observability.PortalObservability.from_env(
            {"PORTAL_POSTHOG_PROJECT_KEY": "phc_test"}, build_id="PORTAL-4.8.0", environment="production",
            client_factory=factory,
        )
        self.assertTrue(obs.enabled)
        self.assertEqual(made[0].kwargs["host"], "https://eu.i.posthog.com")
        self.assertTrue(made[0].kwargs["disable_geoip"])
        self.assertTrue(made[0].kwargs["is_server"])
        self.assertNotIn("enable_exception_autocapture", made[0].kwargs)
        self.assertTrue(obs.server_started())
        distinct_id, event, props = made[0].events[-1]
        self.assertEqual((distinct_id, event), ("portal-server", "portal_server_started"))
        self.assertIs(props["$process_person_profile"], False)
        self.assertIs(props["$geoip_disable"], True)
        self.assertEqual(props["build"], "PORTAL-4.8.0")

    def test_error_capture_redacts_url_identifiers_and_payload(self):
        client = FakeClient()
        obs = observability.PortalObservability(client, build_id="build-4", environment="production")
        self.assertTrue(obs.request_result(
            method="POST", route="/api/v3/work/123", status=503, duration_ms=48,
            exception_type=RuntimeError,
        ))
        distinct_id, event, props = client.events[-1]
        self.assertEqual(distinct_id, "portal-server")
        self.assertEqual(event, "portal_server_error")
        self.assertEqual(props["route"], "/api/v3/work/{id}")
        self.assertEqual(props["status_class"], "5xx")
        self.assertEqual(props["exception_type"], "RuntimeError")
        self.assertNotIn("distinct_id", props)
        forbidden = ["tenant-991", "alice@example.com", "secret-token", "client-name", "filename.xlsx", "payload-value"]
        serialized = repr((distinct_id, event, props))
        self.assertFalse(any(value in serialized for value in forbidden))
        self.assertTrue(obs.request_result(method="GET", route="/api/ping?token=secret-token", status=500, duration_ms=1))
        self.assertEqual(client.events[-1][2]["route"], "unknown")
        self.assertNotIn("secret-token", repr(client.events[-1]))

    def test_untrusted_route_and_method_collapse_to_coarse_labels(self):
        client = FakeClient()
        obs = observability.PortalObservability(client)
        obs.request_result(method="DELETE", route="https://host/private/alice.xlsx?token=secret", status=500,
                           duration_ms=2, exception_type=ValueError)
        props = client.events[-1][2]
        self.assertEqual(props["method"], "OTHER")
        self.assertEqual(props["route"], "unknown")
        self.assertNotIn("alice.xlsx", repr(props))
        self.assertNotIn("secret", repr(props))

    def test_capture_and_shutdown_network_errors_are_fail_quiet(self):
        obs = observability.PortalObservability(BrokenClient())
        self.assertFalse(obs.server_started())
        self.assertFalse(obs.request_result(method="GET", route="/api/ready", status=500, duration_ms=2))
        self.assertIsNone(obs.shutdown())

    def test_request_error_response_behavior_is_unchanged(self):
        import portal_app_server as app
        handler = app.Handler.__new__(app.Handler)
        handler.path = "/api/ping?token=secret"
        responses = []
        handler.route = lambda method: (_ for _ in ()).throw(ValueError("existing validation error"))
        handler.error_json = lambda message, status: (setattr(handler, "response_status", status), responses.append((message, status)))
        with patch.object(app, "OBSERVABILITY", observability.PortalObservability()):
            handler.do_GET()
        self.assertEqual(len(responses), 1)
        self.assertEqual(str(responses[0][0]), "existing validation error")
        self.assertEqual(responses[0][1], 400)


if __name__ == "__main__":
    unittest.main()
