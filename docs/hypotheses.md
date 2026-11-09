# Hypothesis inventory (as of Mon Nov 9, 2026)

Everything we hypothesised in the first build session (Nov 6–9), with how each was measured, the latest
result, and what is still open. Written as the hand-off for the next session.

## Data status

| | |
|---|---|
| Collection window | Fri Nov 6, 11:12 PM ET → Sun Nov 8, 6:07 PM ET (no batches after that; the cron-job.org trigger appears paused) |
| Calls | 1,272 real (non-test), **0 errors** |
| Prompt "base" (airline **not** named) | 1,236 calls, 35 batches, 10 routes per airline |
| Prompt "named" (airline named) | 36 calls, **1 batch** (run 35, Sun 3:07 PM ET) |
| Models | Claude `claude-sonnet-5-5` 636 · OpenAI `gpt-6.1-sol` 186 (until Sat ~11 AM ET) + `gpt-6-luna` 450 |
| Cadence | hourly (cron-job.org) from Sat 9 AM ET; every 3 h from Sun ~6 AM ET; earlier batches were manual / GitHub cron |
| Spend (estimate) | OpenAI ≈ $37 at list price · Claude search fees ≈ $13 + 15.7M input / 0.8M output tokens (Claude token price not verified) |

## How to read the results

- **Cited** = URLs the answer actually cites (`citations` in Claude, `url_citation` in OpenAI): where a user is sent.
  **Consulted** = every URL the search returned (`web_search_tool_result` / `action.sources`). OTAs appear in
  99.9% of consulted lists, so "consulted" rarely discriminates; *cited* is the main lens.
- **Unit = one API call.** Shares are "share of calls where the answer cites at least one URL of that kind".
- **Statistics.** Calls inside one batch share routes, dates and time, so they are not independent. All intervals and
  p-values below come from a **cluster bootstrap that resamples whole batches** (10,000 reps, seed 7), unless marked
  "naive". H3–H5 use a Holm correction across the three. H1/H2 numbers here use the same bootstrap (computed for this
  file; `src/analyze.py` still prints a naive z-test).
- **Routes are not comparable across airlines** (Alaska: SEA hub incl. Alaska/Hawaii; Delta: ATL hub, East/Florida;
  Southwest: point to point). Any "airline" difference may be a "market/route" difference.
