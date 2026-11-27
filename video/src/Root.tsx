import React from "react";
import { Composition } from "remotion";

import { Launch, totalFrames } from "./Launch";
import { SIZES, type Storyboard } from "./types";

const sample: Storyboard = {
  format: "landscape",
  fps: 30,
  bpm: 112,
  tone: "default",
  brand: { name: "Acme", url: "acme.test", colors: { bg: "#0c111d", fg: "#ffffff", accent: "#7c5cff" }, dark: true },
  shots: [],
  scenes: [
    { type: "hook", lines: ["Make a video", "from a website"], beats: 4 },
    { type: "outro", title: "Try it", cta: "Get started", url: "acme.test", beats: 6 },
  ],
};

export const Root: React.FC = () => (
  <Composition
    id="Launch"
    component={Launch as unknown as React.FC<Record<string, unknown>>}
    defaultProps={sample as unknown as Record<string, unknown>}
    durationInFrames={totalFrames(sample)}
    fps={30}
    width={1920}
    height={1080}
    calculateMetadata={({ props }) => {
      const sb = props as unknown as Storyboard;
      return { durationInFrames: totalFrames(sb), fps: sb.fps, ...SIZES[sb.format] };
    }}
  />
);
