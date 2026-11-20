// Three.js (r128, global THREE) scene of the RVCE campus and its surroundings.
// Geometry comes from data/rvce/campus.json (Microsoft ML footprints, local metres).
import { solarPosition, dayOfYear, CIVIL_TWILIGHT_DEG } from "./solar.js";

const THREE = window.THREE;
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

function extrude(polygon, height, base = 0) {
  const shape = new THREE.Shape(polygon.map(([x, y]) => new THREE.Vector2(x, y)));
  const geo = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false });
  // Shape is in the x/y plane extruded along +z; map to world x (east), y (up), -z (north).
  geo.rotateX(-Math.PI / 2);
  geo.translate(0, base, 0);
  return geo;
}

function mergeGeometries(geometries) {
  let count = 0;
  const parts = geometries.map((g) => (g.index ? g.toNonIndexed() : g));
  parts.forEach((g) => (count += g.attributes.position.count));
  const position = new Float32Array(count * 3), normal = new Float32Array(count * 3);
  let offset = 0;
  for (const g of parts) {
    g.computeVertexNormals();
    position.set(g.attributes.position.array, offset * 3);
    normal.set(g.attributes.normal.array, offset * 3);
    offset += g.attributes.position.count;
  }
  const merged = new THREE.BufferGeometry();
  merged.setAttribute("position", new THREE.BufferAttribute(position, 3));
  merged.setAttribute("normal", new THREE.BufferAttribute(normal, 3));
  return merged;
}

