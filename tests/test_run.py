import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from src import run


class Batch(unittest.TestCase):
    def setUp(self):
        self.settings, self.routes = run.load_config(run.ROOT / "config")

    def test_batch_shape_and_determinism(self):
        a = run.build_batch(5, date(2026, 11, 7), self.settings, self.routes)
        b = run.build_batch(5, date(2026, 11, 7), self.settings, self.routes)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 36)  # 3 airlines x 3 routes x 2 directions x 2 providers
        self.assertLessEqual(len(a), self.settings["max_calls_per_run"])

    def test_prompt_never_names_airline_in_base_variant(self):
        for t in run.build_batch(3, date(2026, 11, 7), self.settings, self.routes):
            for name in ("Alaska", "Delta", "Southwest"):
                self.assertNotIn(name, t["prompt_text"])
            self.assertIn("SOURCES:", t["prompt_text"])

    def test_same_variables_across_provider_and_direction(self):
        tasks = run.build_batch(7, date(2026, 11, 7), self.settings, self.routes)
        first = [t for t in tasks if t["airline_target"] == "alaska"][:4]
        self.assertEqual({(t["booking_window"], t["fare_type"], t["add_on"], t["travel_date"]) for t in first}.__len__(), 1)
        self.assertEqual({t["provider"] for t in first}, {"anthropic", "openai"})
        self.assertEqual({t["direction"] for t in first}, {"outbound", "return"})

    def test_first_12_calls_cover_everything(self):  # what a --limit 12 test run exercises
        first = run.build_batch(0, date(2026, 11, 7), self.settings, self.routes)[:12]
        self.assertEqual({t["airline_target"] for t in first}, {"alaska", "delta", "southwest"})
        self.assertEqual({t["provider"] for t in first}, {"anthropic", "openai"})


class Execute(unittest.TestCase):
    def setUp(self):
        self.settings, self.routes = run.load_config(run.ROOT / "config")
        self.task = run.build_batch(1, date(2026, 11, 7), self.settings, self.routes)[0]
        self.meta = {"run_id": "x", "run_number": 1, "is_test": False, "timestamp_utc": "t"}

    def test_failure_is_captured_and_key_scrubbed(self):
        secret = "sk-ant-SECRETSECRET123"
        env = {"ANTHROPIC_API_KEY": secret}
        boom = mock.Mock(side_effect=RuntimeError(f"401 bad key {secret}"))
        with mock.patch.dict(run.CALLERS, {self.task["provider"]: boom}):
            self.settings["max_retries"] = 0
            row = run.execute(self.task, {self.task["provider"]: object()}, self.settings, self.meta, env, None)
        self.assertIn("RuntimeError", row["error"])
        self.assertNotIn("SECRETSECRET", row["error"])
        self.assertIsNone(row["response_text"])

    def test_success_row(self):
        fake = mock.Mock(return_value={"search_queries": ["q"], "result_urls": ["https://a.com"],
                                       "cited_urls": ["https://a.com"], "response_text": "hi",
                                       "self_reported_sources": "a.com", "input_tokens": 1, "output_tokens": 2,
                                       "raw": {}})
        with mock.patch.dict(run.CALLERS, {self.task["provider"]: fake}):
            row = run.execute(self.task, {self.task["provider"]: object()}, self.settings, self.meta, {}, None)
        self.assertIsNone(row["error"])
        self.assertEqual(row["cited_urls"], ["https://a.com"])
        self.assertIn("latency_ms", row)
        json.dumps(row)  # must be serialisable

    def test_missing_keys_exit_code(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(run.main(["--limit", "2"]), 2)


if __name__ == "__main__":
    unittest.main()