- **Model pooling.** OpenAI rows pool `gpt-6.1-sol` and `gpt-6-luna` (Carlos' choice). Luna cites slightly less OTA
  (47% vs 56%) and own site (39% vs 47%) than sol, so OpenAI results lean a bit toward luna's behaviour.

## Summary

| ID | Hypothesis | Origin | Status |
|---|---|---|---|
| H1 | Agents rely more on OTAs than on the airline's own site | Spec | **Mixed**: true overall and for Delta/Southwest; false for Alaska on OpenAI |
| H2 | It happens more for Alaska than for the comparison carrier | Spec | **Rejected (reversed)**: Alaska has *fewer* OTA citations than Delta |
| H3 | Claude's Delta gap is a retrieval problem, not a preference | Chat (Nov 8) | **Supported, replicated** out of sample |
| H4 | First-class queries push agents toward OTAs | Chat (Nov 8) | **Supported, replicated** out of sample |
| H5 | OpenAI cites Alaska's site more than rivals' sites when it finds it | Chat (Nov 8) | **Supported, replicated**, but route-confounded |
| H6 | Naming the airline in the prompt lowers OTA reliance | Chat (Nov 8) | **Untested**: only 1 named batch; descriptive signal is large |
| S1–S5 | Spec's secondary questions (model, direction, window, fare, add-ons) | Spec | Model and fare matter; direction, window, add-ons do not |
| X1 | "Absence": the agent recommends a different airline | Spec | Large for OpenAI; heuristic metric, removed from dashboard |
| X2 | Agents use OTAs because only OTAs expose prices | Chat (Nov 8, exploration) | **Dropped**: no difference found |
| X3 | `delta.com` blocks Claude's crawler | Chat (speculation) | **Unverified** guess explaining H3 |
| X4 | Self-reported sources agree with structured citations | Spec | Agree ~99–100% (weak cross-check) |
| X5 | `gpt-6-luna` behaves like `gpt-6.1-sol` (cost switch) | Chat (Nov 7) | Close, not identical |

---

## H1 — Agents rely more on OTAs than on the airline's own website

**Statement (spec §2).** When asked to find flight prices, LLM agents with web search rely more on
aggregators/OTAs than on the airline's own site.

**Why it matters.** Disintermediation: an OTA booking costs Alaska 5–20% commission plus ancillaries, loyalty and the
co-brand card.

**Operationalisation.** Per call: `cited_target` (cites the airline's own domain; for Alaska also
`hawaiianairlines.com`) vs `cited_ota` (cites any domain in `config/domains.yaml → ota_aggregator`, incl. Google
Flights paths). Statistic: own-site share − OTA share, base prompt only.

**Result (base, 1,236 calls).**

| | Own site cited | OTA cited | Own − OTA (95% CI) |
|---|---|---|---|
| All | 52% | 71% | −19.6 pp [−24.3, −15.2] |
| Claude · Alaska | 86% | 89% | −3.4 pp [−10.7, +3.9] (n.s.) |
| Claude · Delta | 14% | 93% | −79.1 pp [−84.0, −73.8] |
| Claude · Southwest | 86% | 95% | −8.7 pp [−17.0, −1.4] |
| OpenAI · Alaska | 65% | 43% | **+21.4 pp** [+8.4, +33.8] |
| OpenAI · Delta | 28% | 60% | −32.0 pp [−40.8, −22.8] |
| OpenAI · Southwest | 32% | 47% | −15.5 pp [−29.5, −1.4] |

Share of all cited URLs: OTA 35%, other airlines 23%, target airline 16%, other (news, blogs…) 26%.
Most cited domains: southwest.com, kayak.com, alaskaair.com, flyfrontier.com, aa.com, trip.com, momondo.com.

**Verdict.** Mixed. OTAs win overall and for Delta and Southwest. **Alaska is the exception on OpenAI** (own site beats
OTA) and roughly a tie on Claude. Note that Claude cites both kinds a lot (≈6 URLs per answer), so "own vs OTA" on
Claude is often "both".

**Caveats.** API ≠ consumer ChatGPT/Claude apps. Base prompt does not name the airline, so the "target" is only the
airline whose home routes we picked.

## H2 — It happens more for Alaska than for the comparison carrier

**Statement (spec §2).** OTA reliance is higher for Alaska than for Delta. Southwest was added as a second
comparison carrier on Nov 6.

**Operationalisation.** `cited_ota` share, Alaska minus each other airline, base prompt, by model and pooled.

**Result.**

| | Alaska | Other | Diff (95% CI) | p |
|---|---|---|---|---|
| All models · vs Delta | 66% | 76% | −10.0 pp [−16.8, −2.9] | 0.004 |
| All models · vs Southwest | 66% | 71% | −4.9 pp [−10.0, +0.5] | 0.07 |
| Claude · vs Delta | 89% | 93% | −3.4 pp [−10.0, +3.3] | 0.36 |
| Claude · vs Southwest | 89% | 95% | −5.8 pp [−11.2, −0.5] | 0.04 |
| OpenAI · vs Delta | 43% | 60% | −16.5 pp [−27.1, −5.9] | 0.001 |
| OpenAI · vs Southwest | 43% | 47% | −3.9 pp [−13.4, +5.9] | 0.46 |

**Verdict.** **Rejected in the stated direction.** Alaska gets *fewer* OTA citations than Delta (driven by OpenAI) and
about the same as Southwest. Alaska's own site is cited far more than Delta's (Claude 86% vs 14%; OpenAI 65% vs 28%).

**Caveats.** Different markets per airline. Several comparisons, no correction across them. Part of the Delta gap on
Claude is H3 (retrieval), not preference.

## H3 — Claude's Delta gap is retrieval, not preference

**Origin.** Noticed Nov 7–8: Claude cited `delta.com` in only ~16% of Delta-route answers vs ~85% for the other two
airlines' sites. Formulated before the confirmation data existed (cutoff Nov 8, 02:05 UTC).

**Statement.** Claude cites an airline's own site at the same high rate whenever its search returns it; the Delta
gap exists because Claude's search rarely returns `delta.com`.

**Operationalisation.** Claude only, base prompt. (a) Retrieval: own domain present in consulted URLs.
(b) Preference: cited | retrieved. (a) tested for difference; (b) tested for **equivalence** (90% CI inside ±20 pp).

**Result.**

| | Discovery (21 batches) | Confirmation (14 batches) |
|---|---|---|
| Own site in Claude's search results: Delta vs Alaska+Southwest | 17% vs 98% (−80.7 pp [−88.1, −72.9]) | 12% vs 98% (−85.7 pp [−92.9, −77.4]) |
| Claude cites it when it appears: Delta vs others | 90% (n=21) vs 87% → equivalent | 90% (n=10) vs 89% → equivalent |

OpenAI, by contrast, finds `delta.com` in 62% of Delta answers.

**Verdict.** **Supported and replicated.** The gap is in what Claude's search returns, not in what Claude chooses.

**Caveats.** The "when it appears" part rests on few calls (21 and 10). Equivalence holds at ±20 pp, not at ±10 pp.
We don't know *why* retrieval fails (see X3).

## H4 — First-class queries push agents toward OTAs

**Origin.** Seen in the dashboard heatmap on Nov 8 (first class cells darkest). One of four trip factors we looked at,
so the discovery result is selection-inflated; the confirmation set is the honest test.

**Statement.** Asking for first class raises the share of answers citing an OTA versus basic economy.

**Operationalisation.** `cited_ota`, first_premium vs basic_economy, averaged within each model × airline stratum.

**Result.**

| | First | Main | Basic | First − basic (95% CI) |
|---|---|---|---|---|
| Discovery | 84% | 67% | 63% | +19.8 pp [+13.8, +25.7] |
| Confirmation | 77% | 71% | 65% | +13.3 pp [+6.6, +20.0] |

**Verdict.** **Supported and replicated** (effect shrank from +20 to +13 pp, as expected after selection).

**Why it matters.** Premium-cabin shoppers are the highest-value customers; they are the ones most often sent to OTAs.
Mechanism unknown (possible: premium fares less visible to the search tool on airline sites; comparison behaviour).

## H5 — OpenAI favours Alaska's own site when it finds it

**Origin.** Seen Nov 8: OpenAI's cited | retrieved rate for alaskaair.com was clearly above Delta's and Southwest's.

**Statement.** Given that the airline's own site is in OpenAI's search results, OpenAI cites it more often for Alaska
than for Delta or Southwest.

**Operationalisation.** OpenAI only, base prompt, cited | retrieved, Alaska vs Delta+Southwest pooled.

**Result.**

| | Alaska | Delta | Southwest | Alaska − others (95% CI) |
|---|---|---|---|---|
| Discovery | 69% (n=111) | 51% (n=77) | 45% (n=91) | +21.8 pp [+6.1, +37.8], p=0.008 |
| Confirmation | 75% (n=75) | 34% (n=50) | 40% (n=60) | +37.4 pp [+14.4, +57.7], p=0.001 |

**Verdict.** **Supported and replicated**, the weakest of the three (wide intervals).

**Caveats.** Cannot separate airline from route: Alaska routes include near-monopolies (SEA–JNU, SEA–FAI) where the
agent has little else to cite. A route-matched design would be needed.

## H6 — Naming the airline lowers OTA reliance

**Origin.** Carlos, Nov 8: does the agent still send people to OTAs once the shopper has picked the airline? The
"named" prompt adds "with <Airline>" ("I want to fly **with Alaska Airlines** from Seattle to San Diego…"); everything
else is identical. From Nov 8, `prompt_variant: alternate` gives even run numbers the base prompt and odd ones the
named prompt.

**Statement.** With the airline named, answers cite OTAs less and the airline's own site more.

**Planned test.** `scripts/hypotheses.py → h6()`: named vs base batches from the side-by-side period, averaged within
model × airline, cluster bootstrap. Needs ≥2 named batches.

**Result.** **Not testable**: only one named batch (run 35, 36 calls) ran before collection stopped. Descriptive only,
named batch vs the two adjacent base batches (34 and 36, 72 calls):

| | Named | Base (adjacent) |
|---|---|---|
| OTA cited | 42% | 74% |
| Own site cited | 89% | 42% |
| Own site in search results | 92% | 65% |
| Answer never names the airline | 0% | 31% |

The drop is concentrated in OpenAI (OTA cited Alaska 0% vs 25%, Delta 17% vs 58%, Southwest 0% vs 67%; n=6 vs 12 each).
Claude stays near 100% OTA for Alaska and Delta.

**Next step.** Run ≥6 more named batches (e.g. cron body `"batches":"2"` so each trigger yields one of each), then
run `python scripts/hypotheses.py`. Adjacent batches cover different routes and trip types, so the numbers above are
a hint, not evidence.

## Secondary questions from the spec (S1–S5)

Spec §2 asked whether the source mix varies by model, direction, booking window, fare class and add-ons. Same method as
H4 (OTA cited, averaged within model × airline, cluster bootstrap), confirmation set unless noted:

| ID | Factor | Result | Verdict |
|---|---|---|---|
| S1 | Model (Claude vs OpenAI) | OTA cited 92% vs 50%; Claude cites ~6 URLs/answer, OpenAI ~2 | Large difference; partly citation *style*, not just preference |
| S2 | Direction (return vs outbound) | +2.0 pp [−6.0, +9.1] (discovery +5.2, p=0.07) | No effect (sanity check passed) |
| S3 | Booking window | holiday vs next week +0.6 pp; next month vs next week +6.3 pp [−2.1, +14.6] | No clear effect |
| S4 | Fare class | see H4 | First class → more OTA |
| S5 | Add-ons (bag, seat) | −1.8 pp and −0.6 pp, CIs ±9 pp | No effect |

## X1 — Absence: the agent recommends another airline

**Spec §1.** Two separate risks: *absence* (agent recommends a different airline, sale lost) and
*disintermediation* (agent sends the user to an OTA, sale at lower margin).

**Operationalisation.** Text heuristic: the answer never mentions the target airline's name (`absent` in
`src/analyze.py`). It does not check *which* airline is recommended.

