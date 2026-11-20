// 3D world of the RVCE campus and its surroundings (three.js r160, bundled offline).
// Geometry: data/rvce/campus.json (Microsoft ML footprints, local metres; x east, y north).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { GTAOPass } from "three/addons/postprocessing/GTAOPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { Sky } from "three/addons/objects/Sky.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { solarPosition, dayOfYear } from "./solar.js";

const FLOOR = 3.5;          // m per storey (declared in tools/build_campus.py)
const BAY = 3.2;            // m per window bay (illustrative facade rhythm)
const STATE_TINT = {
  0: new THREE.Color(1, 1, 1),
  1: new THREE.Color(1.0, 0.68, 0.22),     // appliance paused
  2: new THREE.Color(0.22, 0.24, 0.28),    // feeder open
  3: new THREE.Color(0.78, 0.68, 1.0),     // protected load on backup
};

// ---------------------------------------------------------------- textures
function facadeTextures() {
  const size = 128;
  const make = (draw) => {
    const c = document.createElement("canvas");
    c.width = c.height = size;
    draw(c.getContext("2d"));
    const t = new THREE.CanvasTexture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(1 / BAY, 1 / FLOOR);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 4;
    return t;
  };
  const win = { x: 22, y: 30, w: 84, h: 62 };
  const map = make((g) => {
    g.fillStyle = "#ffffff"; g.fillRect(0, 0, size, size);
    g.fillStyle = "#f1efe9"; g.fillRect(0, 0, size, 8);                  // slab edge
    const grad = g.createLinearGradient(0, win.y, 0, win.y + win.h);
    grad.addColorStop(0, "#5d6b7a"); grad.addColorStop(1, "#2f3944");
    g.fillStyle = grad; g.fillRect(win.x, win.y, win.w, win.h);         // glazing
    g.fillStyle = "rgba(255,255,255,.18)"; g.fillRect(win.x, win.y, win.w, 6);
    g.fillStyle = "#d9d6cf"; g.fillRect(win.x - 3, win.y + win.h, win.w + 6, 5); // sill
    g.fillRect(win.x + win.w / 2 - 1.5, win.y, 3, win.h);                 // mullion
  });
  const emissive = make((g) => {
    g.fillStyle = "#000"; g.fillRect(0, 0, size, size);
    g.fillStyle = "#ffd9a0"; g.fillRect(win.x + 2, win.y + 2, win.w - 4, win.h - 4);
  });
  emissive.colorSpace = THREE.SRGBColorSpace;
  const rough = make((g) => {
    g.fillStyle = "#e0e0e0"; g.fillRect(0, 0, size, size);
    g.fillStyle = "#404040"; g.fillRect(win.x, win.y, win.w, win.h);    // glass is smoother
  });
  rough.colorSpace = THREE.NoColorSpace;
  return { map, emissive, rough };
}

function noiseTexture(base, spread, repeat, size = 256) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const img = g.createImageData(size, size);
  const [r, gr, b] = base;
  for (let i = 0; i < size * size; i++) {
    const n = (Math.random() - 0.5) * spread;
    img.data[i * 4] = r + n; img.data[i * 4 + 1] = gr + n; img.data[i * 4 + 2] = b + n; img.data[i * 4 + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(repeat, repeat);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// Multiply window emission by the vertex colour so cut buildings go dark at night.
function emissiveFollowsVertexColor(material) {
  material.onBeforeCompile = (shader) => {
    shader.fragmentShader = shader.fragmentShader.replace(
      "#include <emissivemap_fragment>",
      "#include <emissivemap_fragment>\n#ifdef USE_COLOR\n totalEmissiveRadiance *= smoothstep(0.3, 0.9, vColor.g);\n#endif");
  };
}

// ---------------------------------------------------------------- geometry
function extrude(polygon, height) {
  const shape = new THREE.Shape(polygon.map(([x, y]) => new THREE.Vector2(x, y)));
  const geo = new THREE.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false });
  geo.rotateX(-Math.PI / 2);           // (x, y, z) -> (x, z, -y): north = -z, up = +y
  return geo;
}

