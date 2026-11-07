import math
import unittest

from src.analyze import build_frame, compare_airlines, self_reported_domains, two_prop_ztest, wilson
from src.classify import load_domains

CFG = load_domains()


def row(airline, provider, cited, seen=None, text="", error=None, sources=None):
    return {"run_number": 1, "timestamp_utc": "t", "provider": provider, "model": "m", "airline_target": airline,
            "route_id": "A-B", "direction": "outbound", "booking_window": "next_week", "fare_type": "basic_economy",
            "add_on": "none", "cited_urls": cited, "result_urls": seen or cited, "response_text": text,
            "self_reported_sources": sources, "error": error}


class Stats(unittest.TestCase):
    def test_ztest_known_value(self):
        z, p = two_prop_ztest(30, 100, 50, 100)  # 0.30 vs 0.50
        self.assertAlmostEqual(z, -2.88675, places=4)
        self.assertAlmostEqual(p, 0.003892, places=5)

    def test_ztest_degenerate(self):
        self.assertTrue(math.isnan(two_prop_ztest(5, 5, 5, 5)[0]))
        self.assertTrue(math.isnan(two_prop_ztest(0, 0, 1, 2)[0]))

    def test_wilson_bounds(self):
        lo, hi = wilson(5, 10)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)
        self.assertTrue(0 <= lo <= hi <= 1)


class Frame(unittest.TestCase):
    def test_flags_and_errors(self):
        rows = [
            row("alaska", "anthropic", ["https://www.alaskaair.com/x", "https://www.kayak.com/y"],
                text="Book on Alaska Airlines", sources="alaskaair.com, Kayak (kayak.com)"),
            row("delta", "openai", ["https://www.expedia.com/z"], text="United has fares"),
            row("delta", "openai", [], error="boom"),
        ]
        df = build_frame(rows, CFG)
        self.assertEqual(len(df), 2)  # failed call dropped
        a, d = df.iloc[0], df.iloc[1]
        self.assertTrue(a.cited_target and a.cited_ota)
        self.assertEqual(a.primary_source, "airline_direct_target")
        self.assertFalse(a.absent)
        self.assertEqual(a.selfreport_in_used, 1.0)
        self.assertTrue(d.absent and d.cited_ota and not d.cited_target)

    def test_compare_airlines(self):
        rows = [row("alaska", "openai", ["https://www.kayak.com/a"]) for _ in range(3)] + \
               [row("delta", "openai", ["https://www.delta.com/a"]) for _ in range(3)]
        res = compare_airlines(build_frame(rows, CFG), "cited_ota")
        allrow = res[res.provider == "all"].iloc[0]
        self.assertEqual((allrow.share_a, allrow.share_b), (1.0, 0.0))

    def test_self_reported_domains(self):
        self.assertEqual(self_reported_domains("KAYAK (kayak.com); Trip.com, www.aa.com"),
                         {"kayak.com", "trip.com", "aa.com"})


if __name__ == "__main__":
    unittest.main()
