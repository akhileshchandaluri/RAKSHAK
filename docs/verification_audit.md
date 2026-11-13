# Rakshak verification audit

The audit covers Rakshak's Python simulation, API, inventory and serial bridge, the browser views and controls, benchmark runners, and ESP32 reference source. The bundled Three.js distribution and the separate comparison repository are third-party inputs.

## Defects corrected

| Area | Finding and correction |
| --- | --- |
| Backup and restoration | A protected compressor could restart immediately after the feeder returned even if its backup ran out moments earlier. Backup exhaustion now records the interruption time. Backup consumption uses the protected devices actually running. |
| Continuity metrics | Medical offline device-minutes now count requested medical devices even when the approved priority is below critical. Critical unserved energy remains a separate metric. |
| Inventory | SQLite connections now close deterministically. Conflicting reviews use insertion order, so requests submitted in the same second are handled correctly. Editing an approved device now preserves its catalog type. |
| Reviewer API | Credential comparison handles UTF-8 input without a type error. |
| Browser | Selecting a building without critical demand clears the prior continuity chart history. |
| ESP32 helper | The fan signature covered 4–10 W, but the outer threshold suppressed a normal 5 W transition. Both rising and falling steps now use the lower bound. The helper is separate from the active relay controller. |

## Comparison with published Indian grid events

| Event | Observations | Implication |
| --- | --- | --- |
| Rajasthan, 15 May 2023 | 7,120 MW generation loss, 49.40 Hz nadir after about 9 s, 4,529 MW combined reported flat-frequency and rate-of-change relay relief. | The first-stage threshold matches. Actual relief was about half the reported 8,988 MW Stage I design quantity. [NERPC minutes, B.10(B)](https://nerpc.gov.in/wp-content/uploads/2023/10/Minutes-of-the-61-260620230506.pdf) |
| Khavda, 13 May 2026 | About 8,963 MW generation loss, 49.39 Hz nadir and 5,880 MW reported AUFLS relief. The committee recorded feeder non-operation associated with relay delay. | A single fixed relay dwell and modeled feeder blocks omit operational variability. [ERLDC event briefing](https://erpc.gov.in/meetings/multiple-document/download/eyJpdiI6IjVCYVVIY25hTWJ3b3BuUUxKcHYyQ3c9PSIsInZhbHVlIjoiZjBpNDQ1Ty9SZkR5MnJ3MGhFd2JVUT09IiwibWFjIjoiMTk0NmI2NTIzNjE2Yjg1MDAwMmE4MzViMThmN2I1YjYyMDQzMGJiMDg3NWM5YjE5YjkzYzZmNDI2YzFkMjhmNyIsInRhZyI6IiJ9) · [ERPC protection discussion](https://www.erpc.gov.in/meetings/multiple-document/download/eyJpdiI6ImZ1RVpWY3U3ZE5UNk9DMnNnQ2hDaHc9PSIsInZhbHVlIjoiVDlFcUZqVVRlRWNkR1RyN09aRk9jdz09IiwibWFjIjoiYWEyMGZjMzc2ZTMzODAzNDgyMzY3MzlkMDRiZjdlNTAxNDQxNmExNjdmOWZmM2M3NjY5M2IyYTU4OTc2Y2M4MyIsInRhZyI6IiJ9) |

The Evidence page and `GET /api/field-check` run a 40-second sensitivity check with Reference AUFLS, default inertia and governor, and each event's reported pre-event frequency as the initial equilibrium. Normalizing the reported MW losses by assumed 200 and 250 GW bases gives nadirs of 49.828–49.857 Hz for Rajasthan and 49.759–49.797 Hz for Khavda, with zero simulated trips. The observed dips are 0.369–0.457 Hz deeper than predicted. The bases are assumptions and the generation loss is applied as a step. The published event summaries establish this discrepancy without identifying a unique set of inertia, reserve and relay settings.

Quantitative field validation requires timestamped frequency and net power, event-time demand, generation response and feeder relay operation. Feeder-level service predictions additionally require measured appliance availability, interruption response, backup transfer and restart pickup. Household ratings in the evidence register remain representative inputs. The wired ESP32 relay test requires an attached board and isolated proxy loads. The audit host exposed no serial ports.

## Checks run

- 23 Python tests including the closed-form swing equation, timestep comparison, energy balance, backup exhaustion, inventory review, and serial heartbeat parsing.
- 40 scenario and sensitivity runs using the shared four-mode engine.
- Chrome showcase and approval workflows, including the 12-building inventory, local fault, mobile inspector, reviewer authorization, and frozen inventory revision.
- Host C++ compile and execution for the edge NILM helper using a minimal Arduino math stub. The target sketch still requires an Arduino ESP32 build. Physical behavior requires a connected board.
- 600 refreshed paired simulations and both four-mode Chrome views. The two views retain all numeric results and highlight improvements in green.
