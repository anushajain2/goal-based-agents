#!/usr/bin/env node
// Render chosen frames of a job as images, to check a storyboard before the full render:
//   node stills.mjs <job folder> <frame> [<frame> ...]      (writes still-<frame>.jpg)
//   node stills.mjs <job folder> auto                         (one per scene, and each transition's middle)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";

const here = path.dirname(fileURLToPath(import.meta.url));
const TRANSITION = 12;

const job = path.resolve(process.argv[2]);
const sb = JSON.parse(fs.readFileSync(path.join(job, "storyboard.json"), "utf8"));
const fpb = (60 / sb.bpm) * sb.fps;
const lens = sb.scenes.map((s) => Math.round(s.beats * fpb));
const starts = [];
let at = 0;
lens.forEach((len, i) => { starts.push(at); at += len - (i < lens.length - 1 ? TRANSITION : 0); });
let frames = process.argv.slice(3).map(Number);
if (process.argv[3] === "auto") {
  frames = [];
  lens.forEach((len, i) => {
    frames.push(starts[i] + Math.round(len * 0.45), starts[i] + len - TRANSITION - 2);
    if (i > 0) frames.push(starts[i] + TRANSITION / 2);
  });
  frames = [...new Set(frames)].filter((f) => f > 0 && f < at).sort((a, b) => a - b);
}
const serveUrl = await bundle({ entryPoint: path.join(here, "src/index.ts"), publicDir: job });
const browserExecutable = process.env.CHROME_PATH || null;
const composition = await selectComposition({ serveUrl, id: "Launch", inputProps: sb, browserExecutable });
for (const frame of frames) {
  await renderStill({ serveUrl, composition, inputProps: sb, browserExecutable, frame, output: path.join(job, `still-${frame}.jpg`), imageFormat: "jpeg", jpegQuality: 80 });
}
console.log(frames.join(" "));
