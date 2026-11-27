// A soundtrack for one launch video, written as code (no samples, no licences to track).
//
// Everything sits on one beat grid counted from the first frame, so cuts land on beats:
//   intro (the hook): pads and a soft pulse; a riser into the reveal
//   main: four-on-the-floor kick, claps on 2 and 4, offbeat hats, a bass that ducks under the kick,
//         detuned pads and a plucked arpeggio, all in one key (A minor: Am F C G)
//   cuts: a soft impact on each scene change, a bigger one on the reveal
//   end: drums stop, the last chord rings out
import fs from "node:fs";

const SR = 44100;
const TAU = Math.PI * 2;

const midiHz = (m) => 440 * 2 ** ((m - 69) / 12);
// Am, F, C, G — root and chord notes (MIDI)
const CHORDS = [
  [57, 60, 64], // A C E
  [53, 57, 60], // F A C
  [48, 52, 55], // C E G
  [55, 59, 62], // G B D
];

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296) * 2 - 1;
}

/**
 * @param {{ seconds: number, bpm: number, revealAt: number, cuts: number[], seed?: number }} o
 * @returns {Float32Array[]} [left, right]
 */
export function compose({ seconds, bpm, revealAt, cuts, seed = 7 }) {
  const n = Math.ceil((seconds + 1.5) * SR);
  const L = new Float32Array(n), R = new Float32Array(n);
  const beat = 60 / bpm;
  const bar = beat * 4;
  const noise = rng(seed);
  const drumsUntil = seconds - beat * 1.5;

  const add = (t0, len, fn, pan = 0, gain = 1) => {
    const i0 = Math.max(0, Math.floor(t0 * SR));
    const i1 = Math.min(n, Math.floor((t0 + len) * SR));
    const gl = gain * Math.cos((pan + 1) * Math.PI / 4), gr = gain * Math.sin((pan + 1) * Math.PI / 4);
    for (let i = i0; i < i1; i++) {
      const v = fn((i - i0) / SR, i / SR);
      L[i] += v * gl;
      R[i] += v * gr;
    }
  };

  // Sidechain: everything melodic dips under each kick.
  const kicks = [];
  const duck = (t) => {
    let g = 1;
    for (let k = kicks.length - 1; k >= 0; k--) {
      const d = t - kicks[k];
      if (d >= 0 && d < 0.3) { g = Math.min(g, 0.35 + 0.65 * (d / 0.3) ** 0.6); break; }
      if (d >= 0.3) break;
    }
    return g;
  };

  const chordAt = (t) => CHORDS[Math.floor(t / bar) % CHORDS.length];

  // --- drums ---
  for (let t = 0; t < drumsUntil; t += beat) {
    const b = Math.round(t / beat);
    const main = t >= revealAt - 0.001;
    if (main || b % 4 === 0) {
      kicks.push(t);
      add(t, 0.45, (x) => {
        const f = 45 + 95 * Math.exp(-x * 28);
        return Math.sin(TAU * f * x - 0.0) * Math.exp(-x * 7.5) * 0.9 + (x < 0.004 ? noise() * 0.25 : 0);
      }, 0, main ? 0.9 : 0.55);
    }
    if (main && (b % 4 === 1 || b % 4 === 3)) {
      let lp = 0;
      add(t, 0.35, (x) => {
        lp += 0.35 * (noise() - lp); // one-pole low-pass: warm, not hissy
        const body = lp * Math.exp(-x * 20);
        const tone = Math.sin(TAU * 190 * x) * Math.exp(-x * 30) * 0.3;
        return (body * 1.4 + tone) * 0.5;
      }, 0.05, 0.38);
    }
    if (main) {
      for (const off of [0, 0.5]) {
        let prev = 0;
        add(t + off * beat, 0.06, (x) => {
          const w = noise();
          const hp = w - prev; // crude high-pass
          prev = w;
          return hp * Math.exp(-x * 70);
        }, off ? 0.35 : -0.35, off ? 0.1 : 0.05);
      }
    }
  }

  // --- bass: eighth-note pulse on the chord root, from the reveal ---
  for (let t = revealAt; t < drumsUntil; t += beat / 2) {
    const root = chordAt(t)[0] - 12;
    const f = midiHz(root);
    add(t, beat / 2, (x, abs) => {
      let v = 0;
      for (let h = 1; h <= 6; h++) v += Math.sin(TAU * f * h * x) / h * (h === 1 ? 1 : 0.6);
      return v * 0.28 * Math.min(1, x * 200) * Math.exp(-x * 4) * duck(abs);
    }, 0, 0.75);
  }

  // --- pads: one chord per bar, detuned, slow attack, under everything ---
  for (let t = 0; t < seconds + 1; t += bar) {
    const notes = chordAt(t + 0.01);
    const len = bar + 0.6;
    for (const m of notes) {
      for (const [det, pan] of [[-0.004, -0.6], [0.004, 0.6]]) {
        const f = midiHz(m) * (1 + det);
        add(t, len, (x, abs) => {
          const env = Math.min(1, x / 0.45) * Math.min(1, (len - x) / 0.6);
          const tri = (2 / Math.PI) * Math.asin(Math.sin(TAU * f * x));
          const soft = Math.sin(TAU * f * 2 * x) * 0.15;
          return (tri * 0.6 + soft) * env * 0.07 * duck(abs);
        }, pan, abs_end(t, seconds) ? 0.9 : 1);
      }
    }
  }

  // --- plucked arpeggio: chord tones an octave up, eighth notes, from the reveal ---
  const pattern = [0, 1, 2, 1, 0, 2, 1, 2];
  let step = 0;
  for (let t = revealAt; t < drumsUntil; t += beat / 2, step++) {
    const notes = chordAt(t);
    const m = notes[pattern[step % pattern.length]] + 12;
    const f = midiHz(m);
    add(t, 0.5, (x, abs) => {
      const v = Math.sin(TAU * f * x) + 0.35 * Math.sin(TAU * f * 2 * x) * Math.exp(-x * 12);
      return v * Math.exp(-x * 9) * 0.16 * duck(abs);
    }, step % 2 ? 0.45 : -0.45);
  }

  // --- riser into the reveal: noise swell plus a rising tone over the last bar ---
  if (revealAt > 0.5) {
    const len = Math.min(bar, revealAt);
    let lp = 0;
    add(revealAt - len, len, (x) => {
      const p = x / len;
      lp += (0.02 + 0.3 * p * p) * (noise() - lp); // the filter opens as it rises
      return (lp * 0.9 * p ** 2 + Math.sin(TAU * (220 + 660 * p * p) * x) * 0.06 * p) * 0.6;
    }, 0, 0.55);
  }

  // --- impacts: a big one on the reveal, soft ones on other cuts ---
  const impact = (t, big) => {
    let lp = 0;
    add(t, big ? 1.6 : 0.6, (x) => {
      const sub = Math.sin(TAU * (38 + 40 * Math.exp(-x * 9)) * x) * Math.exp(-x * (big ? 2.6 : 7));
      lp += 0.12 * (noise() - lp);
      const air = lp * Math.exp(-x * (big ? 4 : 14)) * 0.9;
      return (sub + air) * (big ? 0.7 : 0.24);
    }, 0, 1);
  };
  impact(revealAt, true);
  for (const c of cuts) if (Math.abs(c - revealAt) > 0.05 && c < seconds - 0.2) impact(c, false);

  // --- the ending: last chord rings out with a soft bell ---
  const last = chordAt(drumsUntil);
  for (const m of last) {
    const f = midiHz(m + 12);
    add(drumsUntil, 2.2, (x) => Math.sin(TAU * f * x) * Math.exp(-x * 1.8) * 0.06, m % 2 ? 0.3 : -0.3);
  }

  // Space: a soft ping-pong echo (3/16 of a bar), so it sounds produced rather than dry.
  const d = Math.round(beat * 0.75 * SR);
  for (let i = d; i < n; i++) {
    L[i] += R[i - d] * 0.16;
    R[i] += L[i - d] * 0.16;
  }

  // Mix: gentle saturation, then normalise to -1 dBFS.
  let peak = 0;
  for (let i = 0; i < n; i++) {
    L[i] = Math.tanh(L[i] * 1.1);
    R[i] = Math.tanh(R[i] * 1.1);
    peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i]));
  }
  const g = peak > 0 ? 0.89 / peak : 1;
  for (let i = 0; i < n; i++) { L[i] *= g; R[i] *= g; }
  return [L, R];
}

function abs_end(t, seconds) {
  return t > seconds - 2;
}

export function writeWav(path, [L, R]) {
  const n = L.length;
  const buf = Buffer.alloc(44 + n * 4);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 4, 4); buf.write("WAVE", 8);
  buf.write("fmt ", 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22);
  buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(SR * 4, 28); buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34);
  buf.write("data", 36); buf.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) {
    buf.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(L[i] * 32767))), 44 + i * 4);
    buf.writeInt16LE(Math.max(-32768, Math.min(32767, Math.round(R[i] * 32767))), 46 + i * 4);
  }
  fs.writeFileSync(path, buf);
}
