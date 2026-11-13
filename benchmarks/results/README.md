# Paired experiment results

Executed 600 runs: seeds 0–19, 0/25/50/75/100% enrollment, 10/18/35% generation loss, reference AUFLS and AUFLS + Rakshak. Each run lasts 270 simulated seconds. Approved inventory revision 0.

| Loss | Enrollment | Nadir reference / Rakshak (Hz) | Critical unserved reference / Rakshak (Wh) | Total requested service unserved reference / Rakshak (Wh) |
| --- | --- | --- | --- | --- |
| 10% | 0% | 49.577 / 49.577 | 0.00 / 0.00 | 0.0 / 0.0 |
| 10% | 25% | 49.577 / 49.577 | 0.00 / 0.00 | 0.0 / 352.7 |
| 10% | 50% | 49.577 / 49.577 | 0.00 / 0.00 | 0.0 / 339.7 |
| 10% | 75% | 49.577 / 49.577 | 0.00 / 0.00 | 0.0 / 335.6 |
| 10% | 100% | 49.577 / 49.577 | 0.00 / 0.00 | 0.0 / 341.4 |
| 18% | 0% | 49.279 / 49.279 | 5.26 / 5.26 | 1613.1 / 1613.1 |
| 18% | 25% | 49.279 / 49.573 | 5.26 / 0.00 | 1613.1 / 5419.1 |
| 18% | 50% | 49.279 / 49.576 | 5.26 / 0.00 | 1613.1 / 5076.7 |
| 18% | 75% | 49.279 / 49.576 | 5.26 / 0.00 | 1613.1 / 3461.6 |
| 18% | 100% | 49.279 / 49.576 | 5.26 / 0.00 | 1613.1 / 2108.2 |
| 35% | 0% | 48.795 / 48.795 | 8.49 / 8.49 | 7487.5 / 7487.5 |
| 35% | 25% | 48.795 / 49.108 | 8.49 / 4.99 | 7487.5 / 8398.5 |
| 35% | 50% | 48.795 / 49.185 | 8.49 / 4.13 | 7487.5 / 12571.2 |
| 35% | 75% | 48.795 / 49.185 | 8.49 / 4.70 | 7487.5 / 11576.3 |
| 35% | 100% | 48.795 / 49.185 | 8.49 / 5.12 | 7487.5 / 9947.4 |

The data show a service trade-off. Larger shortages generally improve in frequency nadir and critical unserved energy, while total requested service curtailment frequently increases. At 10% loss, the controller produces additional curtailment without improving the nadir. At zero enrollment the policies agree. These outcomes do not establish blanket superiority or justify deployment.

The metric includes temporarily deferred requested running watts. It is not a prediction of permanently lost household energy, because catch-up charging and thermal states are not modeled. The default heuristic should be compared with comfort/energy-constrained policies in subsequent research.

Individual runs are in `paired_runs.csv`. `summary.json` reports paired differences and 95% Student-t intervals (19 degrees of freedom). These describe modeled seed variation only. Raw outcomes include trips, restoration peak, pause duration, backup energy and relief shortfall.

Research conclusion: a defensible demonstration of the cost of prioritizing critical services, not proof of an optimal or universally beneficial controller.
