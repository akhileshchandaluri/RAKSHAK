// Minimal canvas charts with real axes, units and reference lines. No dependencies.

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function prepare(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const c = canvas.getContext("2d");
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, w, h);
  return { c, w, h };
}

function niceTicks(min, max, count = 5) {
  const span = max - min || 1;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || 10 * mag;
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

/**
 * series: [{ points: [[x, y]...], color, label, width, dash }]
 * refs:   [{ y, label, color, dash }]   horizontal reference lines
 * marks:  [{ x, label, color }]         vertical markers
 */
export function lineChart(canvas, { series, refs = [], marks = [], xLabel = "", yLabel = "", yMin, yMax, xMin, xMax, compact = false }) {
  const { c, w, h } = prepare(canvas);
  const pad = compact ? { l: 46, r: 12, t: 10, b: 22 } : { l: 54, r: 16, t: 14, b: 34 };
  const all = series.flatMap((s) => s.points);
  if (!all.length) return;
  const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]).concat(refs.map((r) => r.y));
  const x0 = xMin ?? Math.min(...xs), x1 = xMax ?? Math.max(...xs, x0 + 1);
  let y0 = yMin ?? Math.min(...ys), y1 = yMax ?? Math.max(...ys);
  if (y1 - y0 < 1e-6) { y0 -= 0.5; y1 += 0.5; }
  const X = (v) => pad.l + ((v - x0) / (x1 - x0)) * (w - pad.l - pad.r);
  const Y = (v) => h - pad.b - ((v - y0) / (y1 - y0)) * (h - pad.t - pad.b);
  const muted = css("--muted"), line = css("--line"), text = css("--text");
  c.font = `11px ${css("--mono") || "monospace"}`;
  c.lineWidth = 1;
  // grid + y ticks
  for (const t of niceTicks(y0, y1, compact ? 3 : 5)) {
    c.strokeStyle = line; c.beginPath(); c.moveTo(pad.l, Y(t)); c.lineTo(w - pad.r, Y(t)); c.stroke();
    c.fillStyle = muted; c.textAlign = "right"; c.textBaseline = "middle";
    c.fillText(t.toFixed(Math.max(0, -Math.floor(Math.log10(Math.abs((y1 - y0) / 5) || 1)))), pad.l - 6, Y(t));
  }
  // x ticks
  for (const t of niceTicks(x0, x1, compact ? 6 : 8)) {
    c.fillStyle = muted; c.textAlign = "center"; c.textBaseline = "top";
    c.fillText(String(+t.toFixed(1)), X(t), h - pad.b + 5);
  }
  if (!compact) {
    c.fillStyle = muted; c.textAlign = "right"; c.textBaseline = "alphabetic";
    c.fillText(xLabel, w - pad.r, h - 4);
    c.save(); c.translate(12, pad.t + 4); c.rotate(-Math.PI / 2); c.textAlign = "right"; c.fillText(yLabel, 0, 0); c.restore();
  }
  c.save();
  c.beginPath(); c.rect(pad.l, pad.t, w - pad.l - pad.r, h - pad.t - pad.b); c.clip();
  for (const r of refs) {
    if (r.y < y0 || r.y > y1) continue;
    c.strokeStyle = r.color || muted; c.setLineDash(r.dash || [4, 4]);
    c.beginPath(); c.moveTo(pad.l, Y(r.y)); c.lineTo(w - pad.r, Y(r.y)); c.stroke();
    c.setLineDash([]);
    c.fillStyle = r.color || muted; c.textAlign = "left"; c.textBaseline = "bottom";
    if (r.label) c.fillText(r.label, pad.l + 4, Y(r.y) - 2);
  }
  for (const m of marks) {
    c.strokeStyle = m.color || muted; c.setLineDash([2, 3]);
    c.beginPath(); c.moveTo(X(m.x), pad.t); c.lineTo(X(m.x), h - pad.b); c.stroke(); c.setLineDash([]);
  }
  for (const s of series) {
    if (!s.points.length) continue;
    c.strokeStyle = s.color || css("--accent"); c.lineWidth = s.width || 1.75; c.setLineDash(s.dash || []);
    c.beginPath();
    s.points.forEach(([x, y], i) => (i ? c.lineTo(X(x), Y(y)) : c.moveTo(X(x), Y(y))));
    c.stroke(); c.setLineDash([]);
  }
  c.restore();
  // legend
  if (!compact && series.length > 1) {
    let lx = pad.l + 8;
    c.textAlign = "left"; c.textBaseline = "middle";
    for (const s of series) {
      c.fillStyle = s.color; c.fillRect(lx, pad.t + 6, 10, 2);
      c.fillStyle = text; c.fillText(s.label, lx + 14, pad.t + 7);
      lx += c.measureText(s.label).width + 30;
    }
  }
}

/** groups: [{ label, values: [{ key, value }] }], keys: [{ key, label, color }] */
export function barChart(canvas, { groups, keys, yLabel = "", log = false }) {
  const { c, w, h } = prepare(canvas);
  const pad = { l: 54, r: 12, t: 28, b: 40 };
  const max = Math.max(1e-9, ...groups.flatMap((g) => g.values.map((v) => v.value)));
  const yMax = niceTicks(0, max, 4).at(-1) || max;
  const Y = (v) => h - pad.b - (v / yMax) * (h - pad.t - pad.b);
  const muted = css("--muted"), line = css("--line"), text = css("--text");
  c.font = `11px ${css("--mono") || "monospace"}`;
  for (const t of niceTicks(0, yMax, 4)) {
    c.strokeStyle = line; c.beginPath(); c.moveTo(pad.l, Y(t)); c.lineTo(w - pad.r, Y(t)); c.stroke();
    c.fillStyle = muted; c.textAlign = "right"; c.textBaseline = "middle"; c.fillText(String(+t.toFixed(2)), pad.l - 6, Y(t));
  }
  const gw = (w - pad.l - pad.r) / groups.length;
  const bw = Math.min(22, (gw - 14) / keys.length);
  groups.forEach((g, gi) => {
    const gx = pad.l + gi * gw + (gw - bw * keys.length) / 2;
    keys.forEach((k, ki) => {
      const v = g.values.find((x) => x.key === k.key)?.value ?? 0;
      c.fillStyle = k.color; c.fillRect(gx + ki * bw, Y(v), bw - 2, h - pad.b - Y(v));
    });
    c.fillStyle = muted; c.textAlign = "center"; c.textBaseline = "top";
    c.fillText(g.label, pad.l + gi * gw + gw / 2, h - pad.b + 6);
  });
  let lx = pad.l;
  c.textAlign = "left"; c.textBaseline = "middle";
  for (const k of keys) {
    c.fillStyle = k.color; c.fillRect(lx, 10, 10, 10);
    c.fillStyle = text; c.fillText(k.label, lx + 14, 15);
    lx += c.measureText(k.label).width + 28;
  }
  c.save(); c.fillStyle = muted; c.translate(12, h - pad.b); c.rotate(-Math.PI / 2); c.textAlign = "left"; c.fillText(yLabel, 0, 0); c.restore();
}

export const palette = () => ({
  accent: css("--accent"), ok: css("--ok"), warn: css("--warn"), crit: css("--crit"),
  protected: css("--protected"), muted: css("--muted"), text: css("--text"),
  series: ["#5b9cf5", "#4cb782", "#e0a43a", "#a888f0", "#e5534b", "#8d96a5"],
});