export class CampusScene {
  constructor(canvas, campus, { onSelect } = {}) {
    this.canvas = canvas;
    this.campus = campus;
    this.onSelect = onSelect;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(42, 1, 1, 6000);
    this.target = new THREE.Vector3(60, 0, 40);
    this.orbit = { radius: 720, theta: -0.75, phi: 0.92 };
    this.meshes = new Map();       // campus building id -> mesh
    this.state = new Map();        // campus building id -> live state
    this.selected = null;
    this.night = 0;
    this.buildWorld();
    this.bindControls();
    this.setTimeOfDay(13);
    this.resize();
    window.addEventListener("resize", () => this.resize());
    const tick = () => { this.render(); requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  buildWorld() {
    const { scene, campus } = this;
    scene.fog = new THREE.Fog(0x0f1216, 1400, 3200);
    this.hemi = new THREE.HemisphereLight(0xdfe8f5, 0x3a3428, 0.55);
    scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight(0xfff3e0, 1.0);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    Object.assign(this.sun.shadow.camera, { left: -520, right: 520, top: 520, bottom: -520, near: 10, far: 2600 });
    this.sun.shadow.bias = -0.0008;
    scene.add(this.sun, this.sun.target);

    this.groundMat = new THREE.MeshStandardMaterial({ color: new THREE.Color(css("--ground") || "#26302a"), roughness: 1 });
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), this.groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);

    // Roads
    const roadMat = new THREE.MeshStandardMaterial({ color: 0x2c2f34, roughness: 0.95 });
    const markMat = new THREE.MeshBasicMaterial({ color: 0xc9c9c0 });
    for (const road of campus.roads) {
      const [[x0, y0], [x1, y1]] = road.points;
      const len = Math.hypot(x1 - x0, y1 - y0), ang = Math.atan2(y1 - y0, x1 - x0);
      const strip = new THREE.Mesh(new THREE.PlaneGeometry(len, road.width_m), roadMat);
      strip.rotation.x = -Math.PI / 2; strip.rotation.z = ang;
      strip.position.set((x0 + x1) / 2, 0.05, -(y0 + y1) / 2);
      strip.receiveShadow = true;
      scene.add(strip);
      for (let s = 0; s < len; s += 12) {
        for (const lane of [-1.75, 1.75]) {
          const dash = new THREE.Mesh(new THREE.PlaneGeometry(4, 0.15), markMat);
          dash.rotation.x = -Math.PI / 2; dash.rotation.z = ang;
          const px = x0 + Math.cos(ang) * s - Math.sin(ang) * lane, py = y0 + Math.sin(ang) * s + Math.cos(ang) * lane;
          dash.position.set(px, 0.08, -py);
          scene.add(dash);
        }
      }
    }

    // Elongated corridor structure (inferred metro alignment)
    const corridor = new THREE.Mesh(extrude(campus.corridor.polygon, 2.2, 8.5),
      new THREE.MeshStandardMaterial({ color: 0x6d7178, roughness: 0.8 }));
    corridor.castShadow = corridor.receiveShadow = true;
    scene.add(corridor);

    // Context buildings merged into one mesh
    const context = campus.buildings.filter((b) => !b.campus);
    const merged = mergeGeometries(context.map((b) => extrude(b.polygon, b.height_m)));
    this.contextMat = new THREE.MeshStandardMaterial({ color: new THREE.Color(css("--b-context") || "#3a414c"), roughness: 0.9 });
    const contextMesh = new THREE.Mesh(merged, this.contextMat);
    contextMesh.castShadow = contextMesh.receiveShadow = true;
    scene.add(contextMesh);

    // Campus buildings: individual meshes for picking and live colouring
    this.baseColor = new THREE.Color(css("--b-normal") || "#8fb3e8");
    const edgeMat = new THREE.LineBasicMaterial({ color: 0x0b0d10, transparent: true, opacity: 0.35 });
    for (const b of campus.buildings.filter((x) => x.campus)) {
      const geo = extrude(b.polygon, b.height_m);
      const mat = new THREE.MeshStandardMaterial({ color: this.baseColor.clone(), roughness: 0.7, metalness: 0.05,
        emissive: new THREE.Color(0xffc977), emissiveIntensity: 0 });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.castShadow = mesh.receiveShadow = true;
      mesh.userData.building = b;
      mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), edgeMat));
      this.scene.add(mesh);
      this.meshes.set(b.id, mesh);
    }

    // Streetlights: instanced poles and lantern heads; ground glow at night
    const n = campus.streetlights.length;
    const pole = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.12, 0.16, 9, 6),
      new THREE.MeshStandardMaterial({ color: 0x55595f }), n);
    this.lampMat = new THREE.MeshBasicMaterial({ color: 0x40382a });
    const lamp = new THREE.InstancedMesh(new THREE.BoxGeometry(1.2, 0.3, 0.5), this.lampMat, n);
    // Soft radial pool of light under each lantern.
    const tex = document.createElement("canvas");
    tex.width = tex.height = 64;
    const g = tex.getContext("2d"), grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grad.addColorStop(0, "rgba(255,214,150,1)"); grad.addColorStop(0.45, "rgba(255,200,120,0.35)"); grad.addColorStop(1, "rgba(255,190,110,0)");
    g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
    this.glowMat = new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(tex), transparent: true, opacity: 0,
      depthWrite: false, blending: THREE.AdditiveBlending });
    const glow = new THREE.InstancedMesh(new THREE.CircleGeometry(9, 24), this.glowMat, n);
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), flat = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0));
    campus.streetlights.forEach(([x, y], i) => {
      m.compose(new THREE.Vector3(x, 4.5, -y), q, new THREE.Vector3(1, 1, 1)); pole.setMatrixAt(i, m);
      m.compose(new THREE.Vector3(x, 9.1, -y), q, new THREE.Vector3(1, 1, 1)); lamp.setMatrixAt(i, m);
      m.compose(new THREE.Vector3(x, 0.12, -y), flat, new THREE.Vector3(1, 1, 1)); glow.setMatrixAt(i, m);
    });
    pole.castShadow = true;
    scene.add(pole, lamp, glow);
  }

  setTimeOfDay(hours, date = new Date()) {
    const { lat, lon } = this.campus.origin;
    const sp = solarPosition(dayOfYear(date), hours, lat, lon, 5.5);
    this.sunInfo = sp;
    const el = sp.elevationDeg * Math.PI / 180, az = sp.azimuthDeg * Math.PI / 180;
    const r = 1500;
    // azimuth clockwise from north: east = +x, north = -z
    this.sun.position.set(r * Math.cos(el) * Math.sin(az), Math.max(20, r * Math.sin(el)), -r * Math.cos(el) * Math.cos(az));
    const day = Math.max(0, Math.min(1, (sp.elevationDeg + 4) / 14));
    this.sun.intensity = 1.05 * day;
    this.hemi.intensity = 0.3 + 0.3 * day;
    this.night = sp.elevationDeg < CIVIL_TWILIGHT_DEG ? 1 : sp.elevationDeg < 0 ? 0.5 : 0;
    const sky = new THREE.Color().setHSL(0.6, 0.35, 0.05 + 0.13 * day);
    this.scene.background = sky;
    this.scene.fog.color = sky;
    this.glowMat.opacity = 0.55 * this.night;
    this.lampMat.color.set(this.night ? 0xffe2a8 : 0x40382a);
    this.applyColors();
    return sp;
  }

  update(campusStates) {
    for (const s of campusStates || []) this.state.set(s.id, s);
    this.applyColors();
  }

  applyColors() {
    const warn = new THREE.Color(css("--warn")), crit = new THREE.Color(css("--crit"));
    for (const [id, mesh] of this.meshes) {
      const s = this.state.get(id);
      const mat = mesh.material;
      let color = this.baseColor, lit = 1;
      if (s && !s.energized) { color = crit; lit = 0; }
      else if (s && s.ac_curtailed) color = warn;
      mat.color.copy(color);
      if (id === this.selected) mat.color.offsetHSL(0, 0, 0.12);
      mat.emissiveIntensity = this.night * 0.12 * lit;
    }
  }

  // ------------------------------------------------------------ controls
  bindControls() {
    const el = this.canvas;
    let drag = null;
    el.addEventListener("contextmenu", (e) => e.preventDefault());
    el.addEventListener("pointerdown", (e) => {
      el.setPointerCapture(e.pointerId);
      drag = { x: e.clientX, y: e.clientY, button: e.button, moved: 0, pan: e.button === 2 || e.shiftKey };
    });
    el.addEventListener("pointermove", (e) => {
      if (!drag) return this.hover(e);
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      drag.x = e.clientX; drag.y = e.clientY; drag.moved += Math.abs(dx) + Math.abs(dy);
      if (drag.pan) {
        const s = this.orbit.radius / 900;
        const right = new THREE.Vector3(Math.cos(this.orbit.theta), 0, -Math.sin(this.orbit.theta));
        const fwd = new THREE.Vector3(Math.sin(this.orbit.theta), 0, Math.cos(this.orbit.theta));
        this.target.addScaledVector(right, -dx * s).addScaledVector(fwd, -dy * s);
      } else {
        this.orbit.theta -= dx * 0.005;
        this.orbit.phi = Math.min(1.45, Math.max(0.12, this.orbit.phi - dy * 0.004));
      }
    });
    el.addEventListener("pointerup", (e) => {
      if (drag && drag.moved < 5) this.pick(e);
      drag = null;
    });
    el.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.orbit.radius = Math.min(2200, Math.max(60, this.orbit.radius * Math.exp(e.deltaY * 0.001)));
    }, { passive: false });
    // two-finger pinch
    const touches = new Map();
    el.addEventListener("touchstart", (e) => { for (const t of e.changedTouches) touches.set(t.identifier, t); }, { passive: true });
    el.addEventListener("touchmove", (e) => {
      if (e.touches.length === 2) {
        const [a, b] = e.touches;
        const d = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
        if (this.pinch) this.orbit.radius = Math.min(2200, Math.max(60, this.orbit.radius * this.pinch / d));
        this.pinch = d;
      }
    }, { passive: true });
    el.addEventListener("touchend", () => { this.pinch = null; }, { passive: true });
    this.raycaster = new THREE.Raycaster();
  }

  resetView(plan = false) {
    this.target.set(60, 0, 40);
    Object.assign(this.orbit, plan ? { radius: 820, theta: 0, phi: 0.13 } : { radius: 720, theta: -0.75, phi: 0.92 });
  }

  ray(e) {
    const r = this.canvas.getBoundingClientRect();
    const p = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(p, this.camera);
    const hit = this.raycaster.intersectObjects([...this.meshes.values()], false)[0];
    return hit ? hit.object.userData.building : null;
  }

  hover(e) {
    const b = this.ray(e);
    this.hovered = b ? b.id : null;
    this.canvas.style.cursor = b ? "pointer" : "grab";
  }

  pick(e) {
    const b = this.ray(e);
    this.select(b ? b.id : null);
  }

  select(id) {
    this.selected = id;
    this.applyColors();
    this.onSelect?.(id == null ? null : this.meshes.get(id).userData.building);
  }

  screenPosition(b) {
    const v = new THREE.Vector3(b.centroid[0], b.height_m + 3, -b.centroid[1]).project(this.camera);
    const r = this.canvas.getBoundingClientRect();
    return { x: (v.x + 1) / 2 * r.width, y: (1 - v.y) / 2 * r.height, visible: v.z < 1 };
  }

  resize() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  render() {
    if (!this.canvas.offsetParent) return;
    const { radius, theta, phi } = this.orbit;
    this.camera.position.set(
      this.target.x + radius * Math.sin(phi) * Math.sin(theta),
      this.target.y + radius * Math.cos(phi),
      this.target.z + radius * Math.sin(phi) * Math.cos(theta));
    this.camera.lookAt(this.target);
    this.sun.target.position.copy(this.target);
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (this.renderer.domElement.width !== Math.round(w * this.renderer.getPixelRatio())) this.resize();
    this.renderer.render(this.scene, this.camera);
    this.onFrame?.();
  }
}
