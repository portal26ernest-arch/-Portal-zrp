import unittest

import messenger_relay_auth as relay


class MessengerRelayAuthBackportTest(unittest.TestCase):
    def test_disabled_without_secret(self):
        env={"PORTAL_TELEGRAM_RELAY_REQUIRED":"0"}
        self.assertEqual(relay.relay_status(env),{"provider":"telegram","enabled":False,"required":False})

    def test_issue_validate_and_expire_scoped_ticket(self):
        env={
            "PORTAL_MESSENGER_RELAY_URL":"https://api.vart-portal.ru:9443",
            "PORTAL_MESSENGER_RELAY_SECRET":"x"*48,
            "PORTAL_MESSENGER_RELAY_TTL_SECONDS":"3600",
            "PORTAL_TELEGRAM_RELAY_REQUIRED":"0",
        }
        ticket=relay.issue_ticket(7,1,env,now=1000)
        self.assertTrue(ticket["enabled"])
        self.assertEqual(ticket["provider"],"telegram")
        self.assertTrue(ticket["username"].startswith("v2.telegram.7.1."))
        valid=relay.validate_ticket(ticket["username"],ticket["password"],env["PORTAL_MESSENGER_RELAY_SECRET"],now=1100)
        self.assertEqual(valid["scope"],"telegram")
        self.assertIsNone(relay.validate_ticket(ticket["username"],ticket["password"],env["PORTAL_MESSENGER_RELAY_SECRET"],now=5001))

    def test_proxy_url_is_https_and_secret_never_returned(self):
        env={
            "PORTAL_MESSENGER_RELAY_URL":"https://api.vart-portal.ru:9443",
            "PORTAL_MESSENGER_RELAY_SECRET":"y"*48,
        }
        ticket=relay.issue_ticket(2,3,env,now=1000)
        self.assertEqual(ticket["proxy_url"],"https://api.vart-portal.ru:9443")
        self.assertNotIn("secret",ticket)
        with self.assertRaises(ValueError): relay.normalize_proxy_url("http://api.vart-portal.ru:9443")


if __name__=='__main__':
    unittest.main()
