// Small SVG chart helpers: crisp at any size and themed through CSS variables.
const NS = "http://www.w3.org/2000/svg";
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function el(name, attrs = {}, parent) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  parent?.appendChild(node);
  return node;
}

export function ticks(min, max, count = 5) {
  const span = max - min || 1;
  const raw = span / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const out = [];
  for (let v = Math.ceil(min / step - 1e-9) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
  return { values: out, step };
}
const fmt = (v, step) => v.toFixed(Math.max(0, -Math.floor(Math.log10(step) + 1e-9)));

/**
 * Line chart.
 * series: [{ points: [[x,y]], color, label, dash, width, area }]
 * refs: [{ y, label, color }]  marks: [{ x, color, label }]  cursor: x
 */
export function lineChart(host, { series, refs = [], marks = [], cursor = null, x0, x1, y0, y1,
  xLabel = "", yLabel = "", height = 200, legend = true }) {
  const width = Math.max(240, host.clientWidth || 360);
  const legendRows = legend ? Math.ceil(series.filter((s) => s.label).reduce((w, s) => w + 30 + s.label.length * 6.2, 0) / Math.max(200, (host.clientWidth || 360) - 8)) : 0;
  const pad = { l: 46, r: 12, t: legend ? 12 + 15 * legendRows : 10, b: 30 };
  const pts = series.flatMap((s) => s.points);
  if (!pts.length) { host.innerHTML = ""; return; }
  x0 ??= Math.min(...pts.map((p) => p[0])); x1 ??= Math.max(...pts.map((p) => p[0]));
  if (x1 <= x0) x1 = x0 + 1;
  const ys = pts.map((p) => p[1]).concat(refs.map((r) => r.y));
  y0 ??= Math.min(...ys); y1 ??= Math.max(...ys);
  if (y1 - y0 < 1e-9) { y0 -= 0.5; y1 += 0.5; }
  const X = (v) => pad.l + ((v - x0) / (x1 - x0)) * (width - pad.l - pad.r);
  const Y = (v) => height - pad.b - ((v - y0) / (y1 - y0)) * (height - pad.t - pad.b);
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img" });
  const grid = el("g", { class: "grid" }, svg);
  const yt = ticks(y0, y1, 4), xt = ticks(x0, x1, 6);
  for (const v of yt.values) {
    el("line", { x1: pad.l, x2: width - pad.r, y1: Y(v), y2: Y(v) }, grid);
    el("text", { x: pad.l - 6, y: Y(v) + 4, "text-anchor": "end" }, svg).textContent = fmt(v, yt.step);
  }
  for (const v of xt.values) el("text", { x: X(v), y: height - pad.b + 16, "text-anchor": "middle" }, svg).textContent = fmt(v, xt.step);
  if (xLabel) el("text", { x: width - pad.r, y: height - 2, "text-anchor": "end", class: "axis-label" }, svg).textContent = xLabel;
  if (yLabel) el("text", { x: pad.l - 6, y: pad.t + 4, "text-anchor": "end", class: "axis-label", dy: "-12" }, svg).textContent = yLabel;
  const clipId = "c" + Math.random().toString(36).slice(2);
  el("rect", { x: pad.l, y: pad.t, width: width - pad.l - pad.r, height: height - pad.t - pad.b }, el("clipPath", { id: clipId }, el("defs", {}, svg)));
  const plot = el("g", { "clip-path": `url(#${clipId})` }, svg);
  for (const r of refs) {
    if (r.y < y0 || r.y > y1) continue;
    el("line", { x1: pad.l, x2: width - pad.r, y1: Y(r.y), y2: Y(r.y), stroke: r.color || css("--faint"), "stroke-dasharray": "4 4" }, plot);
    if (r.label) {
      const t = el("text", { x: width - pad.r - 4, y: Y(r.y) - 4, "text-anchor": "end" }, plot);
      t.textContent = r.label; t.style.fill = r.color || css("--muted");
    }
  }
  for (const m of marks) el("line", { x1: X(m.x), x2: X(m.x), y1: pad.t, y2: height - pad.b, stroke: m.color || css("--faint"), "stroke-dasharray": "2 3" }, plot);
  for (const s of series) {
    if (!s.points.length) continue;
    const d = s.points.map(([x, y], i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join("");
    if (s.area) el("path", { d: `${d}L${X(s.points.at(-1)[0])},${Y(y0)}L${X(s.points[0][0])},${Y(y0)}Z`, fill: s.color, opacity: 0.08 }, plot);
    el("path", { d, fill: "none", stroke: s.color, "stroke-width": s.width || 2, "stroke-dasharray": s.dash || "",
      "stroke-linejoin": "round", "stroke-linecap": "round" }, plot);
  }
  if (cursor != null && cursor >= x0 && cursor <= x1) el("line", { x1: X(cursor), x2: X(cursor), y1: pad.t, y2: height - pad.b, stroke: css("--text"), "stroke-opacity": 0.35 }, plot);
  if (legend) {
    let lx = 4, ly = 10;
    for (const s of series.filter((s) => s.label)) {
      const w = 30 + s.label.length * 6.2;
      if (lx + w > width && lx > 4) { lx = 4; ly += 15; }
      el("line", { x1: lx, x2: lx + 14, y1: ly, y2: ly, stroke: s.color, "stroke-width": 2.5, "stroke-dasharray": s.dash || "" }, svg);
      const t = el("text", { x: lx + 19, y: ly + 4 }, svg); t.textContent = s.label; t.style.fill = css("--text");
      lx += w;
    }
  }
  host.replaceChildren(svg);
}

/** Grouped bars. groups: [{label, values:{key: number}}], keys: [{key,label,color}] */
export function barChart(host, { groups, keys, yLabel = "", height = 240 }) {
  const width = Math.max(260, host.clientWidth || 480);
  const pad = { l: 46, r: 10, t: 30, b: 40 };
  const max = Math.max(1e-9, ...groups.flatMap((g) => keys.map((k) => g.values[k.key] ?? 0)));
  const yt = ticks(0, max, 4);
  const yMax = Math.max(yt.values.at(-1), max);
  const Y = (v) => height - pad.b - (v / yMax) * (height - pad.t - pad.b);
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, height });
  const grid = el("g", { class: "grid" }, svg);
  for (const v of yt.values) {
    el("line", { x1: pad.l, x2: width - pad.r, y1: Y(v), y2: Y(v) }, grid);
    el("text", { x: pad.l - 6, y: Y(v) + 4, "text-anchor": "end" }, svg).textContent = fmt(v, yt.step);
  }
  if (yLabel) el("text", { x: 4, y: pad.t - 12, class: "axis-label" }, svg).textContent = yLabel;
  const gw = (width - pad.l - pad.r) / groups.length;
  const bw = Math.min(18, (gw - 12) / keys.length);
  groups.forEach((g, gi) => {
    const gx = pad.l + gi * gw + (gw - bw * keys.length) / 2;
    keys.forEach((k, ki) => {
      const v = g.values[k.key] ?? 0;
      const r = el("rect", { x: gx + ki * bw + 1, y: Y(v), width: bw - 2, height: Math.max(0, height - pad.b - Y(v)), rx: 2, fill: k.color }, svg);
      el("title", {}, r).textContent = `${k.label}: ${v.toFixed(2)}`;
    });
    g.label.split("\n").forEach((line, i) => {
      el("text", { x: pad.l + gi * gw + gw / 2, y: height - pad.b + 15 + i * 13, "text-anchor": "middle" }, svg).textContent = line;
    });
  });
  let lx = pad.l;
  for (const k of keys) {
    el("rect", { x: lx, y: 4, width: 10, height: 10, rx: 2, fill: k.color }, svg);
    const t = el("text", { x: lx + 14, y: 13 }, svg); t.textContent = k.label; t.style.fill = css("--text");
    lx += 26 + k.label.length * 6.2;
  }
  host.replaceChildren(svg);
}

export function sparkline(svg, points, { x0, x1, y0, y1, color, refs = [] }) {
  const w = svg.clientWidth || 600, h = svg.clientHeight || 26;
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  const X = (v) => ((v - x0) / (x1 - x0)) * w, Y = (v) => h - ((v - y0) / (y1 - y0)) * h;
  const parts = refs.map((r) => `<line x1="0" x2="${w}" y1="${Y(r.y)}" y2="${Y(r.y)}" stroke="${r.color}" stroke-dasharray="3 3" stroke-width="1"/>`);
  const d = points.map(([x, y], i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(y).toFixed(1)}`).join("");
  parts.push(`<path d="${d}" fill="none" stroke="${color}" stroke-width="1.6"/>`);
  svg.innerHTML = parts.join("");
}
