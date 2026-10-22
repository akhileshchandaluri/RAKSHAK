import { useMemo, useState } from "react";
import { Activity, AlertTriangle, BatteryCharging, Building2, Cable, CheckCircle2, Circle, CloudSun, Power, RotateCcw, ShieldCheck, Wifi, WifiOff, Zap } from "lucide-react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import CityScene from "./components/CityScene";
import { useTwin } from "./hooks/useTwin";
import type { Building } from "./types";

function Metric({ label, value, unit, tone = "" }: { label: string; value: string; unit?: string; tone?: string }) {
  return <div className="metric">
    <div className="metric-label">{label}</div>
    <div className={`metric-value ${tone}`}>{value}<span>{unit}</span></div>
  </div>;
}

export default function App() {
  const { state, history, connected, setScenario, setBalancing } = useTwin();
  const [selectedId, setSelectedId] = useState<string | null>("home-01");
  const [busy, setBusy] = useState(false);

  const selected: Building | undefined = useMemo(
    () => state?.buildings.find(b => b.id === selectedId), [state, selectedId]
  );

  async function runScenario(s: string) {
    setBusy(true);
    try { await setScenario(s); } finally { setBusy(false); }
  }

  if (!state) return <main className="loading"><div className="pulse-dot" />Connecting to Rakshak simulation...</main>;

  const frequencyTone = state.frequencyHz <= state.shedThresholdHz ? "danger" : state.frequencyHz < 49.85 ? "warning" : "good";
  const onCount = state.buildings.flatMap(b => b.appliances).filter(a => a.status === "on").length;
  const totalCount = state.buildings.reduce((sum, b) => sum + b.appliances.length, 0);

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand-mark"><ShieldCheck size={23} /></div>
      <div className="brand-copy"><strong>RAKSHAK</strong><span>GRID-EDGE DIGITAL TWIN</span></div>
      <div className="topbar-spacer" />
      <div className={`connection ${connected ? "connected" : ""}`}>
        {connected ? <Wifi size={15} /> : <WifiOff size={15} />}
        {connected ? "SIMULATION LIVE" : "RECONNECTING"}
      </div>
      <div className="mode-chip"><Circle size={7} fill="currentColor" /> SIMULATION MODE</div>
    </header>

    <section className="metrics-row">
      <Metric label="GRID FREQUENCY" value={state.frequencyHz.toFixed(2)} unit="Hz" tone={frequencyTone} />
      <Metric label="GENERATION" value={state.generationKw.toFixed(1)} unit="kW" />
      <Metric label="ACTIVE LOAD" value={state.buildings.flatMap(b => b.appliances).filter(a => a.status === "on").reduce((sum, a) => sum + a.powerKw, 0).toFixed(1)} unit="kW" />
      <Metric label="ACTIVE APPLIANCES" value={`${onCount}/${totalCount}`} />
      <Metric label="SHED ACTIONS" value={String(state.metrics.shedActions)} tone={state.metrics.shedActions ? "warning" : ""} />
    </section>

    <section className="main-grid">
      <div className="scene-panel panel">
        <div className="panel-heading">
          <div><span className="eyebrow">LIVE ENVIRONMENT</span><h2>Smart City Twin</h2></div>
          <span className="view-hint"><span className="live-dot" /> REAL-TIME STATE</span>
        </div>
        <div className="scene-wrap">
          <CityScene state={state} selectedId={selectedId} onSelect={setSelectedId} />
          <div className="scene-overlay scene-overlay-left">
            <span className="overlay-label">GRID STATUS</span>
            <strong className={frequencyTone}>{state.frequencyHz <= state.shedThresholdHz ? "DISTURBANCE" : "NOMINAL"}</strong>
            <span>{state.disturbance.replace("_", " ").toUpperCase()}</span>
          </div>
          <div className="scene-overlay scene-overlay-right">
            <span className="overlay-label">CONNECTED LOADS</span>
            <strong>{onCount} <small>/ {totalCount}</small></strong>
            <span>{state.buildings.length} BUILDINGS</span>
          </div>
          <div className="scene-legend">
            <span><i className="legend-green" /> Active feeder</span>
            <span><i className="legend-red" /> Under-frequency risk</span>
          </div>
        </div>
        <div className="scene-footer"><span><Cable size={14}/> Drag to orbit · Scroll to zoom · Click a building to inspect</span><span>3D TWIN · V1.0</span></div>
      </div>

      <aside className="right-column">
        <div className="panel control-panel">
          <div className="panel-heading compact"><div><span className="eyebrow">SCENARIO LAB</span><h2>Disturbance controls</h2></div><Activity size={19} /></div>
          <p className="panel-description">Inject a grid event and observe the virtual city and controller response.</p>
          <button className="scenario-button" disabled={busy} onClick={() => runScenario("solar_drop")}><span className="scenario-icon"><CloudSun size={18}/></span><span><strong>Solar generation drop</strong><small>Simulate a sudden renewable supply loss</small></span><Zap size={16} /></button>
          <button className="scenario-button" disabled={busy} onClick={() => runScenario("demand_surge")}><span className="scenario-icon amber"><BatteryCharging size={18}/></span><span><strong>Demand surge</strong><small>Simulate a sudden increase in demand</small></span><Zap size={16} /></button>
          <button className="scenario-button" disabled={busy} onClick={() => runScenario("none")}><span className="scenario-icon neutral"><RotateCcw size={18}/></span><span><strong>Reset scenario</strong><small>Return to baseline conditions</small></span></button>
          <div className="toggle-row"><div><strong>Automatic balancing</strong><small>Allow simulated load shedding</small></div><button className={`toggle ${state.balancingEnabled ? "on" : ""}`} onClick={() => setBalancing(!state.balancingEnabled)} aria-label="Toggle automatic balancing"><span /></button></div>
          <div className="threshold-note"><AlertTriangle size={14}/><span>Demo threshold: {state.shedThresholdHz.toFixed(1)} Hz · Critical tier is protected in the control policy.</span></div>
        </div>

        <div className="panel selected-panel">
          <div className="panel-heading compact"><div><span className="eyebrow">ASSET INSPECTOR</span><h2>{selected?.name ?? "Select a building"}</h2></div><Building2 size={18}/></div>
          {selected ? <div className="appliance-list">{selected.appliances.map(a => <div className="appliance-row" key={a.id}>
            <span className={`appliance-state ${a.status}`} />
            <div className="appliance-info"><strong>{a.name}</strong><small>Tier {a.tier} · {a.powerKw.toFixed(1)} kW</small></div>
            <span className={`status-pill ${a.status}`}>{a.status.toUpperCase()}</span>
          </div>)}</div> : <p className="panel-description">Select a building in the 3D scene to inspect its appliances.</p>}
          <div className="tier-legend"><span><i className="tier-critical"/> Critical</span><span><i className="tier-essential"/> Essential</span><span><i className="tier-flex"/> Deferrable</span></div>
        </div>
      </aside>
    </section>

    <section className="bottom-grid">
      <div className="panel chart-panel">
        <div className="panel-heading compact"><div><span className="eyebrow">GRID TELEMETRY</span><h2>Frequency response</h2></div><span className="chart-unit">Hz</span></div>
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history.map((p, i) => ({ ...p, seconds: i }))} margin={{ top: 8, right: 12, bottom: 0, left: -20 }}>
              <CartesianGrid stroke="#263744" strokeDasharray="3 4" />
              <XAxis dataKey="seconds" tick={{ fill: "#7f91a2", fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis domain={[48, 50.5]} tick={{ fill: "#7f91a2", fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "#101c28", border: "1px solid #2a3a48", borderRadius: 8 }} labelStyle={{ color: "#9eafbf" }} />
              <Line type="monotone" dataKey="frequencyHz" name="Frequency" stroke="#4de0b2" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="panel events-panel">
        <div className="panel-heading compact"><div><span className="eyebrow">SYSTEM ACTIVITY</span><h2>Event log</h2></div><Power size={18}/></div>
        <div className="event-list">{state.events.slice(0, 6).map((event, i) => <div className="event-row" key={`${event}-${i}`}><CheckCircle2 size={14}/><span>{event}</span></div>)}</div>
      </div>
    </section>

    <footer className="footer"><span>TEAM RAKSHAK · EDGE-INTELLIGENT GRID RESILIENCE</span><span>SIMULATION ONLY · NOT FOR REAL GRID CONTROL</span></footer>
  </main>;
}