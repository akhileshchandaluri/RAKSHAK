# Comparison-project feature decisions

| Capability | Original Rakshak revision | Decision |
| --- | --- | --- |
| Appliance state constraints | Minimum on/off time, lockout, consent and interruption-budget state | Adopted concept, implemented in shared Python engine |
| Priority-aware control | Four service classes independent of consent and current state | Corrected conflation of uncontrolled and essential loads |
| Feeder protection baseline | Fixed scaled blocks, 5/6/7/7% AUFLS, protected-facility exclusions | Corrected; short frequency-only ADMS is not imported |
| Participation analysis | 20 paired seeds at five enrollment levels, CSV + interval summary | Adopted concept with deterministic hashed enrollment |
| Decision audits | Trigger, target, eligible/actual watts, excluded loads and restore holds | Adopted and exposed in telemetry |
| Repeatable runs | Frozen inventory revision, common engine for UI and CLI | Adopted |
| NILM | Separate synthetic signature-fit estimate; never determines priority | Retained with limitations |
| Hardware bridge | Existing serial adapter retained; no measured validation claimed | Outside simulation-first acceptance |
| PV cloud drop | No physical irradiance/inverter model | Excluded from showcase |
| Communications fault bus | No demonstrated end-to-end transport validation | Not claimed as implemented |
| Review workflow | Persistent SQLite requests, credential-protected review | New local application capability |

The comparison repository is left unchanged. Feature labels alone are not treated as evidence of physical accuracy.