// Split an ExtrudeGeometry into roof (group 0 caps) and walls (group 1 sides).
function splitExtrude(geo) {
  const g = geo.index ? geo.toNonIndexed() : geo;
  const parts = { roof: [], walls: [] };
  for (const group of geo.groups) {
    const sub = new THREE.BufferGeometry();
    for (const name of ["position", "normal", "uv"]) {
      const a = g.attributes[name];
      sub.setAttribute(name, new THREE.BufferAttribute(a.array.slice(group.start * a.itemSize, (group.start + group.count) * a.itemSize), a.itemSize));
    }
    (group.materialIndex === 0 ? parts.roof : parts.walls).push(sub);
  }
  return {
    roof: parts.roof.length > 1 ? mergeGeometries(parts.roof) : parts.roof[0],
    walls: parts.walls.length > 1 ? mergeGeometries(parts.walls) : parts.walls[0],
  };
}

function pointInPolygon(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function convexHull(points) {
  const p = points.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [], upper = [];
  for (const q of p) { while (lower.length >= 2 && cross(lower.at(-2), lower.at(-1), q) <= 0) lower.pop(); lower.push(q); }
  for (const q of p.reverse()) { while (upper.length >= 2 && cross(upper.at(-2), upper.at(-1), q) <= 0) upper.pop(); upper.push(q); }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

function inflate(poly, d) {
  const cx = poly.reduce((s, p) => s + p[0], 0) / poly.length, cy = poly.reduce((s, p) => s + p[1], 0) / poly.length;
  return poly.map(([x, y]) => { const l = Math.hypot(x - cx, y - cy) || 1; return [x + (x - cx) / l * d, y + (y - cy) / l * d]; });
}

// ---------------------------------------------------------------- world
export class World {
  constructor(canvas, campus) {
    this.canvas = canvas;
    this.campus = campus;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.9;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, 2, 9000);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = 1.42;
    this.controls.minDistance = 40;
    this.controls.maxDistance = 2200;
    this.controls.target.set(60, 0, -40);
    this.camera.position.set(-420, 430, 520);
    this.tex = facadeTextures();
    this.night = 0;
    this.split = null;
    this.labels = [];
    this.campusMeshes = new Map();       // campus footprint id -> mesh
    this.fleetToCampus = new Map();      // fleet index -> campus footprint id
    this.householdRanges = [];           // fleet index -> {walls:[start,count], roof:[...]}
    this.raycaster = new THREE.Raycaster();
    this.build();
    this.setupPost();
    this.setTimeOfDay(13);
    this.resize();
    new ResizeObserver(() => this.resize()).observe(canvas);
    canvas.addEventListener("pointerdown", (e) => (this.down = [e.clientX, e.clientY]));
    canvas.addEventListener("pointerup", (e) => {
      if (this.down && Math.hypot(e.clientX - this.down[0], e.clientY - this.down[1]) < 5) this.onPick?.(this.pick(e));
    });
    canvas.addEventListener("pointermove", (e) => {
      const hit = this.pick(e);
      canvas.style.cursor = hit ? "pointer" : "grab";
      this.onHover?.(hit);
    });
    const loop = () => { this.frame(); requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
  }

  // -------------------------------------------------------------- build
  build() {
    const { scene, campus } = this;
    // Sky and lights
    this.sky = new Sky();
    this.sky.scale.setScalar(8000);
    Object.assign(this.sky.material.uniforms, {});
    this.sky.material.uniforms.turbidity.value = 6;
    this.sky.material.uniforms.rayleigh.value = 1.6;
    this.sky.material.uniforms.mieCoefficient.value = 0.005;
    this.sky.material.uniforms.mieDirectionalG.value = 0.8;
    scene.add(this.sky);
    this.hemi = new THREE.HemisphereLight(0xdde7f5, 0x5d5446, 0.6);
    scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight(0xfff1dc, 2.4);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(4096, 4096);
    Object.assign(this.sun.shadow.camera, { left: -650, right: 650, top: 650, bottom: -650, near: 50, far: 4000 });
    this.sun.shadow.bias = -0.0004;
    this.sun.shadow.normalBias = 0.6;
    scene.add(this.sun, this.sun.target);
    this.moon = new THREE.DirectionalLight(0x9fb4ff, 0.0);
    this.moon.position.set(300, 800, -200);
    scene.add(this.moon);
    this.stars = this.makeStars();
    scene.add(this.stars);
    scene.fog = new THREE.Fog(0xcfd8e3, 1600, 4200);

    // Ground: urban base, campus lawn over the campus hull
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(6000, 6000),
      new THREE.MeshStandardMaterial({ map: noiseTexture([142, 140, 134], 20, 60), roughness: 1 }));
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
    const campusPts = campus.buildings.filter((b) => b.campus).flatMap((b) => b.polygon);
    this.campusHull = inflate(convexHull(campusPts), 22);
    const lawnShape = new THREE.Shape(this.campusHull.map(([x, y]) => new THREE.Vector2(x, y)));
    const lawn = new THREE.Mesh(new THREE.ShapeGeometry(lawnShape),
      new THREE.MeshStandardMaterial({ map: noiseTexture([104, 126, 84], 26, 0.08), roughness: 1 }));
    lawn.geometry.rotateX(-Math.PI / 2);
    lawn.position.y = 0.05;
    lawn.receiveShadow = true;
    scene.add(lawn);
    // Paved aprons around campus buildings (illustrative hardscape).
    const aprons = campus.buildings.filter((b) => b.campus).map((b) => {
      const g = new THREE.ShapeGeometry(new THREE.Shape(inflate(b.polygon, 7).map(([x, y]) => new THREE.Vector2(x, y))));
      g.rotateX(-Math.PI / 2); g.translate(0, 0.09, 0);
      return g;
    });
    const apron = new THREE.Mesh(mergeGeometries(aprons), new THREE.MeshStandardMaterial({ map: noiseTexture([196, 192, 182], 16, 0.12), roughness: 0.95 }));
    apron.receiveShadow = true;
    scene.add(apron);
    const edge = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(this.campusHull.map(([x, y]) => new THREE.Vector3(x, 0.3, -y))),
      new THREE.LineBasicMaterial({ color: 0xe8e4d8 }));
    scene.add(edge);

    // Roads and the elevated metro corridor
    const asphalt = new THREE.MeshStandardMaterial({ map: noiseTexture([58, 60, 64], 14, 40), roughness: 0.95 });
    const paint = new THREE.MeshBasicMaterial({ color: 0xe9e6dc });
    for (const road of campus.roads) {
      const [[x0, y0], [x1, y1]] = road.points;
      const len = Math.hypot(x1 - x0, y1 - y0), ang = Math.atan2(y1 - y0, x1 - x0);
      const strip = new THREE.Mesh(new THREE.PlaneGeometry(len, road.width_m), asphalt);
      strip.rotation.set(-Math.PI / 2, 0, ang);
      strip.position.set((x0 + x1) / 2, 0.08, -(y0 + y1) / 2);
      strip.receiveShadow = true;
      scene.add(strip);
      const dashes = [];
      for (let s = 6; s < len; s += 14) for (const lane of [-1.75, 1.75]) {
        const d = new THREE.PlaneGeometry(5, 0.18);
        d.rotateX(-Math.PI / 2); d.rotateY(ang);
        d.translate(x0 + Math.cos(ang) * s - Math.sin(ang) * lane, 0.12, -(y0 + Math.sin(ang) * s + Math.cos(ang) * lane));
        dashes.push(d);
      }
      scene.add(new THREE.Mesh(mergeGeometries(dashes), paint));
    }
    this.buildViaduct();

    // Buildings
    const facadeFor = (color) => new THREE.MeshStandardMaterial({
      color, map: this.tex.map, roughnessMap: this.tex.rough, roughness: 0.9, metalness: 0.05,
      emissiveMap: this.tex.emissive, emissive: new THREE.Color(0xffc477), emissiveIntensity: 0 });
    const contextWalls = [], contextRoofs = [];
    const householdWalls = [], householdRoofs = [];
    const households = new Map(campus.households.map((h) => [h.footprint_id, h.fleet_index]));
    this.roofMatCampus = new THREE.MeshStandardMaterial({ color: 0x9db7dc, roughness: 0.85 });
    this.campusFacade = facadeFor(0xf3efe7);
    for (const b of campus.buildings) {
      const geo = extrude(b.polygon, b.height_m);
      if (b.campus) {
        const mesh = new THREE.Mesh(geo, [this.roofMatCampus.clone(), this.campusFacade.clone()]);
        mesh.castShadow = mesh.receiveShadow = true;
        mesh.userData = { building: b, kind: "campus" };
        scene.add(mesh);
        this.campusMeshes.set(b.id, mesh);
        continue;
      }
      const { roof, walls } = splitExtrude(geo);
      if (households.has(b.id)) {
        householdWalls.push({ geo: walls, i: households.get(b.id), b });
        householdRoofs.push({ geo: roof, i: households.get(b.id), b });
      } else {
        contextWalls.push(walls); contextRoofs.push(roof);
      }
    }
    // Context buildings: static
    const ctxFacade = facadeFor(0xe6e1d8);
    const ctxRoof = new THREE.MeshStandardMaterial({ color: 0xb9b5ad, roughness: 0.95 });
    for (const [geos, mat] of [[contextWalls, ctxFacade], [contextRoofs, ctxRoof]]) {
      const m = new THREE.Mesh(mergeGeometries(geos), mat);
      m.castShadow = m.receiveShadow = true;
      scene.add(m);
    }
    this.ctxFacade = ctxFacade;
    // Households: merged, coloured per building through a vertex colour attribute
    const buildMerged = (items, material) => {
      let offset = 0;
      const ranges = [];
      for (const it of items) { ranges.push({ i: it.i, b: it.b, start: offset, count: it.geo.attributes.position.count }); offset += it.geo.attributes.position.count; }
      const geo = mergeGeometries(items.map((it) => it.geo));
      const colors = new Float32Array(offset * 3).fill(1);
      geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      material.vertexColors = true;
      const mesh = new THREE.Mesh(geo, material);
      mesh.castShadow = mesh.receiveShadow = true;
      mesh.userData = { kind: "households", ranges };
      this.scene.add(mesh);
      return { mesh, ranges };
    };
    this.hhFacade = facadeFor(0xeee8dc);
    emissiveFollowsVertexColor(this.hhFacade);
    this.hhWalls = buildMerged(householdWalls, this.hhFacade);
    this.hhRoofs = buildMerged(householdRoofs, new THREE.MeshStandardMaterial({ color: 0xc8b9a6, roughness: 0.9 }));
    this.hhIndex = new Map();
    this.hhWalls.ranges.forEach((r, k) => this.hhIndex.set(r.i, { walls: r, roof: this.hhRoofs.ranges[k] }));

    this.buildTrees();
    this.buildStreetlights();
  }

  buildViaduct() {
    const c = this.campus.corridor;
    const deck = extrude(c.polygon, 1.6);
    deck.translate(0, 9, 0);
    const mat = new THREE.MeshStandardMaterial({ color: 0xbfc3c8, roughness: 0.8 });
    const mesh = new THREE.Mesh(deck, mat);
    mesh.castShadow = mesh.receiveShadow = true;
    this.scene.add(mesh);
    // Pillars along the long axis of the corridor polygon
    const pts = c.polygon;
    let best = null;
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i], b = pts[(i + 1) % pts.length];
      const l = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (!best || l > best.l) best = { a, b, l };
    }
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length, cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    const ux = (best.b[0] - best.a[0]) / best.l, uy = (best.b[1] - best.a[1]) / best.l;
    const pillars = [];
    for (let s = -best.l / 2 + 10; s < best.l / 2; s += 28) {
      const p = new THREE.CylinderGeometry(1.1, 1.3, 9, 10);
      p.translate(cx + ux * s, 4.5, -(cy + uy * s));
      pillars.push(p);
    }
    const pm = new THREE.Mesh(mergeGeometries(pillars), mat);
    pm.castShadow = true;
    this.scene.add(pm);
  }

  buildTrees() {
    // Illustrative landscaping: jittered grid inside the campus hull, clear of buildings.
    const polys = this.campus.buildings.map((b) => b.polygon);
    const near = (x, y) => this.campus.buildings.some((b) => Math.hypot(b.centroid[0] - x, b.centroid[1] - y) < 70 &&
      (pointInPolygon(x, y, b.polygon) || b.polygon.some(([px, py]) => Math.hypot(px - x, py - y) < 6)));
    const xs = this.campusHull.map((p) => p[0]), ys = this.campusHull.map((p) => p[1]);
    const spots = [];
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let x = Math.min(...xs); x < Math.max(...xs); x += 13) {
      for (let y = Math.min(...ys); y < Math.max(...ys); y += 13) {
        const px = x + (rnd() - 0.5) * 10, py = y + (rnd() - 0.5) * 10;
        if (pointInPolygon(px, py, this.campusHull) && !near(px, py) && rnd() < 0.55) spots.push([px, py, 0.7 + rnd() * 0.6]);
      }
    }
    void polys;
    const trunk = new THREE.CylinderGeometry(0.35, 0.5, 4, 6);
    trunk.translate(0, 2, 0);
    const canopy = new THREE.IcosahedronGeometry(3.6, 0);
    canopy.translate(0, 6.2, 0);
    const trunks = new THREE.InstancedMesh(trunk, new THREE.MeshStandardMaterial({ color: 0x6b4f3a, roughness: 1 }), spots.length);
    const crowns = new THREE.InstancedMesh(canopy, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, flatShading: true }), spots.length);
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), color = new THREE.Color();
    spots.forEach(([x, y, s], i) => {
      q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), rnd() * Math.PI);
      m.compose(new THREE.Vector3(x, 0, -y), q, new THREE.Vector3(s, s, s));
      trunks.setMatrixAt(i, m); crowns.setMatrixAt(i, m);
      crowns.setColorAt(i, color.setHSL(0.27 + rnd() * 0.06, 0.45, 0.28 + rnd() * 0.08));
    });
    trunks.castShadow = crowns.castShadow = true;
    this.scene.add(trunks, crowns);
  }

  buildStreetlights() {
    const lights = this.campus.streetlights;
    const n = lights.length;
    const pole = new THREE.CylinderGeometry(0.12, 0.16, 9, 6); pole.translate(0, 4.5, 0);
    const head = new THREE.BoxGeometry(1.4, 0.25, 0.5); head.translate(0, 9.1, 0);
    this.lampMat = new THREE.MeshStandardMaterial({ color: 0x555a60, emissive: new THREE.Color(0xffd7a0), emissiveIntensity: 0 });
    const poles = new THREE.InstancedMesh(pole, new THREE.MeshStandardMaterial({ color: 0x6b7077, roughness: 0.6 }), n);
    const heads = new THREE.InstancedMesh(head, this.lampMat, n);
    const glowTex = (() => {
      const c = document.createElement("canvas"); c.width = c.height = 64;
      const g = c.getContext("2d"), r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
      r.addColorStop(0, "rgba(255,214,150,1)"); r.addColorStop(0.5, "rgba(255,200,120,.35)"); r.addColorStop(1, "rgba(255,190,110,0)");
      g.fillStyle = r; g.fillRect(0, 0, 64, 64);
      return new THREE.CanvasTexture(c);
    })();
    this.glowMat = new THREE.MeshBasicMaterial({ map: glowTex, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending });
    const disc = new THREE.PlaneGeometry(18, 18); disc.rotateX(-Math.PI / 2); disc.translate(0, 0.2, 0);
    const pools = new THREE.InstancedMesh(disc, this.glowMat, n);
    const m = new THREE.Matrix4();
    lights.forEach(([x, y], i) => { m.makeTranslation(x, 0, -y); poles.setMatrixAt(i, m); heads.setMatrixAt(i, m); pools.setMatrixAt(i, m); });
    poles.castShadow = true;
    this.scene.add(poles, heads, pools);
  }

  makeStars() {
    const n = 1500, pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const th = Math.random() * Math.PI * 2, ph = Math.acos(Math.random() * 0.9);
      pos.set([Math.sin(ph) * Math.cos(th) * 5000, Math.cos(ph) * 5000, Math.sin(ph) * Math.sin(th) * 5000], i * 3);
    }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    return new THREE.Points(g, new THREE.PointsMaterial({ color: 0xffffff, size: 2, sizeAttenuation: false, transparent: true, opacity: 0, fog: false }));
  }

  setupPost() {
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    try {
      this.gtao = new GTAOPass(this.scene, this.camera, 1, 1);
      this.gtao.updateGtaoMaterial({ radius: 6, distanceExponent: 1.5, thickness: 2, scale: 1.2, samples: 12 });
      this.composer.addPass(this.gtao);
    } catch (err) {
      this.gtao = null;
    }
    this.composer.addPass(new OutputPass());
    this.quality = true;
  }

  // -------------------------------------------------------------- sun
  setTimeOfDay(hours, date = new Date()) {
    const { lat, lon } = this.campus.origin;
    const sp = solarPosition(dayOfYear(date), hours, lat, lon, 5.5);
    const el = THREE.MathUtils.degToRad(sp.elevationDeg), az = THREE.MathUtils.degToRad(sp.azimuthDeg);
    const dir = new THREE.Vector3(Math.cos(el) * Math.sin(az), Math.sin(el), -Math.cos(el) * Math.cos(az));
    this.sky.material.uniforms.sunPosition.value.copy(dir);
    this.sun.position.copy(dir.clone().multiplyScalar(2000)).add(this.controls.target);
    const day = THREE.MathUtils.clamp((sp.elevationDeg + 3) / 12, 0, 1);
    this.night = sp.elevationDeg < -6 ? 1 : sp.elevationDeg < 2 ? (2 - sp.elevationDeg) / 8 : 0;
    this.sun.intensity = 2.6 * day;
    this.hemi.intensity = 0.12 + 0.55 * day;
    this.moon.intensity = 0.35 * this.night;
    this.renderer.toneMappingExposure = 0.55 + 0.4 * day;
    this.stars.material.opacity = this.night;
    this.scene.fog.color.setHSL(0.6, 0.25, 0.08 + 0.72 * day);
    this.glowMat.opacity = 0.65 * this.night;
    this.lampMat.emissiveIntensity = 3 * this.night;
    this.sunInfo = sp;
    this.applyNight();
    return sp;
  }

  applyNight() {
    const lit = 1.6 * this.night;
    this.hhFacade.emissiveIntensity = lit;
    this.ctxFacade.emissiveIntensity = lit * 0.6;
    for (const mesh of this.campusMeshes.values()) {
      const s = mesh.userData.state ?? 0;
      mesh.material[1].emissiveIntensity = s === 2 ? 0 : lit * (s === 1 ? 0.7 : 1);
    }
  }

  // -------------------------------------------------------------- state
  /** state: Uint8Array over fleet indices; replay: Replay (for index map). */
  applyState(state, replay) {
    if (!state || !replay) return;
    if (!this.fleetToCampus.size || this.indexFor !== replay) {
      this.fleetToCampus = new Map(replay.data.buildings.filter((b) => b.campus_id != null).map((b) => [b.i, b.campus_id]));
      this.indexFor = replay;
    }
    const colorWalls = this.hhWalls.mesh.geometry.attributes.color;
    const colorRoofs = this.hhRoofs.mesh.geometry.attributes.color;
    for (const [i, entry] of this.hhIndex) {
      const tint = STATE_TINT[state[i]] || STATE_TINT[0];
      for (const [r, attr] of [[entry.walls, colorWalls], [entry.roof, colorRoofs]]) {
        for (let v = r.start; v < r.start + r.count; v++) attr.setXYZ(v, tint.r, tint.g, tint.b);
      }
    }
    colorWalls.needsUpdate = colorRoofs.needsUpdate = true;
    for (const [i, id] of this.fleetToCampus) {
      const mesh = this.campusMeshes.get(id);
      if (!mesh) continue;
      const s = state[i];
      mesh.userData.state = s;
      const [roof, facade] = mesh.material;
      const tint = STATE_TINT[s] || STATE_TINT[0];
      facade.color.setRGB(0.953 * tint.r, 0.937 * tint.g, 0.906 * tint.b);
      roof.color.set(s === 1 ? 0xf2a93b : s === 2 ? 0x3a3f47 : s === 3 ? 0xb197fc : this.selected === id ? 0x8fb4ff : 0x9db7dc);
    }
    this.applyNight();
  }

  select(id) {
    this.selected = id;
    for (const [bid, mesh] of this.campusMeshes) {
      if ((mesh.userData.state ?? 0) === 0) mesh.material[0].color.set(bid === id ? 0x8fb4ff : 0x9db7dc);
    }
  }

  // -------------------------------------------------------------- picking
  pick(e) {
    const r = this.canvas.getBoundingClientRect();
    const v = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    if (this.split) return null;
    this.raycaster.setFromCamera(v, this.camera);
    const hits = this.raycaster.intersectObjects([...this.campusMeshes.values(), this.hhWalls.mesh, this.hhRoofs.mesh], false);
    const h = hits[0];
    if (!h) return null;
    if (h.object.userData.kind === "campus") return { kind: "campus", building: h.object.userData.building };
    const vertex = h.faceIndex * 3;
    const range = h.object.userData.ranges.find((x) => vertex >= x.start && vertex < x.start + x.count);
    return range ? { kind: "household", fleetIndex: range.i, building: range.b } : null;
  }

  // -------------------------------------------------------------- camera
  flyTo({ target, distance = 600, polar = 0.95, azimuth = -0.65, duration = 1.6 }) {
    const t0 = this.controls.target.clone(), p0 = this.camera.position.clone();
    const t1 = new THREE.Vector3(target[0], 0, -target[1]);
    const p1 = new THREE.Vector3(
      t1.x + distance * Math.sin(polar) * Math.sin(azimuth), distance * Math.cos(polar),
      t1.z + distance * Math.sin(polar) * Math.cos(azimuth));
    this.flight = { t0, t1, p0, p1, start: performance.now(), duration: duration * 1000 };
  }

  screen(x, y, z) {
    const v = new THREE.Vector3(x, z, -y).project(this.camera);
    const r = this.canvas.getBoundingClientRect();
    return { x: (v.x + 1) / 2 * r.width, y: (1 - v.y) / 2 * r.height, visible: v.z < 1 && v.x > -1.1 && v.x < 1.1 };
  }

  setQuality(high) { this.quality = high; }

  setSplit(split) { this.split = split; this.resize(); }

  resize() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.gtao?.setSize(w, h);
    this.camera.aspect = (this.split ? w / 2 : w) / h;
    this.camera.updateProjectionMatrix();
  }

  frame() {
    if (!this.canvas.offsetParent) return;
    if (this.flight) {
      const k = Math.min(1, (performance.now() - this.flight.start) / this.flight.duration);
      const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      this.controls.target.lerpVectors(this.flight.t0, this.flight.t1, e);
      this.camera.position.lerpVectors(this.flight.p0, this.flight.p1, e);
      if (k >= 1) this.flight = null;
    }
    this.controls.update();
    this.sun.target.position.copy(this.controls.target);
    if (this.split) {
      const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
      this.renderer.setScissorTest(true);
      for (const [side, x] of [["left", 0], ["right", w / 2]]) {
        this.split[side]?.();
        this.renderer.setViewport(x, 0, w / 2, h);
        this.renderer.setScissor(x, 0, w / 2, h);
        this.renderer.render(this.scene, this.camera);
      }
      this.renderer.setScissorTest(false);
      this.renderer.setViewport(0, 0, w, h);
    } else if (this.quality && this.gtao) {
      this.composer.render();
    } else {
      this.renderer.render(this.scene, this.camera);
    }
    this.onFrame?.();
  }
}
