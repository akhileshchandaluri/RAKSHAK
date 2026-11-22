# Architecture

> **Historical (Phase 2).** This describes the first version. For the current system see [whats_new.md](whats_new.md) and [methods.md](methods.md).

The browser showcase and its four-mode comparison enable seeded appliance sessions on the 12 visible buildings. The other buildings supply steady background demand, and the published paired benchmark uses its original fixed-demand protocol. The accelerated sessions are illustrative and shared across policies. Unmanaged has no emergency dispatch. Reference AUFLS switches feeder blocks. Rakshak modes also dispatch enrolled flexible appliances. Independent facility backup and common outcome metrics are retained across modes.

Browser controls → validated ScenarioRequest → per-WebSocket SimulationController → FleetSimulator + GridEngine → snapshots, electrical continuity, audit log and charts.

The benchmark CLI and HTTP benchmark invoke the same controller and model. InventoryStore supplies a frozen approved revision at run creation/reset. SQLite holds requests and review history in ignored `var/`; reviewer mutations require a server-validated credential. Browser rendering uses text escaping for submitted names and validated HTTP(S) evidence links.

The frequency model integrates a single-area swing equation, governor and turbine with RK4 at 50 ms. Fleet dispatch and appliance maintenance operate at 500 ms. NumPy arrays cache device state and aggregate active power; cache rebuilds follow dispatch, maintenance and feeder state changes. Startup transients contribute to grid demand. Service-energy metrics integrate requested operating watts. Each building's idealized finite backup supplies its protected bus only.

Modes: unmanaged experimental control; reference AUFLS; reference AUFLS plus staggered Rakshak; reference AUFLS plus bulk-restart ablation. All modes share scenario parameters, seeded inventories, reference demand and backup. The local fault model opens a physical feeder independently of the frequency-control policy. AUFLS stage blocks are allocated once at initialization and exclude dedicated protected facilities. Detailed allocation assumptions are in model_evidence.md.

Live clients own their simulation, so changing one client's mode does not modify another's run. A benchmark freezes one inventory snapshot across all modes. A stale inventory revision returns HTTP 409. The browser stops advancing simulation when disconnected; a new connection starts a new run. No alternate browser physics engine is used.

The optional HIL serial adapter remains a separate experimental interface. This revision does not validate real appliances or electrical protection equipment. Public deployment would require a full identity/authorization system, transport security, operational limits and site-specific engineering.

Local feeder-fault scenarios assume an ideal stiff upstream grid at 50 Hz. Upstream import follows the surviving demand. This isolates continuity and backup behavior from the area-frequency experiments. The local fault therefore cannot be interpreted as a national frequency disturbance. The backup-exhaustion preset starts with 0.25 minutes of protected-facility backup and an 85 s fault.