**Result (base).**

| | Alaska | Delta | Southwest |
|---|---|---|---|
| Claude | 0% | 6% | 2% |
| OpenAI | 22% | 52% | 59% |

Example: OpenAI, LAS→SEA basic economy, search returned alaskaair.com and delta.com, answer offered Frontier only.
With the airline named (H6, one batch) absence drops to 0%.

**Status.** Removed from the dashboard on Nov 8 (confusing next to the OTA numbers); still computed in the data.
OpenAI rarely naming the "home" airline on competitive routes is a real finding for the absence risk, but the metric is
crude: a better version would parse which carrier the answer recommends.

## X2 — Agents use OTAs because only OTAs expose prices (dropped)

**Idea (Nov 8).** Airline sites render fares dynamically, so the search tool can't read prices there; answers built
on the airline's site would more often lack a price or admit they couldn't verify it.

**Operationalisation.** Regex for a `$` amount and for "couldn't / unable to … verify / find / confirm" phrases, split
by what the answer cites.

**Result.** Claude includes a $ price in 100% of answers regardless of source. OpenAI: 83% (OTA cited) vs 88% (own
site only). "Couldn't verify" disclaimers appear in 73–93% of answers in every group.

**Verdict.** **Dropped**: no difference in the predicted direction. Note that most answers carry a disclaimer that the
exact fare could not be verified, which is worth mentioning when discussing reliability.

