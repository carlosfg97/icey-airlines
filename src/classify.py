"""Map URLs to registrable domains and classify them.

Categories: airline_direct_target, airline_direct_other, ota_aggregator, other.
Run `python -m src.classify data/results.jsonl` to see domain counts and the
"other" domains that may need a manual look (add them to config/domains.yaml).
"""
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = ["airline_direct_target", "airline_direct_other", "ota_aggregator", "other"]
# Small list of two-part public suffixes so e.g. www.skyscanner.co.uk -> skyscanner.co.uk
TWO_PART_SUFFIXES = {
    "co.uk", "org.uk", "com.au", "co.nz", "co.jp", "co.in", "com.br", "com.mx",
    "com.sg", "com.hk", "com.tr", "co.za", "com.ar", "com.co", "co.kr",
}


def load_domains(path=None):
    path = Path(path) if path else ROOT / "config" / "domains.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def split_url(url):
    """Return (registrable_domain, path) or (None, "") if the URL is unusable."""
    if not url:
        return None, ""
    if "://" not in url:
        url = "https://" + url
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return None, ""
    if not host or "." not in host:
        return None, ""
    labels = host.split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in TWO_PART_SUFFIXES:
        domain = ".".join(labels[-3:])
    else:
        domain = ".".join(labels[-2:])
    return domain, parsed.path or ""


def registrable_domain(url):
    return split_url(url)[0]


def classify_url(url, airline_target, cfg):
    """Return (domain, category) for one URL, relative to the target airline."""
    domain, path = split_url(url)
    if domain is None:
        return None, "other"
    for rule in cfg.get("path_rules", []):
        if domain == rule["domain"] and path.startswith(rule["path_prefix"]):
            return domain, rule["category"]
    if domain in cfg["airlines"].get(airline_target, []):
        return domain, "airline_direct_target"
    if domain in cfg["other_airlines"]:
        return domain, "airline_direct_other"
    if domain in cfg["ota_aggregator"]:
        return domain, "ota_aggregator"
    return domain, "other"


def classify_urls(urls, airline_target, cfg):
    return [classify_url(u, airline_target, cfg) for u in urls]


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else ROOT / "data" / "results.jsonl"
    cfg = load_domains()
    cats, domains, other = Counter(), Counter(), Counter()
    rows = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows += 1
        for url in row.get("cited_urls", []):
            domain, cat = classify_url(url, row["airline_target"], cfg)
            cats[cat] += 1
            domains[(domain, cat)] += 1
            if cat == "other":
                other[domain] += 1
    print(f"{rows} rows; cited URL categories: {dict(cats)}")
    print("\nTop cited domains:")
    for (d, c), n in domains.most_common(20):
        print(f"  {n:4d}  {d}  [{c}]")
    print("\nDomains classified 'other' (review; add to config/domains.yaml if needed):")
    for d, n in other.most_common(30):
        print(f"  {n:4d}  {d}")


if __name__ == "__main__":
    main(sys.argv)
