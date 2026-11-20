// Replay player: reconstructs building states at any time from the change log and plays
// one or two replays in lock-step (compare mode).

const CHECKPOINT_EVERY = 20;

export class Replay {
  constructor(data) {
    this.data = data;
    this.frames = data.frames;
    this.n = data.buildings.length;
    this.duration = this.frames.at(-1).t;
    // Checkpoints of the full state array for fast seeking.
    this.checkpoints = [];
    const state = new Uint8Array(this.n);
    this.firstAffected = new Float32Array(this.n).fill(Infinity);
    this.frames.forEach((frame, i) => {
      for (const [b, code] of frame.c) {
        state[b] = code;
        if (code === 1 || code === 2) this.firstAffected[b] = Math.min(this.firstAffected[b], frame.t);
      }
      if (i % CHECKPOINT_EVERY === 0) this.checkpoints.push(state.slice());
    });
    this.campusIndex = new Map(data.buildings.filter((b) => b.campus_id != null).map((b, k) => [b.i, k]));
  }

  frameIndex(t) {
    const dt = this.data.frame_dt;
    return Math.max(0, Math.min(this.frames.length - 1, Math.round(t / dt)));
  }

  stateAt(t) {
    const i = this.frameIndex(t);
    const cp = Math.floor(i / CHECKPOINT_EVERY);
    const state = this.checkpoints[cp].slice();
    for (let j = cp * CHECKPOINT_EVERY + 1; j <= i; j++) for (const [b, code] of this.frames[j].c) state[b] = code;
    return state;
  }

  frameAt(t) { return this.frames[this.frameIndex(t)]; }

  /** Running outcome counters up to time t. */
  countersAt(t) {
    let affected = 0, cut = 0, paused = 0;
    const state = this.stateAt(t);
    for (let b = 0; b < this.n; b++) {
      if (this.firstAffected[b] <= t) affected++;
      if (state[b] === 2) cut++;
      if (state[b] === 1) paused++;
    }
    const stages = new Set(this.data.decisions.filter((d) => d.kind === "aufls" && d.t <= t).map((d) => d.stage)).size;
    let fmin = 50;
    for (let i = 0; i <= this.frameIndex(t); i++) fmin = Math.min(fmin, this.frames[i].f);
    const campus = this.data.buildings.filter((b) => b.campus_id != null);
    const campusCut = campus.filter((b) => state[b.i] === 2).length;
    return { affected, cut, paused, stages, fmin, campusCut, critical: this.data.metrics.protected_sites_interrupted };
  }

  decisionsUpTo(t) { return this.data.decisions.filter((d) => d.t <= t); }
}

export class Player {
  constructor({ onFrame }) {
    this.onFrame = onFrame;
    this.replays = [];
    this.t = 0;
    this.speed = 4;
    this.playing = false;
    this.stopAt = null;
    this.last = null;
    const tick = (now) => {
      if (this.playing && this.replays.length) {
        const dt = this.last == null ? 0 : (now - this.last) / 1000;
        let t = this.t + dt * this.speed;
        const end = Math.min(...this.replays.map((r) => r.duration));
        if (this.stopAt != null && t >= this.stopAt) { t = this.stopAt; this.stopAt = null; this.pause(); this.onStop?.(); }
        if (t >= end) { t = end; this.pause(); }
        this.seek(t, false);
      }
      this.last = now;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  load(replays) { this.replays = replays; this.seek(0); }
  play(stopAt = null) { this.stopAt = stopAt; this.playing = true; this.onPlayState?.(true); }
  pause() { this.playing = false; this.onPlayState?.(false); }
  toggle() { this.playing ? this.pause() : this.play(); }
  seek(t, user = true) {
    this.t = Math.max(0, t);
    if (user) this.stopAt = null;
    this.onFrame?.(this.t, this.replays);
  }
}
