import json
import unittest
from urllib.error import URLError

import openai_code_interpreter as ci


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class CaptureOpener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None
        self.timeout = None

    def __call__(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return FakeResponse(self.payload)


class CodeInterpreterTests(unittest.TestCase):
    def enabled_env(self, **extra):
        values = {
            "PORTAL_CODE_INTERPRETER_ENABLED": "true",
            "PORTAL_CODE_INTERPRETER_MODEL": "gpt-5.4-mini",
            "PORTAL_CODE_INTERPRETER_MEMORY": "1g",
            "PORTAL_CODE_INTERPRETER_TIMEOUT_SECONDS": "180",
            "OPENAI_API_KEY": "test-secret-key",
        }
        values.update(extra)
        return values

    def test_default_is_disabled_and_public_status_never_exposes_key(self):
        status = ci.public_status({})
        self.assertFalse(status["enabled"])
        self.assertFalse(status["configured"])
        self.assertFalse(status["network_access"])
        self.assertFalse(status["store_responses"])
        self.assertNotIn("api_key", status)

        settings = ci.load_settings(self.enabled_env())
        self.assertNotIn("test-secret-key", repr(settings))

    def test_invalid_configuration_is_fail_closed(self):
        for value in ("yes", "1", ""):
            with self.subTest(enabled=value), self.assertRaises(ValueError):
                ci.load_settings({"PORTAL_CODE_INTERPRETER_ENABLED": value})
        for memory in ("2g", "0g", "bad"):
            with self.subTest(memory=memory), self.assertRaises(ValueError):
                ci.load_settings(self.enabled_env(PORTAL_CODE_INTERPRETER_MEMORY=memory))
        for model in ("", "bad model", "../model"):
            with self.subTest(model=model), self.assertRaises(ValueError):
                ci.load_settings(self.enabled_env(PORTAL_CODE_INTERPRETER_MODEL=model))

    def test_request_uses_responses_api_sandbox_no_network_and_no_storage(self):
        opener = CaptureOpener({
            "id": "resp_test",
            "model": "gpt-5.4-mini-2026-03-17",
            "output": [
                {"type": "code_interpreter_call", "container_id": "cntr_test"},
                {"type": "message", "content": [
                    {"type": "output_text", "text": "Среднее значение: 12.5"}
                ]},
            ],
        })
        result = ci.run("Посчитай среднее: 10, 15", self.enabled_env(), opener=opener)
        self.assertEqual(result["text"], "Среднее значение: 12.5")
        self.assertEqual(result["response_id"], "resp_test")
        self.assertEqual(result["container_id"], "cntr_test")
        self.assertEqual(opener.timeout, 180)
        self.assertEqual(opener.request.full_url, ci.RESPONSES_URL)
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer test-secret-key")

        payload = json.loads(opener.request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "gpt-5.4-mini")
        self.assertFalse(payload["store"])
        self.assertEqual(payload["tool_choice"], "required")
        tool = payload["tools"][0]
        self.assertEqual(tool["type"], "code_interpreter")
        self.assertEqual(tool["container"]["type"], "auto")
        self.assertEqual(tool["container"]["memory_limit"], "1g")
        self.assertEqual(tool["container"]["network_policy"], {"type": "disabled"})
        self.assertEqual(payload["input"], "Посчитай среднее: 10, 15")

    def test_disabled_missing_key_prompt_limits_and_remote_errors_are_sanitized(self):
        with self.assertRaises(ci.CodeInterpreterUnavailable):
            ci.run("x", {}, opener=lambda *a, **k: None)
        missing = self.enabled_env(OPENAI_API_KEY="")
        with self.assertRaises(ci.CodeInterpreterUnavailable):
            ci.run("x", missing, opener=lambda *a, **k: None)
        with self.assertRaises(ValueError):
            ci.run(" ", self.enabled_env(), opener=lambda *a, **k: None)
        with self.assertRaises(ValueError):
            ci.run("x" * (ci.MAX_PROMPT_CHARS + 1), self.enabled_env(),
                   opener=lambda *a, **k: None)

        def offline(*_args, **_kwargs):
            raise URLError("Bearer test-secret-key must never surface")

        with self.assertRaises(ci.CodeInterpreterRemoteError) as captured:
            ci.run("2+2", self.enabled_env(), opener=offline)
        self.assertNotIn("test-secret-key", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
