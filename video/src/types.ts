// The storyboard: everything a launch video is made from. Claude writes it (as data, never code)
// from the company's own website; the templates in this folder turn it into motion.

export type Format = "landscape" | "vertical" | "square";
export type Tone = "default" | "polished" | "bold";

/** A rectangle on a screenshot, as fractions of its width and height (0-1). */
export type Box = { x: number; y: number; w: number; h: number };

export type Shot = {
  src: string; // file name in the job's folder (served next to the bundle)
  width: number;
  height: number;
};

export type Scene =
  | { type: "hook"; lines: string[]; beats: number } // 1-2 short lines, the first 2 seconds
  | { type: "reveal"; title: string; tagline: string; beats: number } // the name and what it is
  | {
      type: "feature";
      kicker?: string; // tiny label above, e.g. "Step 1" or "Compare"
      title: string; // what it does for them, a few words
      body?: string; // one short supporting line
      shot: number; // index into shots
      focus: Box; // the part of the screenshot that matters
      click?: { x: number; y: number }; // where a simulated cursor clicks, in the screenshot's 0-1 space
      beats: number;
    }
  | { type: "proof"; quote: string; who: string; beats: number } // only real words from the site
  | { type: "outro"; title: string; cta: string; url: string; beats: number };

export type Storyboard = {
  format: Format;
  fps: number;
  bpm: number;
  tone: Tone;
  brand: {
    name: string;
    url: string;
    logo?: string; // file name, optional
    font?: string; // a Google Fonts family to try first; Inter when it can't load
    colors: { bg: string; fg: string; accent: string; accent2?: string; muted?: string };
    dark: boolean;
  };
  shots: Shot[];
  scenes: Scene[];
  music?: string; // file name of the soundtrack
};

export const SIZES: Record<Format, { width: number; height: number }> = {
  landscape: { width: 1920, height: 1080 },
  vertical: { width: 1080, height: 1920 },
  square: { width: 1080, height: 1080 },
};

export const framesPerBeat = (sb: Pick<Storyboard, "fps" | "bpm">) => (60 / sb.bpm) * sb.fps;
export const sceneFrames = (sb: Storyboard, s: Scene) => Math.round(s.beats * framesPerBeat(sb));
