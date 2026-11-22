# What changed since Phase 2, and what is new

This is the briefing for the EL demo and the paper. The website deliberately does not label "Phase 2" or "Phase 3"; use this page to explain the difference when asked.

## Phase 2 in one paragraph

Phase 2 (commit `3b181bc`) was a resilience simulator with these parts:
- **Grid model:** a single-area swing equation with a governor.
- **Comparison:** four modes (unmanaged, reference AUFLS, AUFLS plus a staggered frequency-threshold rule, and a bulk-restart ablation).
- **Display:** a street of 12 illustrative buildings.
- **Supporting pieces:** a NILM demo, an appliance-request and reviewer workflow, and an optional ESP32 hardware-in-the-loop prototype.

Its control rule switched appliances off in proportion to how far frequency had fallen below 49.6 Hz. It never asked how much relief protection actually needed, and the campus was not real.

## What changed

### 1. Research core (the paper)

| Area | Phase 2 | Now | Backing |
|---|---|---|---|
| Frequency model | Swing equation with a simple governor | Reheat System Frequency Response model, closed-form and exact nadir | Anderson & Mirheydar, IEEE TPWRS 1990; Kundur 1994 |
| Disturbance estimate | None | Shortfall from RoCoF via the swing equation | Kundur; Inoue 1997; Terzija, IEEE TPWRS 2006 |
| Decision | Fixed threshold, proportional | **NP-MRD**: smallest relief that keeps the *predicted* nadir above AUFLS stage 1 plus a margin | AUFLS stages: SRPC task force 2024 |
| Who is paused | Order of the list | Lexicographic covering knapsack (HiGHS MILP): customers first, then deferred energy, then comfort slack | SAIFI, IEEE Std 1366; Lu, IEEE TSG 2012; Xu et al., IEEE TAC 2016 |
| Comfort | None | ETP room-temperature model and EV laxity | Mathieu et al., IEEE TPWRS 2013 |
| Bad communication | Not modelled | Latency, jitter and packet loss; a **pre-armed hybrid** that triggers locally on RoCoF | Special protection schemes: Anderson & LeReverend 1996 |
| Fair baseline | None | Decentralised frequency relays | Molina-García et al., IEEE TPWRS 2011 |
| Calibration | Textbook constants | Governor gain fitted to the Rajasthan (2023) and Khavda (2026) events, leaving one out each time; test error ≤ 0.007 Hz | Grid-India and RPC event reports |
| Evidence | 600 paired runs of the threshold rule | 1,870 runs over experiments E1–E5 (10 seeds) with paired Wilcoxon tests | |
| Paper | None | 5-page IEEE conference draft, every number generated from data | `paper/` |

### 2. Digital twin (the EL showcase)

| Area | Phase 2 | Now |
|---|---|---|
| Place | 12 illustrative buildings | The real RVCE campus and the neighbourhood around it |
| Geometry | Hand-placed boxes | **Photoreal:** Google photorealistic 3D tiles of the actual campus. **Model:** OpenStreetMap buildings, names, floors, roads, metro viaduct and river on Esri satellite imagery |
| Building data | Assumed | Energy is floor area × BEE benchmark, calibrated to RVCE's NAAC built-up area (67,721 m²) and hostel area (38,659 m²). The 500 kW rooftop PV sits on the 8 buildings named in the BESCOM report |
| Explanation | Live charts only | Seven-step guided **Story**; side-by-side **Compare**; a **decision explainer** showing what the controller measured, predicted and chose, and why |
| Look | Dashboard | Full-screen 3D, light and dark themes, sun position by NOAA equations, streetlights at civil twilight |
| Reproducibility | Live only | Deterministic replays cached by scenario and code version |

### 3. Hardware

The ESP32 firmware now holds a pre-armed RoCoF trigger. It is the bench version of the hybrid's local trigger. It is optional and not part of the paper.

## The novelty, in three sentences

