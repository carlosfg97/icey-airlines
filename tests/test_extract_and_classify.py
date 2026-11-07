import json
import unittest
from pathlib import Path

from src.classify import classify_url, load_domains, registrable_domain
from src.providers import extract_anthropic, extract_openai, parse_self_reported

FIX = Path(__file__).parent / "fixtures"
CFG = load_domains()


def load(name):
    return json.loads((FIX / name).read_text())


class AnthropicExtract(unittest.TestCase):
    def test_fields(self):
        out = extract_anthropic(load("anthropic_sample.json"))
        self.assertEqual(out["search_queries"][0], "Alaska Airlines SEA to ANC price November 13 2026 basic economy")
        self.assertEqual(len(out["search_queries"]), 2)
        self.assertEqual(len(out["result_urls"]), 3)
        self.assertEqual(out["cited_urls"], [
            "https://www.kayak.com/flight-routes/Seattle-SEA/Anchorage-ANC",
            "https://www.alaskaair.com/en/flights/seattle-to-anchorage"])  # deduped, order kept
        self.assertEqual(out["search_errors"], ["unavailable"])
        self.assertEqual(out["self_reported_sources"], "kayak.com, alaskaair.com")


class OpenAIExtract(unittest.TestCase):
    def test_fields(self):
        out = extract_openai(load("openai_sample.json"))
        self.assertEqual(out["search_queries"], ["Delta ATL to MCO price"])
        self.assertEqual(len(out["result_urls"]), 2)  # deduped
        self.assertEqual(len(out["cited_urls"]), 2)
        self.assertEqual(out["self_reported_sources"], "expedia.com, delta.com")  # bold markers tolerated


class SelfReported(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(parse_self_reported("no sources line here"))
        self.assertEqual(parse_self_reported("a\nSources: x.com"), "x.com")


class Classify(unittest.TestCase):
    def test_domains(self):
        self.assertEqual(registrable_domain("https://www.alaskaair.com/a/b"), "alaskaair.com")
        self.assertEqual(registrable_domain("https://www.skyscanner.co.uk/x"), "skyscanner.co.uk")
        self.assertIsNone(registrable_domain("not a url"))

    def test_categories(self):
        c = lambda u, a: classify_url(u, a, CFG)[1]
        self.assertEqual(c("https://www.alaskaair.com/x", "alaska"), "airline_direct_target")
        self.assertEqual(c("https://www.hawaiianairlines.com/x", "alaska"), "airline_direct_target")
        self.assertEqual(c("https://www.alaskaair.com/x", "delta"), "airline_direct_other")
        self.assertEqual(c("https://www.delta.com/x", "delta"), "airline_direct_target")
        self.assertEqual(c("https://www.southwest.com/x", "southwest"), "airline_direct_target")
        self.assertEqual(c("https://www.kayak.com/x", "alaska"), "ota_aggregator")
        self.assertEqual(c("https://www.google.com/travel/flights", "delta"), "ota_aggregator")
        self.assertEqual(c("https://www.google.com/search?q=x", "delta"), "other")
        self.assertEqual(c("https://en.wikipedia.org/wiki/X", "delta"), "other")
        self.assertEqual(c("https://www.flightconnections.com/x", "delta"), "ota_aggregator")
        self.assertEqual(c("https://www.flightsfrom.com/x", "delta"), "ota_aggregator")


if __name__ == "__main__":
    unittest.main()
