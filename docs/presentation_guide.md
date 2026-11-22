# EL demonstration sequence

> **Historical (Phase 2).** This describes the first version. For the current system see [whats_new.md](whats_new.md) and [methods.md](methods.md).

1. Start the server and show **LIVE SIMULATION**. Identify the 50 Hz reference, normal band and separate AUFLS/experimental DR thresholds. Open the evidence register.
2. Select normal operation. Explain that protected priority does not mean an appliance continuously consumes its nameplate watts.
3. Select generation loss and Compare All Modes. Compare reference AUFLS with the same AUFLS plus Rakshak. Both have identical backup and inventories. Describe actual metrics, including any unfavorable result.
4. Select a normal home, a medical home, clinic, cold-chain facility and water service. Inspect all installed devices. Explain ordinary versus flexible consumption, consent and constraints. The water-service capacities are assumptions.
5. Select local feeder fault. Critical priorities cannot energize a disconnected home. The clinic uses finite backup. Select backup exhaustion to demonstrate unserved electrical energy. No patient vital signs or vaccine temperatures are simulated.
6. Compare staggered and bulk restoration with the same scenario. Observe grid demand, frequency and compressor lockout. Interruption budgets can be exceeded if safe restoration is unavailable, and that limitation must be reported.
7. Submit an appliance request, open the separate reviewer page, enter the server credential, and record a reasoned decision. Reset to use the new inventory revision. An approval is not evidence that a real device is medically essential.
8. Show the paired-seed CSV and confidence intervals, including zero-participation and small-contingency cases. Explain the difference between numerical verification, model assumptions and real-world validation.

Candidate research question: when does consent-aware appliance control reduce unserved service energy or feeder trips without unacceptable interruption and restoration behavior, compared with a shared protection baseline?

Claim a reproducible simulation testbed. Do not claim universal blackout prevention, patient safety, established novelty, a validated digital twin, or publication readiness solely from this demo. Prior work already establishes frequency-responsive loads and staggered recovery. Physical calibration and a systematic related-work review are future research requirements.
