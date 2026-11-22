# Methods, sources and open verification items

This file lists every model in Rakshak v2, the source it comes from, and what is a declared assumption. No formula in the code is original to this project: the contributions are how published models are combined (minimum relief from a predicted nadir, lexicographic customer-first selection, pre-armed graded relief with local RoCoF triggers) and the experiments.

## Models and their sources

| Component | Code | Source |
|---|---|---|
| Frequency dynamics: reheat System Frequency Response model | `backend/grid_engine.py` (`plant="sfr_reheat"`) | P. M. Anderson, M. Mirheydar, IEEE TPWRS 5(3), 1990 |
| Closed-form nadir and exact step response | `backend/nadir_predictor.py` | Same paper; state-space matrix exponential for the overdamped case |
| Governor dead band, reserve limits | `GridConfig` | Standard limiters (Kundur 1994) |
| Deficit estimate from the swing equation | `SFRObserver.update` | Kundur 1994; Inoue et al., IEEE TPWRS 12(1), 1997 |
| 20 samples/s frequency stream | `NadirPredictivePolicy.on_step` | IEEE C37.118.1-2011 permitted reporting rates |
| Covering 0/1 knapsack, HiGHS | `policies/np_mrd.py` | Kellerer, Pferschy, Pisinger, *Knapsack Problems*, 2004 |
| Customers interrupted as first objective | same | Customer count of SAIFI, IEEE Std 1366-2022 |
| Thermal slack ordering | same, `thermal.py` | Priority stack, N. Lu, IEEE TSG 3(3), 2012 |
| EV laxity | `thermal.py` | Xu, Pan, Tong, IEEE TAC 61(12), 2016 |
| First-order ETP thermal model, C and R | `thermal.py` | Callaway 2009; Mathieu, Koch, Callaway, IEEE TPWRS 28(1), 2013 |
| Pre-armed relief, local trigger | `policies/hybrid.py` | Special protection schemes, Anderson & LeReverend, IEEE TPWRS 11(3), 1996 |
| Decentralised relays (baseline) | `policies/edge.py` | Molina-García, Bouffard, Kirschen, IEEE TPWRS 26(1), 2011; Short et al. 2007 |
| AUFLS stages and relief | `GridConfig` | SRPC task-force report, 27 March 2024 |
| Normal frequency band 49.90–50.05 Hz | UI, restoration | CERC IEGC |
| Fairness | `simulation.service_metrics` | Jain, Chiu, Hawe, DEC-TR-301, 1984 |
| Building energy | `tools/build_campus.py` | BEE/UNDP-GEF *Energy benchmarks for Commercial Buildings*, Moderate zone |
| Campus outline, names, floors, roads, rail, river | `data/rvce/source/osm_rvce_area.json` | OpenStreetMap contributors, ODbL 1.0 (campus way 55685638) |
| Campus layout check | `data/rvce/source/keyplan_registration.json` | ACE Group Architects key plan, RVCE NAAC SSR Criterion 4.1.1 |
| Unmapped footprints | `data/rvce/source/` | Microsoft Global ML Building Footprints, release 2026-02-03, ODbL 1.0 |
| Documented campus facts | `data/rvce/facts.json` | RVCE NAAC SSR (built-up 67,721 m², hostels 38,659 m²), BESCOM SRTPV report (500 kW, 8 buildings), RVCE website |
| Photoreal scene | `frontend/app/world.js` | Google Photorealistic 3D Tiles via Cesium ion (asset 2275207); not stored |
| Satellite ground | `backend/main.py` `/api/imagery` | Esri World Imagery (Maxar, Earthstar Geographics); streamed, not stored |
| Sun position | `frontend/app/solar.js` | NOAA GML general solar position equations; azimuth by Meeus, eq. 13.5 |

## Declared assumptions (swept or flagged)

- Governor gain K_m = 0.15 from leave-one-event-out calibration (`benchmarks/results/calibration.json`). Both events were arrested by AUFLS, so this is an upper bound, not an identified value. K_m = 0.95 is reported as sensitivity (experiment E5).
- System base 200 or 250 GW and H = 4 or 5 s in calibration; H swept over 2–5 s in experiments.
- Protection margin 0.05 Hz above AUFLS stage 1 (swept in E3); restore hysteresis 0.05 Hz.
- Hybrid ladder 0.01–0.30 pu in 0.01 steps; 0.25 s local detection; arming resent every 1 s, re-planned every 60 s.
- Communication: latency, jitter and loss are abstract parameters (E2), not a model of a specific network.
- Campus: floors not tagged in OSM use a per-use default; 3.5 m per floor; use is classified from the building name; energy floor area is scaled to the NAAC totals (factor about 0.54 for non-hostel RVCE buildings, 2.14 for hostels, because OSM floor tags undercount hostel storeys); AC is 30 % of average demand; streetlight spacing is illustrative.
- Building demand uses annual averages; time of day changes lighting only.

## To verify before submission

1. Exact titles, dates and URLs of the SRPC, NERPC and ERPC event documents (`paper/references.bib`, entries marked VERIFY).
2. A Grid-India frequency-response-characteristic report for one of the events, to cite next to the calibration.
3. Page numbers of all journal references.
4. BEE water-heater standby-loss figure used for the geyser time constant (`backend/thermal.py`).
5. BEE default AC temperature notification (24 °C) reference.
6. RVCE campus: floor counts not tagged in OSM, health centre and server rooms (`data/rvce/overrides.json`), and if possible metered annual kWh to replace the benchmark.
7. A systematic related-work search (IEEE Xplore, Scopus) for "nadir-constrained demand response", "AUFLS appliance", "pre-armed load shedding demand side", to confirm novelty claims.

## Overrides format

`data/rvce/overrides.json` maps a building key (`way/<id>`, `relation/<id>` or `msb/<n>`, stored as `key` in `campus.json`) to verified data:

```json
{
  "way/132994721": {"name": "Administrative Block", "use": "admin", "floors": 4, "campus": true},
  "msb/242": {"floors": 5}
}
```

Uses: `academic`, `library`, `admin`, `hostel`, `canteen`, `health`, `other`. Then run `python tools/build_campus.py`.
