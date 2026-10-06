import unittest

import observability


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.events = []
        self.closed = False

    def capture(self, event, properties=None):
        self.events.append((event, dict(properties or {})))

    def shutdown(self):
        self.closed = True


class ObservabilityTests(unittest.TestCase):
    def test_disabled_without_project_key(self):
        obs = observability.PortalObservability.from_env({}, build_id="B", environment="test")
        self.assertFalse(obs.enabled)
        self.assertFalse(obs.server_started())

    def test_rejects_non_posthog_host(self):
        env = {"PORTAL_POSTHOG_PROJECT_KEY": "phc_test", "PORTAL_POSTHOG_HOST": "https://example.invalid"}
        obs = observability.PortalObservability.from_env(env, client_factory=FakeClient)
        self.assertFalse(obs.enabled)

    def test_personless_privacy_properties_and_eu_host(self):
        created = []
        def factory(**kwargs):
            client = FakeClient(**kwargs)
            created.append(client)
            return client
        env = {
            "PORTAL_POSTHOG_PROJECT_KEY": "phc_test",
            "PORTAL_POSTHOG_HOST": "https://eu.i.posthog.com",
            "PORTAL_POSTHOG_SLOW_MS": "1500",
        }
        obs = observability.PortalObservability.from_env(
            env, build_id="PORTAL Server · test", environment="test", client_factory=factory
        )
        self.assertTrue(obs.enabled)
        self.assertEqual(created[0].kwargs["host"], "https://eu.i.posthog.com")
        self.assertTrue(created[0].kwargs["disable_geoip"])
        obs.server_started()
        event, props = created[0].events[-1]
        self.assertEqual(event, "portal_server_started")
        self.assertIs(props["$process_person_profile"], False)
        self.assertIs(props["$geoip_disable"], True)
        self.assertNotIn("distinct_id", props)

    def test_only_error_or_slow_requests_are_captured(self):
        client = FakeClient()
        obs = observability.PortalObservability(client, build_id="B", environment="prod", slow_ms=1000)
        self.assertFalse(obs.request_result(method="GET", route="/api/ping", status=200, duration_ms=15))
        self.assertTrue(obs.request_result(method="GET", route="/api/ready", status=200, duration_ms=1200))
        self.assertEqual(client.events[-1][0], "portal_server_slow_request")
        self.assertTrue(obs.request_result(
            method="POST", route="/api/v3/work", status=500, duration_ms=20, exception_type="RuntimeError"
        ))
        event, props = client.events[-1]
        self.assertEqual(event, "portal_server_error")
        self.assertEqual(props["exception_type"], "RuntimeError")
        forbidden = {"token", "company_id", "user_id", "request_body", "query", "message"}
        self.assertTrue(forbidden.isdisjoint(props))

    def test_shutdown_is_fail_open(self):
        client = FakeClient()
        obs = observability.PortalObservability(client)
        obs.shutdown()
        self.assertTrue(client.closed)


if __name__ == "__main__":
    unittest.main()
