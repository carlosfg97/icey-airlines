"""Build the hourly batch, call the APIs, append one JSON row per call.

  python -m src.run --dry-run                 # print prompts + rotation, no API calls, no keys needed
  python -m src.run --dry-run --run-number 5  # preview a specific run
  python -m src.run --check-rotation 72       # show how balanced the rotation is over 72 runs
  python -m src.run --test --limit 12         # real calls, flagged is_test, raw responses saved
  python -m src.run                           # the hourly run (what GitHub Actions executes)
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from itertools import product
from pathlib import Path

import yaml

from src.providers import CALLERS, make_clients, with_retries

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = ["next_week", "next_month", "holiday"]
FARES = ["basic_economy", "main_economy", "first_premium"]
ADDONS = ["none", "checked_bag", "seat_selection"]
FARE_PHRASE = {"basic_economy": "basic economy", "main_economy": "regular economy",
               "first_premium": "first class"}
ADDON_PHRASE = {"none": "with no extras", "checked_bag": "with one checked bag",
                "seat_selection": "with seat selection"}
FINAL_INSTRUCTION = "At the end, add one line starting with SOURCES: listing the websites you used."
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
COMBOS = list(product(WINDOWS, FARES, ADDONS))  # 27 combinations


def load_config(config_dir):
    d = Path(config_dir)
    with open(d / "settings.yaml") as f:
        settings = yaml.safe_load(f)
    with open(d / "routes.yaml") as f:
        routes = yaml.safe_load(f)
    return settings, routes


def travel_date(window, run_date, settings):
    if window == "holiday":
        return datetime.strptime(settings["holiday_date"], "%Y-%m-%d").date()
    return run_date + timedelta(days=settings["window_days"][window])


def fmt_date(d):
    return f"{d:%B} {d.day}, {d.year}"


def make_prompt(origin_city, dest_city, date, fare, addon, variant, airline_name):
    who = f" with {airline_name}" if variant == "named" else ""
    return (f"I want to fly{who} from {origin_city} to {dest_city} on {fmt_date(date)}, "
            f"{FARE_PHRASE[fare]}, {ADDON_PHRASE[addon]}. "
            f"Can you find me the price and where I can book it? {FINAL_INSTRUCTION}")


def variant_for(setting, run_number):
    """'base' / 'named' are fixed; 'alternate' gives even run numbers 'base' and odd ones 'named', so both
    variants keep accumulating side by side (a 2-batch dispatch always yields one of each)."""
    if setting == "alternate":
        return "named" if run_number % 2 else "base"
    return setting


def build_batch(run_number, run_date, settings, routes_cfg):
    """Deterministic batch for one run. Same variables for both directions and both providers.

    Rotation: each run takes `routes_per_airline_per_run` consecutive routes per airline
    (cycling through the list). Each (airline, slot) gets combo index
    (run*10 + airline*slots + slot) % 27; 10 is coprime with 27, so over 27 runs every
    (airline, slot) walks through all 27 window x fare x add-on combinations.
    """
    slots = settings["routes_per_airline_per_run"]
    airports = routes_cfg["airports"]
    variant = variant_for(settings["prompt_variant"], run_number)
    tasks = []
    for slot in range(slots):
        for a_idx, airline in enumerate(settings["airlines"]):
            route_list = routes_cfg["routes"][airline]
            a, b = route_list[(run_number * slots + slot) % len(route_list)]
            window, fare, addon = COMBOS[(run_number * 10 + a_idx * slots + slot) % len(COMBOS)]
            date = travel_date(window, run_date, settings)
            for direction, (o, d) in (("outbound", (a, b)), ("return", (b, a))):
                for provider in settings["providers"]:
                    tasks.append({
                        "provider": provider, "airline_target": airline,
                        "route_id": f"{a}-{b}", "origin": o, "destination": d, "direction": direction,
                        "booking_window": window, "travel_date": date.isoformat(),
                        "fare_type": fare, "add_on": addon,
                        "prompt_variant": variant,
                        "prompt_text": make_prompt(airports[o], airports[d], date, fare, addon,
                                                   variant,
                                                   routes_cfg["airline_names"][airline]),
                    })
    return tasks


def read_rows(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def next_run_number(rows):
    nums = [r["run_number"] for r in rows if not r.get("is_test")]
    return (max(nums) + 1) if nums else 1


def scrub(text, env):
    """Remove anything that looks like an API key from a string before it is logged or stored."""
    for name in KEY_ENV.values():
        if env.get(name):
            text = text.replace(env[name], "[REDACTED]")
    return re.sub(r"(sk-[A-Za-z0-9_\-\*\.]{6,}|sk-ant-[A-Za-z0-9_\-\*\.]+)", "[REDACTED]", text)


def execute(task, clients, settings, meta, env, raw_dir):
    start = time.monotonic()
    row = {**meta, **task, "model": settings[task["provider"]]["model"],
           "search_queries": [], "result_urls": [], "cited_urls": [], "self_reported_sources": None,
           "response_text": None, "input_tokens": None, "output_tokens": None, "error": None}
    try:
        out = with_retries(lambda: CALLERS[task["provider"]](clients[task["provider"]],
                                                              task["prompt_text"], settings),
                           settings["max_retries"])
        raw = out.pop("raw")
        row.update(out)
        if raw_dir is not None:
            name = f"{task['provider']}__{task['airline_target']}_{task['route_id']}_{task['direction']}.json"
            (raw_dir / name).write_text(json.dumps(raw, ensure_ascii=False, indent=1))
            row["raw_file"] = f"{raw_dir.name}/{name}"
    except Exception as e:  # one failure must not kill the run
        row["error"] = scrub(f"{type(e).__name__}: {e}", env)[:400]
    row["latency_ms"] = int((time.monotonic() - start) * 1000)
    return row


def print_dry_run(meta, tasks):
    print(f"DRY RUN  run_number={meta['run_number']}  run_id={meta['run_id']}  calls={len(tasks)}  "
          f"prompt_variant={tasks[0]['prompt_variant'] if tasks else '-'}  (no API calls)\n")
    for i, t in enumerate(tasks, 1):
        print(f"[{i:02d}] {t['provider']:9s} {t['airline_target']:9s} {t['origin']}->{t['destination']} "
              f"{t['booking_window']:10s} {t['fare_type']:13s} {t['add_on']:14s} {t['travel_date']}")
        print(f"     {t['prompt_text']}")
    print("\nCalls per provider x airline:", dict(Counter((t["provider"], t["airline_target"]) for t in tasks)))


def check_rotation(n_runs, run_date, settings, routes_cfg):
    counts = defaultdict(Counter)  # airline -> Counter of labels (counted per route-pair, not per call)
    combos = defaultdict(Counter)
    seen = set()
    for run in range(1, n_runs + 1):
        for t in build_batch(run, run_date, settings, routes_cfg):
            key = (run, t["airline_target"], t["route_id"], t["booking_window"], t["fare_type"], t["add_on"])
            if key in seen:
                continue
            seen.add(key)
            a = t["airline_target"]
            counts[a]["route:" + t["route_id"]] += 1
            counts[a]["window:" + t["booking_window"]] += 1
            counts[a]["fare:" + t["fare_type"]] += 1
            counts[a]["addon:" + t["add_on"]] += 1
            combos[a][(t["booking_window"], t["fare_type"], t["add_on"])] += 1
    print(f"Rotation over {n_runs} runs (one count per route-pair per run; each is queried in both directions "
          f"and by both providers):")
    for a, c in counts.items():
        print(f"\n{a}:")
        for prefix in ("window", "fare", "addon", "route"):
            items = {k.split(':', 1)[1]: v for k, v in sorted(c.items()) if k.startswith(prefix + ":")}
            print(f"  {prefix:7s} {items}")
        vals = [combos[a].get(c3, 0) for c3 in COMBOS]
        print(f"  27 combos: min={min(vals)} max={max(vals)} (per-combo counts)")


def run_batch(args, settings, routes_cfg, run_date, run_number):
    """Build and execute (or dry-run) one batch. Returns an exit code (0 ok, 1 all failed, 2 missing keys)."""
    now = datetime.now(timezone.utc)
    results_path = ROOT / settings["paths"]["results"]
    existing = read_rows(results_path)
    run_id = now.strftime("%Y%m%dT%H%M%SZ") + ("-test" if args.test else f"-r{run_number}")
    meta = {"run_id": run_id, "run_number": run_number, "is_test": args.test,
            "timestamp_utc": now.isoformat(timespec="seconds")}

    tasks = build_batch(run_number, run_date, settings, routes_cfg)

    spent = sum(1 for r in existing if not r.get("is_test"))
    cap = min(settings["max_calls_per_run"], args.limit or 10**9,
              max(settings["max_total_calls"] - spent, 0) if not args.test else 10**9)
    if len(tasks) > cap:
        print(f"Limiting batch from {len(tasks)} to {cap} calls "
              f"(max_calls_per_run={settings['max_calls_per_run']}, budget used={spent}/{settings['max_total_calls']}).")
        tasks = tasks[:cap]
    if not tasks:
        print("Nothing to run (budget exhausted?).")
        return 0

    if args.dry_run:
        print_dry_run(meta, tasks)
        return 0

    env = dict(os.environ)
    needed = sorted({t["provider"] for t in tasks})
    missing = [KEY_ENV[p] for p in needed if not env.get(KEY_ENV[p])]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)} (set them as repo secrets).", file=sys.stderr)
        return 2
    clients = make_clients(needed, env)

    raw_dir = None
    if settings["raw_responses"] == "all" or (settings["raw_responses"] == "test_only" and args.test):
        raw_dir = ROOT / settings["paths"]["raw_dir"] / run_id
        raw_dir.mkdir(parents=True, exist_ok=True)

    results_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"{run_id}: running {len(tasks)} calls with {settings['workers']} workers")
    ok = failed = 0
    with ThreadPoolExecutor(max_workers=settings["workers"]) as pool, open(results_path, "a") as out:
        futures = [pool.submit(execute, t, clients, settings, meta, env, raw_dir) for t in tasks]
        for fut in as_completed(futures):
            row = fut.result()
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            if row["error"]:
                failed += 1
                print(f"  ERROR {row['provider']} {row['airline_target']} {row['route_id']} {row['direction']}: {row['error']}")
            else:
                ok += 1
    print(f"Done: {ok} ok, {failed} failed.")
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print prompts and rotation, call no API, write nothing")
    ap.add_argument("--limit", type=int, help="max calls per batch (takes the first N of the batch)")
    ap.add_argument("--batches", type=int, default=1,
                    help="run N consecutive batches (run numbers n, n+1, ...) in one go; ignored with --test")
    ap.add_argument("--run-number", type=int, help="override the computed run number")
    ap.add_argument("--test", action="store_true", help="flag rows is_test, run_number 0, save raw responses")
    ap.add_argument("--providers", help="comma list to restrict providers, e.g. anthropic")
    ap.add_argument("--check-rotation", type=int, metavar="N", help="show rotation balance over N runs and exit")
    ap.add_argument("--config", default=str(ROOT / "config"))
    ap.add_argument("--date", help="override run date YYYY-MM-DD (for reproducible dry runs)")
    args = ap.parse_args(argv)

    settings, routes_cfg = load_config(args.config)
    if args.providers:
        settings["providers"] = [p for p in args.providers.split(",") if p in KEY_ENV]
    run_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(timezone.utc).date()

    if args.check_rotation:
        check_rotation(args.check_rotation, run_date, settings, routes_cfg)
        return 0

    batches = 1 if args.test else max(1, min(args.batches, settings.get("max_batches_per_dispatch", 8)))
    if not args.test and args.batches > batches:
        print(f"--batches {args.batches} capped to {batches} (max_batches_per_dispatch).")
    if args.test:
        base = args.run_number if args.run_number is not None else 0
    else:
        base = args.run_number or next_run_number(read_rows(ROOT / settings["paths"]["results"]))

    codes = []
    for i in range(batches):
        if batches > 1:
            print(f"\n=== batch {i + 1}/{batches} (run_number {base + i}) ===")
        codes.append(run_batch(args, settings, routes_cfg, run_date, base + i))
        if codes[-1] == 2:  # missing keys: no point continuing
            break
    return 2 if 2 in codes else (0 if 0 in codes else 1)


if __name__ == "__main__":
    sys.exit(main())
