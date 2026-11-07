# icey-airlines: where do AI agents source flight prices?

Hourly experiment: ask Claude and OpenAI (both with web search) for flight prices on Alaska, Delta and
Southwest routes, and record which websites they actually use (airline sites vs. OTAs/aggregators).
Sources come from **structured API fields** (search queries, result URLs, cited URLs), not from the model
describing itself. The model's own `SOURCES:` line is stored separately as a cross-check.

Caveat: the API with web search is not identical to the consumer ChatGPT/Claude apps. Read results as "how
the models search and source flight prices", not exactly what end users see. No bookings are made.

## Layout
- `config/settings.yaml` models, caps, rotation settings (change models here, not in code)
- `config/routes.yaml` routes per airline (**drafts, not verified**; Southwest list is my own guess)
- `config/domains.yaml` domain → category map (`airline_direct_target`, `airline_direct_other`, `ota_aggregator`, `other`)
- `src/run.py` builds the batch, calls APIs, appends rows to `data/results.jsonl`
- `src/providers.py` Anthropic + OpenAI wrappers and URL extraction · `src/classify.py` domain classification
- `.github/workflows/run_experiment.yml` hourly schedule + manual "Run workflow"

## Design
- Each hourly run: 3 airlines × 3 routes × 2 directions × 2 providers = **36 calls** (cap: 40).
- Routes advance 3 per run per airline; window / fare / add-on follow a deterministic rotation over 27 combos
  keyed on the run number. Both directions and both providers get the identical prompt variables.
- Base prompt never names the airline (tests whether the agent picks it). `prompt_variant: named` is available but off.
- Test runs (`--test` / manual run with "test" checked) are flagged `is_test` and excluded from analysis.
- Known confound: Alaska (West Coast/Alaska), Delta (Atlanta/East), Southwest (hub-to-hub) are different markets.

## Local commands (no API keys needed)
```
python -m src.run --dry-run                  # show the next run's prompts
python -m src.run --dry-run --run-number 12  # preview any run
python -m src.run --check-rotation 72        # balance of the rotation over 72 runs
python -m unittest discover -s tests -t .
python -m src.classify data/results.jsonl    # category counts, top domains, unknown domains
```

## GitHub setup
1. Secrets (Settings → Secrets and variables → Actions → Secrets): `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.
2. Run the first test from the Actions tab: **Run experiment → Run workflow** (leave test = true, limit = 12).
3. Create the repo **variable** `SCHEDULE_ENABLED` = `true` (Variables tab) to start the hourly runs (minute 7 of
   each hour, UTC). Set it to `false` to pause. Manual runs always work.
   GitHub can still start scheduled runs a few minutes late; the real start time is in `timestamp_utc`.
