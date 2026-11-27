#!/usr/bin/env node
// Render one launch video.
//
//   node render.mjs <job folder>
//
// The job folder holds storyboard.json (see src/types.ts) and the files it names (screenshots, the
// logo). Writes soundtrack.wav, brag-style outputs launch.mp4 and poster.jpg into the same folder.
// Chrome: CHROME_PATH (or Remotion's own headless shell). Nothing here runs code from the storyboard:
// it's data for fixed templates.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";

import { compose, writeWav } from "./music.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const TRANSITION = 12; // keep in step with src/Launch.tsx

async function main() {
  const job = path.resolve(process.argv[2] || "");
  const sb = JSON.parse(fs.readFileSync(path.join(job, "storyboard.json"), "utf8"));
  const fpb = (60 / sb.bpm) * sb.fps;
  const lens = sb.scenes.map((s) => Math.round(s.beats * fpb));
  const starts = [];
  let at = 0;
  lens.forEach((len, i) => { starts.push(at); at += len - (i < lens.length - 1 ? TRANSITION : 0); });
  const total = at;

  // The soundtrack, cut to this storyboard.
  const revealIdx = sb.scenes.findIndex((s) => s.type === "reveal");
  const cuts = starts.slice(1).map((f) => (f + TRANSITION / 2) / sb.fps);
  const revealAt = revealIdx > 0 ? (starts[revealIdx] + TRANSITION / 2) / sb.fps : 0;
  writeWav(path.join(job, "soundtrack.wav"), compose({ seconds: total / sb.fps, bpm: sb.bpm, revealAt, cuts }));
  sb.music = "soundtrack.wav";

  const browserExecutable = process.env.CHROME_PATH || null;
  const serveUrl = await bundle({ entryPoint: path.join(here, "src/index.ts"), publicDir: job });
  const composition = await selectComposition({ serveUrl, id: "Launch", inputProps: sb, browserExecutable });
  const common = { serveUrl, composition, inputProps: sb, browserExecutable, chromiumOptions: { gl: "swangle" } };

  await renderMedia({
    ...common,
    codec: "h264",
    crf: 18,
    pixelFormat: "yuv420p",
    audioCodec: "aac",
    outputLocation: path.join(job, "launch.mp4"),
    concurrency: Number(process.env.RENDER_CONCURRENCY || 2),
    onProgress: ({ progress }) => {
      if (Math.round(progress * 100) % 25 === 0) process.stdout.write(`render ${Math.round(progress * 100)}%\n`);
    },
  });
  // The poster: a settled frame from the reveal (or the first feature).
  const posterIdx = revealIdx >= 0 ? revealIdx : 0;
  const posterFrame = Math.min(total - 1, starts[posterIdx] + Math.round(lens[posterIdx] * 0.7));
  await renderStill({ ...common, frame: posterFrame, output: path.join(job, "poster.jpg"), imageFormat: "jpeg", jpegQuality: 90 });
  fs.writeFileSync(path.join(job, "result.json"), JSON.stringify({ frames: total, seconds: total / sb.fps, poster_frame: posterFrame }));
  process.stdout.write("done\n");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