## X3 — `delta.com` blocks Claude's crawler (unverified)

**Idea.** The simplest explanation for H3. Not checked: we did not fetch `delta.com/robots.txt` or test Claude's
search tool directly. Next step: check robots.txt for Anthropic's crawler user agents and compare with
alaskaair.com and southwest.com; run a few direct searches with `allowed_domains: ["delta.com"]`.

## X4 — Self-reported sources match the structured citations

**Spec §4.** The prompt asks for a final `SOURCES:` line, stored as `self_reported_sources`, as a cross-check.

**Result.** The line is present in 99.9% of answers. Share of self-reported domains found among cited or consulted URLs:
Claude 100%, OpenAI 99%. **Verdict:** consistent, but a weak check (it only tests that what the model lists was
really in front of it, not completeness).

## X5 — `gpt-6-luna` behaves like `gpt-6.1-sol`

**Context.** OpenAI model switched from `gpt-6-astra` (first test only) to `gpt-6.1-sol` (Nov 7, cost) and to
`gpt-6-luna` (Nov 7 ~11 AM ET, cost; ~half the per-call price, search fees dominate).

**Result (base).** Searches per call 4.5 vs 4.0; consulted URLs 44 vs 47; cited 1.7 vs 2.0. OTA cited 47% vs 56%;
own site cited 39% vs 47%; own site retrieved 75% vs 76%.

