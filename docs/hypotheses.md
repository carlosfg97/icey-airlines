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
  "naive". H3–H5 use a Holm correction across the three. H1/H2 use the same bootstrap (`h1_h2()` in
  `scripts/hypotheses.py`; the `src/analyze.py` CLI still prints a naive z-test; the dashboard uses the bootstrap).
- **Domain list (reviewed Nov 9).** Country versions of listed OTAs (expedia.ca, kayak.co.uk, …), other OTAs
  (traveloka, hotwire, edreams, …), two route finders (directflights.com, flightroutes.com) and a few airline domains
  (alaskaair.net, hawaiianair.com, aveloair.com, …) were added to `config/domains.yaml`. **helloaxel.com**, an AI-native
  ticket search built for agent-to-agent use, has its own category `ai_travel_agent` and is **not** counted as an OTA
  (see X6). Fee/policy guides and small fare sites stay "other". All numbers in this file use the reviewed list.
- **Routes are not comparable across airlines** (Alaska: SEA hub incl. Alaska/Hawaii; Delta: ATL hub, East/Florida;
  Southwest: point to point). Any "airline" difference may be a "market/route" difference.
- **Model pooling.** OpenAI rows pool `gpt-6.1-sol` and `gpt-6-luna` (Carlos' choice). Luna cites slightly less OTA
  (49% vs 58%) and own site (39% vs 47%) than sol, so OpenAI results lean a bit toward luna's behaviour.

## Summary

| ID | Hypothesis | Origin | Status (after the Nov 9 robustness review, see [below](#robustness-review-nov-9)) |
|---|---|---|---|
| H1 | Agents rely more on OTAs than on the airline's own site | Spec | **Mixed**: true overall and for Delta/Southwest. The Alaska-on-OpenAI exception is **fragile**: luna only, and borderline (p = 0.09) if the AI travel agent counts as an intermediary |
| H2 | It happens more for Alaska than for the comparison carrier | Spec | **Rejected (reversed)**, robust: Alaska is sent to an OTA *without* its own site far less often than Delta (both models) and Southwest (OpenAI) |
| H3 | Claude's Delta gap is a retrieval problem, not a preference | Chat (Nov 8) | **Supported, replicated**, and narrowed: Claude's search rarely returns delta.com **even when its query says "Delta"**, and never returns a Delta fare page |
| H4 | First-class queries push agents toward OTAs | Chat (Nov 8) | **Supported, robust**: holds within route × model, in both OpenAI models; it is "OTA instead of own site", not just "more links" |
| H5 | OpenAI cites Alaska's site more than rivals' sites when it finds it | Chat (Nov 8) | **Supported for `gpt-6-luna` only** (none in `gpt-6.1-sol`); survives route-level CI and leave-one-route-out |
| H6 | Naming the airline in the prompt lowers OTA reliance | Chat (Nov 8) | **Untested**: only 1 named batch; same-route comparison makes the signal even larger for OpenAI |
| S1–S5 | Spec's secondary questions (model, direction, window, fare, add-ons) | Spec | Model and fare matter; direction, window, add-ons do not |
| X1 | "Absence": the agent recommends a different airline | Spec | Large for OpenAI; heuristic metric (checked: not inflated by the state name "Alaska") |
| X2 | Agents use OTAs because only OTAs expose prices | Chat (Nov 8, exploration) | **Dropped**: no difference found |
| X3 | `delta.com` blocks Claude's crawler | Chat (speculation) | **Unverified**; more plausible after R6, but robots.txt could not be fetched from the sandbox |
| X4 | Self-reported sources agree with structured citations | Spec | Agree ~99–100% (weak cross-check) |
| X5 | `gpt-6-luna` behaves like `gpt-6.1-sol` (cost switch) | Chat (Nov 7) | **No** for own-site citation: Delta own site cited 50% (sol) vs 18% (luna); this drives H5 |
| X6 | The AI travel agent helloaxel.com is a new kind of intermediary | Carlos (Nov 9) | **Descriptive**: cited in 9% of answers, mostly Claude on Alaska routes, economy trips; in half of those it is the only intermediary |

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
| All | 52% | 72% | −20.9 pp [−25.5, −16.5] |
| Claude · Alaska | 86% | 91% | −5.3 pp [−11.9, +1.5] (n.s.) |
| Claude · Delta | 14% | 93% | −79.1 pp [−84.0, −73.8] |
| Claude · Southwest | 86% | 96% | −9.2 pp [−17.1, −1.9] |
| OpenAI · Alaska | 65% | 44% | **+20.9 pp** [+7.9, +33.3] |
| OpenAI · Delta | 28% | 63% | −35.0 pp [−44.2, −25.2] |
| OpenAI · Southwest | 32% | 49% | −17.5 pp [−31.1, −3.8] |

Share of all cited URLs: OTA 37%, other airlines 23%, target airline 16%, AI travel agent 2%, other (news,
blogs…) 22%. Most cited domains: kayak.com, southwest.com, alaskaair.com, flyfrontier.com, aa.com, trip.com,
momondo.com.

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
| All models · vs Delta | 67% | 78% | −10.2 pp [−16.7, −3.6] | 0.001 |
| All models · vs Southwest | 67% | 72% | −4.9 pp [−10.0, +0.2] | 0.07 |
| Claude · vs Delta | 91% | 93% | −1.5 pp [−7.8, +4.8] | 0.72 |
| Claude · vs Southwest | 91% | 96% | −4.4 pp [−10.0, +1.0] | 0.15 |
| OpenAI · vs Delta | 44% | 63% | −18.9 pp [−29.5, −8.6] | <0.001 |
| OpenAI · vs Southwest | 44% | 49% | −5.3 pp [−14.6, +4.3] | 0.29 |

**Verdict.** **Rejected in the stated direction.** Alaska gets *fewer* OTA citations than Delta (driven by OpenAI) and
about the same as Southwest (the Claude-vs-Southwest gap, p = 0.04 before the domain review, is now n.s.: most
newly listed route finders appear on Alaska routes). Alaska's own site is cited far more than Delta's (Claude 86% vs 14%; OpenAI 65% vs 28%).

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
| Discovery | 84% | 68% | 65% | +18.6 pp [+12.6, +24.5] |
| Confirmation | 77% | 73% | 67% | +11.5 pp [+4.4, +18.9] |

**Verdict.** **Supported and replicated** (effect shrank from +19 to +12 pp, as expected after selection; Holm p =
0.003 in the confirmation set).

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
| Discovery | 68% (n=114) | 51% (n=77) | 45% (n=91) | +19.9 pp [+4.0, +36.3], p=0.015 |
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
| OTA cited | 44% | 75% |
| Own site cited | 89% | 42% |
| Own site in search results | 92% | 65% |
| Answer never names the airline | 0% | 31% |

The drop is concentrated in OpenAI (OTA cited Alaska 0% vs 33%, Delta 33% vs 58%, Southwest 0% vs 67%; n=6 vs 12 each).
Claude stays at 100% OTA for Alaska and Delta.

**Next step.** Run ≥6 more named batches (e.g. cron body `"batches":"2"` so each trigger yields one of each), then
run `python scripts/hypotheses.py`. Adjacent batches cover different routes and trip types, so the numbers above are
a hint, not evidence.

## Secondary questions from the spec (S1–S5)

Spec §2 asked whether the source mix varies by model, direction, booking window, fare class and add-ons. Same method as
H4 (OTA cited, averaged within model × airline, cluster bootstrap), confirmation set unless noted:

| ID | Factor | Result | Verdict |
|---|---|---|---|
| S1 | Model (Claude vs OpenAI) | OTA cited 93% vs 52%; Claude cites ~6 URLs/answer, OpenAI ~2 | Large difference; partly citation *style*, not just preference |
| S2 | Direction (return vs outbound) | −0.0 pp [−7.5, +7.5] (discovery +5.5, p=0.049) | No effect (sanity check passed in confirmation) |
| S3 | Booking window | holiday vs next week +0.7 pp; next month vs next week +6.6 pp [−2.2, +15.6] (discovery +9.0, p=0.04) | No clear effect |
| S4 | Fare class | see H4 | First class → more OTA |
| S5 | Add-ons (bag, seat) | −3.0 pp and −0.6 pp, CIs ±9 pp | No effect |

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

## X6 — AI travel agents: helloaxel.com (Nov 9)

**Context.** During the domain review Carlos flagged helloaxel.com: an AI-native ticket search built for
agent-to-agent use. It is neither the airline nor a classic OTA, so it has its own category (`ai_travel_agent`), its
own color on the dashboard, and is **not** counted in `cited_ota`. Descriptive only (`scripts/robustness.py` R10); no
hypothesis was set in advance.

| % of calls (base) | Retrieved by search | Cited | Cited if retrieved |
|---|---|---|---|
| Claude · Alaska | 43 | **19** | 45 (n=88) |
| Claude · Delta | 33 | 8 | 24 (n=68) |
| Claude · Southwest | 28 | 1 | 5 (n=58) |
| OpenAI · Alaska | 74 | 10 | 13 (n=152) |
| OpenAI · Delta | 65 | 9 | 13 (n=134) |
| OpenAI · Southwest | 66 | 4 | 7 (n=135) |

- Cited in 106 of 1,236 answers (9%); 2% of all cited URLs.
- **OpenAI sees it in most searches but rarely cites it; Claude sees it less but cites it far more often**, mainly on
  Alaska routes (SEA-ANC 30%, SEA-HNL 30%, SEA-LAS 25%) and ATL-PBI (34%).
- **Economy, not first class**: cited in 9% of basic, 13% of main economy, 3% of first-class answers, the opposite
  of the H4 pattern for OTAs.
- **It often replaces an OTA**: in 52% of the answers that cite it, no OTA is cited (own site cited in 53%).
- Similar on both days (Nov 7 7%, Nov 8 10%) and both OpenAI models (sol 6%, luna 8%).

**Why it matters.** A new layer between the shopper's agent and the airline: if AI-native fare sites become agents'
preferred source, "OTA vs own site" understates disintermediation. It also tilts H1: counting it as an intermediary
makes the OpenAI-Alaska exception borderline (see the robustness review).

**Open.** Whether helloaxel sells tickets itself or hands off to the airline/OTA (check its booking flow); other AI
travel agents to add to the category as they appear.

---

## Robustness review (Nov 9)

Question asked: are we using the data correctly to prove or disprove each hypothesis, and where are the blind spots?
All numbers below come from `python scripts/robustness.py` (base prompt, 1,236 calls, same cluster bootstrap by batch
unless marked "route CI"). Numbers were refreshed after the Nov 9 domain review (see "How to read the results").

### What holds up

- **Data integrity.** 35 batches × 36 calls (+ 1 named batch), no duplicate call keys, 0 errors; only ~1.5% of
  OpenAI answers cite nothing. The doc's numbers reproduce exactly from `scripts/hypotheses.py`.
- **H2 (reversed) is robust.** The outcome that matters for disintermediation is "sent to an OTA *and not* to the
  airline's own site" (`ota_only`), because Claude cites ~6 URLs and "any OTA" sits at 91–96% for every airline.
  On that outcome Alaska is far below Delta (Claude −65.5 pp [−73, −57]; OpenAI −18.0 pp [−28, −7]) and below
  Southwest on OpenAI (−18.9 pp [−28, −9]). Resampling routes instead of batches gives the same Alaska-vs-Delta
  result on OpenAI (−18.9 pp [−28.9, −9.6]).

  | `ota_only` / `both` / `own_only` / `neither` (% of calls) | Alaska | Delta | Southwest |
  |---|---|---|---|
  | Claude | 14 / 78 / 8 / 0 | 79 / 14 / 0 / 7 | 14 / 82 / 4 / 0 |
  | OpenAI | 24 / 19 / 45 / 11 | 42 / 20 / 7 / 30 | 43 / 6 / 26 / 25 |

- **H4 is robust.** First class fare is not balanced across routes (e.g. SEA-HNL 20 first-class calls vs 12 basic), so
  the test was redone within route × model (60 strata): +15.3 pp [+10.1, +20.4]. It is not "more links": cited URLs
  per call are flat by fare (Claude 6.3 vs 6.0, OpenAI 1.8 vs 1.8). "OTA only" rises +9.8 pp [+5.0, +15.1] and the
  own-site *fare page* is cited slightly less (−3.4 pp, p = 0.06). It appears in both OpenAI models (sol +29 pp,
  luna +12 pp raw).
- **H3 is sharper than stated.** The search *query* names the airline in 72% of Claude's Delta calls (similar to
  the 69–82% for the other airlines). Even then, Claude's search returns delta.com only 21% of the time, against
  97–99% for alaskaair.com / southwest.com and 81% for OpenAI on the same kind of query. **No Claude call ever got a
  Delta fare or booking page**; the delta.com pages it cites are baggage/onboard info. So the gap is in Claude's search
  index or crawl access, not in query wording or in Claude's choices (consistent with X3, still unverified).
- **X1 heuristic.** Matching only brand forms ("Alaska Airlines", "alaskaair", "Hawaiian Airlines") gives the same
  absence rates (OpenAI Alaska 21% vs 22%), so the state name "Alaska" does not inflate presence.

### What is weaker than the doc says

1. **The confirmation set is not a clean replication for OpenAI: the model changed.** Discovery holds 186 `gpt-6.1-sol`
   + 180 `gpt-6-luna` OpenAI calls; confirmation holds **only luna** (252). The two models differ a lot on Delta's
   own site (cited 50% sol vs 18% luna). Split by model:

   | H5: OpenAI cites own site given it was retrieved, Alaska − others (route CI) | |
   |---|---|
   | `gpt-6.1-sol` (discovery) | **−2.8 pp [−21.0, +17.0]** |
   | `gpt-6-luna` discovery | +44.0 pp [+22.5, +63.9] |
   | `gpt-6-luna` confirmation | +37.4 pp [+17.8, +55.4] |

   H5 replicates *within luna*, but it is a luna behaviour, not "OpenAI". The same holds for the H1 Alaska exception
   (own − OTA: sol +4.8 pp [−19, +27], luna +27.8 pp [+14, +42]). Pooling the models (agreed Nov 7) hides this.
2. **The H1 Alaska exception depends on how the AI travel agent is counted.** After the domain review, OpenAI-Alaska
   own − OTA is +20.9 pp [+7.9, +33.3]. If helloaxel.com (X6) also counts as an intermediary, it falls to
   **+12.1 pp [−1.9, +25.7], p = 0.09**. H2 does not change for OpenAI (−18.0 pp); for Claude, OTA-or-AI-agent reaches
   93–96% everywhere (ceiling). *Correction:* an earlier version of this section also counted fee/policy guides
   (withautopilot.com, deeparrival.com, dyme.earth) as "fare sites"; they are not, and they barely moved the result.
3. **"Own site cited" mixes fare pages with info pages.** Alaska and Southwest publish static
   "flights-from-X-to-Y" route pages with fares that search tools index; Delta does not (its retrieved pages are
   baggage, onboard, PDFs, pro.delta.com agency pages, and the dynamic booking page). Own *fare/booking* page cited:
   Claude 83 / 0 / 86%, OpenAI 56 / 15 / 30% (Alaska / Delta / Southwest). This is a likely **mechanism** for both H2
   and H5 (it's an inference): airlines with crawlable fare pages get cited. H5 survives restricting to calls where an own
   *fare* page was retrieved (+27.6 pp [+13.6, +41.6]), but Delta's rate rises from 44% to 64% (n=58) under that filter,
   so part of Delta's gap is page type.
4. **Airline claims rest on 10 routes per airline.** The batch bootstrap treats the 30 routes as fixed. Resampling
   routes inside each airline widens intervals (Claude Alaska vs Southwest on `cited_ota`: p = 0.15 by batch, 0.30 by
   route). OpenAI Alaska vs Delta (p < 0.001) and H5 (+26.8 pp [+10.3, +42.6]) survive.
   H5 is not driven by one route: leaving any single Alaska route out keeps it between +24 and +30 pp (the
   "near-monopoly" worry, SEA-JNU/SEA-FAI, does not explain it).

### H6, closer look

Comparing the named batch (run 35) with the 348 base calls on the **same routes and directions** (instead of the two
adjacent batches): OpenAI OTA cited **11% vs 52%**, own site cited 100% vs 47%, absence 0% vs 41%. Claude: OTA 78% vs
96%, own site 78% vs 66%. Still one batch (n = 18 per model), so still untested, but the matched comparison points
the same way and is larger for OpenAI.

### Blind spots the data cannot answer

- **"OTA cited" ≠ "the target airline's fare sold through an OTA".** We never check which carrier the OTA link
  shows. On a Southwest route an OTA page may list only other carriers' fares (Southwest's OTA distribution is
  limited and should be checked), so H1/H2 measure "sent to an intermediary", not lost margin on the target airline.
- **Citation ≠ click or booking.** Claude cites ~6 URLs; we don't know which one a user would open. Citation order
  is a weak proxy at best (not analysed).
- **One draw per condition.** Each prompt × model × route × date runs once; we can't separate model randomness from
  condition effects except through the batch bootstrap. A few repeated identical prompts would measure this.
- **Two days, one location, the API.** Search indexes and fares change; the consumer apps may differ.
- **Model's own query choice is an intermediate outcome.** Whether the agent puts the airline in its query strongly
  drives retrieval on OpenAI (Southwest: 96% retrieved if named in the query, 44% if not). Conditioning on it is
  descriptive, not causal.
- **Domain list.** Reviewed once on Nov 9 (all 944 "other" domains scanned, candidates validated by Carlos). New
  sites will keep appearing; rerun `python -m src.classify data/results.jsonl` after new data.

### Dashboard changes made (Nov 9)

`app.py` now: (1) adds a third boarding-pass row and a route-board column, "OTA, no own-site link";
(2) replaces the naive pooled z-test card with per-model comparisons on that metric, using a batch-cluster bootstrap
(`compare_airlines_clustered` in `src/analyze.py`, 2,000 reps; no test with fewer than 5 batches, so the named prompt
shows "too few to test"); (3) adds a "Split OpenAI" toggle (sol vs luna); (4) fixes text that said collection is
hourly; (5) after the domain review, shows the AI travel agent as its own color in the URL mix, a fourth boarding-pass
row and a route-board column. With models split, OpenAI sol shows no Alaska-vs-Delta gap on "OTA only" (+2 pts
[−13, +18]); luna does (−26 pts [−38, −15]). All numbers above match the dashboard.

### Suggested changes to how results are reported

1. Report OpenAI results **per model** (or luna only), at least for H1 and H5.
2. Use `ota_only` (OTA without own site) as the headline disintermediation metric next to `cited_ota`.
3. Show H1 both ways: OTA only, and OTA or AI travel agent (done in `scripts/robustness.py` R1).
4. Report airline differences with route-level intervals.
5. For the Alaska call: "Alaska's static route/fare pages are a likely reason agents cite alaskaair.com" is a
   testable, actionable story (keep them crawlable; check what premium-cabin pages exist, given H4).

---

## Method notes and known limitations

- **Design.** Each batch: 3 airlines × 3 routes × 2 directions × 2 models = 36 calls, same prompt variables for both
  directions and both models. Rotation over 27 window × fare × add-on combinations keyed on the run number.
- **Prompt.** "I want to fly from {origin} to {destination} on {date}, {fare}, {add-on}. Can you find me the price and
  where I can book it? At the end, add one line starting with SOURCES: listing the websites you used."
- **Holiday date** is fixed at Dec 23, 2026. "Next week" = run date + 7 days, "next month" = + 30 days.
- **Route lists are drafts** (`config/routes.yaml`): Alaska and Delta from the spec, Southwest chosen by Claude; none
  verified against DOT/OAG.
- **Domain classification** in `config/domains.yaml`, reviewed Nov 9 (all "other" domains scanned; additions validated
  by Carlos). Remaining "other" = news, blogs, fee guides, airport PDFs, flight trackers and small fare sites.
- **Coverage gap.** Sat Nov 7, 07:02–13:04 UTC had no data (GitHub's cron misfired); fixed with a manual 6-batch run
  and the cron-job.org trigger.

## Reproduce

```
python -m src.analyze                  # base prompt; --variant named | all
python scripts/hypotheses.py           # H3–H5 discovery/confirmation, H1/H2 tables, H6 when ≥2 named batches exist
python scripts/robustness.py           # Nov 9 robustness review (R1–R10)
python -m src.classify data/results.jsonl
```
The H1/H2 tables come from `h1_h2()` in `scripts/hypotheses.py`.

## Open items for next session

1. Decide whether to restart collection for H6 (named prompt) and how many batches; turn the cron back on with
   `"batches":"2"` or pause it for good.
2. If stopping: pause the cron-job.org job, **revoke the GitHub fine-grained token** (it was pasted in chat; expires
   Dec 7), optionally delete branch `claude/clever-dijkstra-k0aeoa`.
3. Check X3 (delta.com robots.txt / crawler access). It could not be fetched from the cloud sandbox (network
   policy); check it from a laptop, for ClaudeBot / Claude-SearchBot / Claude-User vs OAI-SearchBot.
4. Improve X1 (detect which carrier the answer recommends).
5. ~~Fold the H1/H2 bootstrap into `scripts/hypotheses.py`~~ done Nov 9 (`src/analyze.py` CLI still uses the z-test).
6. Talking points for the François (Alaska) call, with the caveats above.
7. Repo and dashboard are **public**; confirm that is acceptable before sharing findings.
