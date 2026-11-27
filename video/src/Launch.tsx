import "@fontsource-variable/inter";

import { slide } from "@remotion/transitions/slide";
import { linearTiming, springTiming, TransitionSeries } from "@remotion/transitions";
import React, { useEffect, useState } from "react";
import { AbsoluteFill, Audio, cancelRender, continueRender, delayRender, Freeze, interpolate, Sequence, staticFile, useVideoConfig } from "remotion";

import { dip } from "./dip";
import { Backdrop } from "./parts";
import { Feature, Hook, Outro, Proof, Reveal } from "./scenes";
import { framesPerBeat, sceneFrames, type Storyboard } from "./types";

export const TRANSITION = 12; // frames each scene overlaps the next

/** Total length: the scenes, minus the overlaps between them. */
export const totalFrames = (sb: Storyboard) =>
  sb.scenes.reduce((t, s) => t + sceneFrames(sb, s), 0) - TRANSITION * Math.max(0, sb.scenes.length - 1);

/** Load the brand's Google font when it has one; fall back to Inter if it can't load in time. */
function useBrandFont(family?: string) {
  const [handle] = useState(() => (family ? delayRender(`font ${family}`, { timeoutInMilliseconds: 15000 }) : null));
  useEffect(() => {
    if (!family || handle === null) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(family)}:wght@400;500;600;700;800&display=block`;
    const done = () => continueRender(handle);
    link.onload = () => {
      Promise.race([
        Promise.all([400, 600, 800].map((w) => document.fonts.load(`${w} 40px "${family}"`))),
        new Promise((r) => setTimeout(r, 6000)),
      ]).then(done, done);
    };
    link.onerror = done; // no network or unknown font: Inter it is
    document.head.appendChild(link);
    const guard = setTimeout(done, 8000);
    return () => clearTimeout(guard);
  }, [family, handle]);
}

export const Launch: React.FC<Storyboard> = (sb) => {
  const { durationInFrames } = useVideoConfig();
  useBrandFont(sb.brand.font);
  const c = sb.brand.colors;
  if (!sb.scenes.length) cancelRender(new Error("A storyboard needs scenes"));

  return (
    <AbsoluteFill style={{ background: c.bg }}>
      <Backdrop bg={c.bg} accent={c.accent} accent2={c.accent2 || c.accent} dark={sb.brand.dark} />
      <TransitionSeries>
        {sb.scenes.flatMap((s, i) => {
          const frames = sceneFrames(sb, s);
          const scene = (
            <TransitionSeries.Sequence key={`s${i}`} durationInFrames={frames}>
              {s.type === "hook" && <Hook sb={sb} s={s} frames={frames} />}
              {s.type === "reveal" && <Reveal sb={sb} s={s} frames={frames} />}
              {s.type === "feature" && <Feature sb={sb} s={s} frames={frames} index={i} />}
              {s.type === "proof" && <Proof sb={sb} s={s} frames={frames} />}
              {s.type === "outro" && <Outro sb={sb} s={s} frames={frames} />}
            </TransitionSeries.Sequence>
          );
          if (i === sb.scenes.length - 1) return [scene];
          const next = sb.scenes[i + 1];
          // Features slide in like turning a page; everything else dips through the background.
          // (typed loosely: the two presentations take different props)
          const presentation = (next.type === "feature" && s.type === "feature" ? slide({ direction: "from-right" }) : dip()) as ReturnType<typeof dip>;
          const timing = next.type === "feature" && s.type === "feature"
            ? springTiming({ config: { damping: 200 }, durationInFrames: TRANSITION })
            : linearTiming({ durationInFrames: TRANSITION });
          return [scene, <TransitionSeries.Transition key={`t${i}`} presentation={presentation} timing={timing} />];
        })}
      </TransitionSeries>
      {/* Frame 0 is the thumbnail every platform shows: a settled, strong frame instead of an empty one. */}
      <PosterFrame sb={sb} />
      {sb.music && (
        <Audio
          src={staticFile(sb.music)}
          volume={(f) => interpolate(f, [0, 6, durationInFrames - 24, durationInFrames], [0, 0.9, 0.9, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}
        />
      )}
    </AbsoluteFill>
  );
};

export { framesPerBeat };

const PosterFrame: React.FC<{ sb: Storyboard }> = ({ sb }) => {
  const idx = Math.max(0, sb.scenes.findIndex((s) => s.type === "reveal"));
  const s = sb.scenes[idx];
  const frames = sceneFrames(sb, s);
  const c = sb.brand.colors;
  return (
    <Sequence durationInFrames={1}>
      <Freeze frame={Math.round(frames * 0.7)}>
        <AbsoluteFill>
          <Backdrop bg={c.bg} accent={c.accent} accent2={c.accent2 || c.accent} dark={sb.brand.dark} />
          {s.type === "reveal" && <Reveal sb={sb} s={s} frames={frames} />}
          {s.type === "hook" && <Hook sb={sb} s={s} frames={frames} />}
          {s.type === "feature" && <Feature sb={sb} s={s} frames={frames} index={idx} />}
          {s.type === "outro" && <Outro sb={sb} s={s} frames={frames} />}
          {s.type === "proof" && <Proof sb={sb} s={s} frames={frames} />}
        </AbsoluteFill>
      </Freeze>
    </Sequence>
  );
};
