# Literature check (20 November 2026)

Searches were web searches (arXiv full text where reachable, abstracts and publisher pages otherwise). IEEE Xplore and Scopus were not queried directly; do one pass there before submission using the queries at the end.

## What is already published (cite, do not claim)

| Idea | Prior work | Note |
|---|---|---|
| Appliances / demand response to avoid triggering UFLS | Wang, Tang, Li, Li, Li, Ni, "Coordinated Scheme of Under-Frequency Load Shedding with Intelligent Appliances in a Cyber Physical Power System," *Energies* 9(8):630, 2016, doi:10.3390/en9080630 | Intelligent appliances replace part of passive UFLS; cyber-physical framing. Closest prior work. Full text not read (publisher blocked automated access); read before submission. |
| Same | "Demand Response an Alternative Solution to Prevent Load Shedding Triggering" (ResearchGate 280258923) | Emergency DR keeps frequency above the AUFLS threshold using smart-meter information. Authors and venue to be confirmed. |
| Frequency-responsive appliances in the field | PNNL Olympic Peninsula / Grid Friendly Appliance demonstrations (e.g. PNNL-23764, 2014) | Water heaters and dryers shed below 59.95 Hz; owners rarely noticed. |
| Disturbance size from the swing equation for adaptive UFLS | V. V. Terzija, "Adaptive underfrequency load shedding based on the magnitude of the disturbance estimation," IEEE TPWRS 21(3):1260–1266, 2006 | Our deficit estimate is this idea; cite it. |
| SFR model to size the minimum load shed | Elzawawy et al., 2019 (analytic SFR + GA, offline); Soroudi/Keane (discretised frequency model, GA) | Feeder-level shed amounts, offline. |
| Model-based adaptive UFLS minimising load shed | Elsaadany, Ali, Pandey, Almassalkhi, "AC-aware Optimization Framework for Under-Frequency Load Shedding," arXiv:2501.03020, 2025 | Periodically re-optimises UFLS relay set-points (MILP) with a reduced-order model incl. governor limits. **Reports that SFR-based set-points underestimated required shedding at reduced inertia** — a threat to our validity. |
| Fast frequency response to keep the nadir above UFLS | Panagi et al., "Dynamic and Risk-Aware Procurement of Fast Frequency Response from Electric Vehicles and Heat Pumps," arXiv:2611.24026, 2026 | Day-ahead procurement of FFR capacity from EV/heat-pump fleets (Cyprus). |
| Appliance / smart-meter UFLS in microgrids | Xu, Paduani, Xiao, Song, Lubkeman, Lu, arXiv:2309.01278, 2023 | Progressive, per-phase appliance shedding for reserve management. |
| Decentralised frequency-responsive loads | Short et al., IEEE TPWRS 2007; Molina-García et al., IEEE TPWRS 2011 | Our edge baseline. |
| Local RoCoF-triggered load response | NESO Enhanced Frequency Control Capability (EFCC); RoCoF-based disconnection studies for Continental Europe | Local triggering on RoCoF is established; site tuning is a known issue. |
| Pre-armed actions, local triggering | Special protection schemes, Anderson & LeReverend, IEEE TPWRS 1996 | Structural precedent for our hybrid. |

## What we did not find (the defensible contribution)

1. **Online, appliance-level minimum relief from a limiter-aware nadir prediction.** Prior work sizes feeder-level UFLS (offline or by periodic set-point updates). We size *appliance* relief online every 0.5 s, and select appliances by a lexicographic covering knapsack: customers interrupted, then guaranteed deferred energy (power × compressor lockout), then thermal/charging slack.
2. **Pre-armed nested appliance sets per contingency level with model-derived RoCoF triggers.** Local RoCoF triggering and SPS pre-arming are each established; arming *nested minimum-relief appliance sets* computed by the nadir predictor, and quantifying robustness to command latency and loss against central dispatch, was not found.
3. **Indian calibration.** Leave-one-event-out calibration of primary-response gain on two Indian events and an India-focused comparison against the SRPC AUFLS reference.

The claim in the paper is therefore the combination (1)–(3), not "appliances to prevent UFLS."

## Threats to validity raised by the literature

- Elsaadany et al. (2025): SFR-type models can underestimate required relief at low inertia because they omit AC network effects. Our results are within an SFR plant, so prediction and plant share the same structure; a higher-fidelity plant is needed to test this.
- Local RoCoF measurement needs site-specific tuning (EFCC); our devices measure noise-free simulated frequency.

## Queries to run on IEEE Xplore / Scopus before submission

- ("under-frequency load shedding" OR UFLS) AND (appliance OR "demand response") AND (nadir OR prediction)
- ("load shedding" OR "demand response") AND ("pre-armed" OR "special protection") AND (household OR residential)
- ("frequency nadir" AND "demand response" AND (knapsack OR "integer programming"))
- India AND ("load shedding" OR AUFLS) AND ("demand response" OR "smart meter")

Sources: [Energies 2016](https://www.mdpi.com/1996-1073/9/8/630), [DR to prevent load shedding](https://www.researchgate.net/publication/280258923_Demand_Response_an_Alternative_Solution_to_Prevent_Load_Shedding_Triggering), [Terzija 2006](https://ieeexplore.ieee.org/document/1664962/authors), [Elzawawy 2019](https://www.iaras.org/filedownloads/ijc/2019/006-0005(2019).pdf), [arXiv:2501.03020](https://arxiv.org/abs/2501.03020), [arXiv:2611.24026](https://arxiv.org/abs/2611.24026), [arXiv:2309.01278](https://arxiv.org/abs/2309.01278), [PNNL-23764](https://www.pnnl.gov/main/publications/external/technical_reports/PNNL-23764.pdf), [NESO EFCC](https://www.neso.energy/document/142876/download).