**Verdict.** Similar search behaviour, slightly fewer citations of every kind. Not a controlled comparison (different
hours, different routes in rotation). Pooled as "OpenAI" in the dashboard at Carlos' request.

---

## Method notes and known limitations

- **Design.** Each batch: 3 airlines × 3 routes × 2 directions × 2 models = 36 calls, same prompt variables for both
  directions and both models. Rotation over 27 window × fare × add-on combinations keyed on the run number.
- **Prompt.** "I want to fly from {origin} to {destination} on {date}, {fare}, {add-on}. Can you find me the price and
  where I can book it? At the end, add one line starting with SOURCES: listing the websites you used."
- **Holiday date** is fixed at Dec 23, 2026. "Next week" = run date + 7 days, "next month" = + 30 days.
- **Route lists are drafts** (`config/routes.yaml`): Alaska and Delta from the spec, Southwest chosen by Claude; none
  verified against DOT/OAG.
- **Domain classification** in `config/domains.yaml`; ~15 small domains remain "other" (e.g. helloaxel.com,
  deeparrival.com, flyxworld.com) and were never reviewed manually.
- **Coverage gap.** Sat Nov 7, 07:02–13:04 UTC had no data (GitHub's cron misfired); fixed with a manual 6-batch run
  and the cron-job.org trigger.

## Reproduce

```
python -m src.analyze                  # base prompt; --variant named | all
python scripts/hypotheses.py           # H3–H5 discovery/confirmation, H6 when ≥2 named batches exist
python -m src.classify data/results.jsonl
```
The H1/H2 bootstrap numbers in this file were computed ad hoc with the helpers in `scripts/hypotheses.py`
(`prep`, `bootstrap`, `summarize`); adding them to that script is a small next step.

## Open items for next session

1. Decide whether to restart collection for H6 (named prompt) and how many batches; turn the cron back on with
   `"batches":"2"` or pause it for good.
2. If stopping: pause the cron-job.org job, **revoke the GitHub fine-grained token** (it was pasted in chat; expires
   Dec 7), optionally delete branch `claude/clever-dijkstra-k0aeoa`.
3. Check X3 (delta.com robots.txt / crawler access).
4. Improve X1 (detect which carrier the answer recommends).
5. Fold the H1/H2 bootstrap into `scripts/hypotheses.py` and `src/analyze.py`.
6. Talking points for the François (Alaska) call, with the caveats above.
7. Repo and dashboard are **public**; confirm that is acceptable before sharing findings.