1. Existing schemes either cut whole feeders (AUFLS) or curtail appliances by a fixed frequency rule. **Rakshak computes the minimum appliance relief from a predicted frequency nadir and picks the fewest consenting customers to supply it**, so AUFLS never operates while far fewer homes are touched.
2. Because central commands can arrive too late, **Rakshak pre-arms nested relief sets for a ladder of contingency sizes and lets appliances trigger locally on RoCoF**. The result is robust to 2 s latency and 40 % packet loss.
3. The work is **calibrated to Indian grid events** and shown on **a sourced digital twin of the RVCE campus**.

How it differs from Tata Power and AutoGrid:
- **Their focus:** demand response for peak reduction over minutes to hours, dispatched by the utility for energy and cost.
- **Rakshak's focus:** the first 2–10 seconds after a generator trip, sizing relief against the protection threshold.

They are different timescales, objectives and control problems.

## Headline numbers (`benchmarks/results/paper/summary.json`)

- **Customers interrupted per event:**
  - AUFLS only: 11.1, and it operates 0.56 AUFLS stages on average.
  - Fixed threshold rule: 12.8.
  - Local relays: 11.6.
  - **NP-MRD: 1.1.**
  - **Hybrid: 1.4.**
- **NP-MRD against AUFLS:** 10.0 fewer customers per event (95 % CI 8.8–11.1).
- **With 2 s command delay:**
  - central NP-MRD lets AUFLS operate and interrupts 24.1 customers;
  - the hybrid operated no stage in any tested latency and loss combination.

## Demo talk track (about 6 minutes)

1. **The twin (Story step 1).** Start in Photoreal. "This is RVCE from Google's aerial 3D capture. Every building's energy is calibrated to the NAAC figures. Click one." Open the Chemical Engineering block and read its sources. Switch to Model: "Our own model, used offline: OpenStreetMap names, floors and roads on satellite imagery."
2. **The event (step 2).** "A 5 % generation loss, the size of the Rajasthan 2023 and Khavda 2026 events. Watch the frequency in the top bar."
3. **AUFLS (step 3).** "At 49.4 Hz whole feeders open. Red buildings are dark, whatever they were running."
4. **Threshold rule (step 4).** "Phase 2's rule stops AUFLS but pauses far more homes than needed, and overshoots."
5. **Rakshak (step 5).** The explainer opens. "Half a second after the trip it estimates the shortfall from the rate of fall, predicts the dip, and asks for the minimum relief. Here is the list it chose and why."
6. **Real networks (step 6).** Split screen. "With 1.5 s delay and 40 % of commands lost, central control is too late on the left. On the right, pre-armed appliances react locally in a quarter of a second."
7. **Evidence (step 7).** Then open Results and Methods if asked.

Keep **Explore** for questions: set "Command delay" to 2 s and compare policies live.

## Likely evaluator questions

- **"Is this real RVCE data?"**
  - Geometry and names are from OpenStreetMap, checked against the architects' key plan in the NAAC submission. Google's view is real photogrammetry.
  - Energy is a BEE benchmark calibrated to NAAC totals, not metered. Metered data would replace it directly (`data/rvce/overrides.json`).
- **"Why not just use AUFLS?"** AUFLS is the last line of defence. It cuts every customer on a feeder, including critical ones. Rakshak acts before it, with appliances people agreed to share.
- **"Did you invent formulas?"** No. Every model is a published one: the SFR model, swing equation, knapsack, SAIFI counting, the ETP model and SPS arming. The table above and `docs/methods.md` give each source.
- **"How do you know the predictor is right?"** It is calibrated on two Indian events with leave-one-out testing (error ≤ 0.007 Hz). The paper also reports sensitivity: with inertia underestimated by 30 %, AUFLS operated in 2 of 10 seeds.
- **"What happens if the network fails?"** That is experiment E2 and Story step 6: the hybrid's local trigger needs no message at event time.
- **"Isn't this what Tata Power does?"** See "How it differs from Tata Power and AutoGrid" above: different timescale, objective and control problem.
- **"What are the limits?"**
  - single-area frequency, with no voltage or power flow;
  - benchmark loads;
  - simulated households;
  - no field trial.

  The README lists these.

## Older documents

`architecture.md`, `model_evidence.md`, `verification_audit.md`, `presentation_guide.md`, `research_insights.md` and `feature_transfer.md` describe Phase 2 and are kept for history.
