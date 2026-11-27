import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import { BrowserFrame, clamp, Cursor, easeInOut, onColor, Rise, Words } from "./parts";
import type { Scene, Storyboard } from "./types";

type Ctx = { sb: Storyboard; frames: number };

const unit = () => {
  const { width, height } = useVideoConfig();
  return Math.min(width, height) / 1080; // 1 at 1080p
};

const font = (sb: Storyboard) => `${sb.brand.font ? `"${sb.brand.font}", ` : ""}"Inter Variable", Inter, system-ui, sans-serif`;

/** Hook: one or two short lines, huge, in the first two seconds. */
export const Hook: React.FC<Ctx & { s: Extract<Scene, { type: "hook" }> }> = ({ sb, s, frames }) => {
  const frame = useCurrentFrame();
  const u = unit();
  const { width } = useVideoConfig();
  const zoom = interpolate(frame, [0, frames], [1, 1.06]);
  const [first, second] = s.lines;
  const size = (sb.format === "landscape" ? 118 : 104) * u * (first.length > 28 ? 0.82 : 1);
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", padding: width * 0.08, fontFamily: font(sb) }}>
      <div style={{ transform: `scale(${zoom})`, textAlign: "center", color: sb.brand.colors.fg, fontWeight: 800, letterSpacing: "-0.035em", lineHeight: 1.04, textWrap: "balance", maxWidth: width * 0.84 }}>
        <div style={{ fontSize: size }}>
          <Words text={first} stagger={3} />
        </div>
        {second && (
          <div style={{ fontSize: size, marginTop: 14 * u, color: sb.brand.colors.accent }}>
            <Words text={second} delay={8 + first.split(" ").length * 2} stagger={3} />
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

/** Reveal: the logo pops, the name lands, the tagline follows, an accent line draws under it. */
export const Reveal: React.FC<Ctx & { s: Extract<Scene, { type: "reveal" }> }> = ({ sb, s }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const u = unit();
  const pop = spring({ frame, fps, config: { damping: 11, stiffness: 160, mass: 0.6 } });
  const line = interpolate(frame, [14, 34], [0, 1], { ...clamp, easing: easeInOut });
  const spacing = interpolate(frame, [0, 26], [0.12, -0.04], { ...clamp, easing: easeInOut });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", padding: width * 0.08, fontFamily: font(sb), textAlign: "center" }}>
      {sb.brand.logo && (
        <Img
          src={staticFile(sb.brand.logo)}
          style={{ height: 120 * u, maxWidth: width * 0.3, objectFit: "contain", marginBottom: 34 * u, transform: `scale(${pop})`, opacity: pop }}
        />
      )}
      <div style={{ fontSize: 150 * u, fontWeight: 800, letterSpacing: `${spacing}em`, color: sb.brand.colors.fg, lineHeight: 1, opacity: Math.min(1, pop * 1.4) }}>
        {s.title}
      </div>
      <div style={{ height: 8 * u, width: 260 * u * line, background: sb.brand.colors.accent, borderRadius: 8, margin: `${30 * u}px auto ${26 * u}px` }} />
      <div style={{ fontSize: 50 * u, fontWeight: 500, color: sb.brand.colors.muted || sb.brand.colors.fg, maxWidth: width * 0.75, lineHeight: 1.25, letterSpacing: "-0.015em", textWrap: "balance" }}>
        <Words text={s.tagline} delay={16} stagger={2} />
      </div>
    </AbsoluteFill>
  );
};

/** Feature: the real product. A browser window tilts in, the camera moves onto what matters, a cursor clicks. */
export const Feature: React.FC<Ctx & { s: Extract<Scene, { type: "feature" }>; index: number }> = ({ sb, s, frames, index }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const u = unit();
  const shot = sb.shots[s.shot] || sb.shots[0];
  const landscape = sb.format === "landscape";

  // Layout: text beside the window (landscape) or above it (vertical, square).
  const fw = landscape ? width * 0.6 : width * 0.88;
  const bar = Math.round(fw * 0.034);
  const innerH = Math.min(fw * (shot.height / shot.width), landscape ? height * 0.72 : height * (sb.format === "vertical" ? 0.5 : 0.52));
  const fh = innerH + bar;
  const frameLeft = landscape ? width - fw - width * 0.05 : (width - fw) / 2;
  const frameTop = landscape ? (height - fh) / 2 : sb.format === "vertical" ? height * 0.4 : height * 0.4;

  // Camera: whole page, then onto the focus area.
  const f = s.focus;
  // Zoom until the focus area fills about two thirds of the window, but never so far that the
  // edges turn into cut-off fragments.
  const zEnd = Math.max(1, Math.min(1.9, 0.66 / Math.max(f.w, (f.h * shot.height * fw) / (shot.width * innerH))));
  const W = (z: number) => fw * z;
  const H = (z: number) => fw * (shot.height / shot.width) * z;
  const target = (z: number) => {
    const tx = Math.min(0, Math.max(fw - W(z), fw / 2 - (f.x + f.w / 2) * W(z)));
    const ty = Math.min(0, Math.max(innerH - H(z), innerH / 2 - (f.y + f.h / 2) * H(z)));
    return { tx, ty };
  };
  const camStart = Math.round(frames * 0.22);
  const camEnd = Math.round(frames * 0.62);
  const p = interpolate(frame, [camStart, camEnd], [0, 1], { ...clamp, easing: easeInOut });
  const z = 1 + (zEnd - 1) * p;
  const end = target(zEnd);
  const tx = end.tx * p;
  const ty = end.ty * p;

  const enter = spring({ frame, fps, config: { damping: 18, stiffness: 90, mass: 0.9 } });
  const tilt = (1 - enter) * 16;

  // The focus ring and the click, in window coordinates once the camera has settled.
  const ring = { x: f.x * W(zEnd) + end.tx, y: f.y * H(zEnd) + end.ty, w: f.w * W(zEnd), h: f.h * H(zEnd) };
  const ringIn = interpolate(frame, [camEnd - 4, camEnd + 8], [0, 1], clamp);
  const click = s.click ? { x: s.click.x * W(zEnd) + end.tx, y: s.click.y * H(zEnd) + end.ty } : null;

  const textBox: React.CSSProperties = landscape
    ? { position: "absolute", left: width * 0.06, top: 0, bottom: 0, width: width * 0.28, display: "flex", flexDirection: "column", justifyContent: "center" }
    : { position: "absolute", left: width * 0.08, right: width * 0.08, top: height * (sb.format === "vertical" ? 0.14 : 0.07), textAlign: "center" };

  return (
    <AbsoluteFill style={{ fontFamily: font(sb) }}>
      <div style={textBox}>
        {s.kicker && (
          <Rise delay={2}>
            <span
              style={{
                display: "inline-block",
                padding: `${8 * u}px ${18 * u}px`,
                borderRadius: 999,
                background: sb.brand.colors.accent,
                color: onColor(sb.brand.colors.accent),
                fontSize: 24 * u,
                fontWeight: 700,
                letterSpacing: "0.02em",
                marginBottom: 22 * u,
              }}
            >
              {s.kicker}
            </span>
          </Rise>
        )}
        <div style={{ fontSize: (landscape ? 70 : 76) * u, fontWeight: 800, letterSpacing: "-0.035em", lineHeight: 1.05, color: sb.brand.colors.fg, textWrap: "balance" }}>
          <Words text={s.title} delay={4} stagger={3} />
        </div>
        {s.body && (
          <Rise delay={14} style={{ marginTop: 22 * u }}>
            <div style={{ fontSize: 32 * u, lineHeight: 1.35, color: sb.brand.colors.muted || sb.brand.colors.fg, fontWeight: 500 }}>{s.body}</div>
          </Rise>
        )}
      </div>

      <div style={{ position: "absolute", left: frameLeft, top: frameTop, perspective: 1600 }}>
        <BrowserFrame
          url={sb.brand.url}
          dark={sb.brand.dark}
          width={fw}
          height={fh}
          style={{
            transform: `translateY(${(1 - enter) * 120 * u}px) rotateX(${tilt}deg) rotateY(${(landscape ? -1 : 0) * tilt * 0.6}deg) scale(${0.94 + 0.06 * enter})`,
            opacity: enter,
          }}
        >
          <Img
            src={staticFile(shot.src)}
            style={{ position: "absolute", left: tx, top: ty, width: W(z), height: H(z), maxWidth: "none" }}
          />
          <div
            style={{
              position: "absolute",
              left: ring.x - 6,
              top: ring.y - 6,
              width: ring.w + 12,
              height: ring.h + 12,
              borderRadius: 14 * u,
              border: `${4 * u}px solid ${sb.brand.colors.accent}`,
              boxShadow: `0 0 ${40 * u}px ${sb.brand.colors.accent}`,
              opacity: ringIn * 0.9,
              transform: `scale(${1.04 - 0.04 * ringIn})`,
            }}
          />
          {click && (
            <Cursor
              from={{ x: fw * 0.92, y: innerH * 1.05 }}
              to={click}
              start={camEnd - 2}
              travel={Math.round(frames * 0.14)}
              size={30 * u * (fw / 1150)}
            />
          )}
        </BrowserFrame>
      </div>
    </AbsoluteFill>
  );
};

/** Proof: a real quote from the site. */
export const Proof: React.FC<Ctx & { s: Extract<Scene, { type: "proof" }> }> = ({ sb, s }) => {
  const u = unit();
  const { width } = useVideoConfig();
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", padding: width * 0.1, fontFamily: font(sb), textAlign: "center" }}>
      <Rise>
        <div style={{ fontSize: 160 * u, lineHeight: 0.6, color: sb.brand.colors.accent, fontWeight: 800 }}>“</div>
      </Rise>
      <div style={{ fontSize: 58 * u, fontWeight: 650, letterSpacing: "-0.025em", lineHeight: 1.2, color: sb.brand.colors.fg, maxWidth: width * 0.78 }}>
        <Words text={s.quote} delay={4} stagger={2} />
      </div>
      <Rise delay={22} style={{ marginTop: 34 * u }}>
        <div style={{ fontSize: 30 * u, color: sb.brand.colors.muted || sb.brand.colors.fg, fontWeight: 600 }}>{s.who}</div>
      </Rise>
    </AbsoluteFill>
  );
};

/** Outro: the line to remember, and where to go. The button pulses on the beat. */
export const Outro: React.FC<Ctx & { s: Extract<Scene, { type: "outro" }> }> = ({ sb, s }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const u = unit();
  const beat = (60 / sb.bpm) * fps;
  const pulse = 1 + 0.035 * Math.max(0, Math.cos(((frame % beat) / beat) * Math.PI * 2)) * interpolate(frame, [20, 30], [0, 1], clamp);
  const pop = spring({ frame: frame - 12, fps, config: { damping: 12, stiffness: 150 } });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", padding: width * 0.08, fontFamily: font(sb), textAlign: "center" }}>
      {sb.brand.logo && (
        <Rise>
          <Img src={staticFile(sb.brand.logo)} style={{ height: 84 * u, maxWidth: width * 0.25, objectFit: "contain", marginBottom: 34 * u }} />
        </Rise>
      )}
      <div style={{ fontSize: 96 * u, fontWeight: 800, letterSpacing: "-0.035em", lineHeight: 1.05, color: sb.brand.colors.fg, maxWidth: width * 0.84, textWrap: "balance" }}>
        <Words text={s.title} stagger={3} />
      </div>
      <div
        style={{
          marginTop: 48 * u,
          display: "inline-flex",
          alignItems: "center",
          gap: 18 * u,
          padding: `${22 * u}px ${44 * u}px`,
          borderRadius: 999,
          background: sb.brand.colors.accent,
          color: onColor(sb.brand.colors.accent),
          fontSize: 38 * u,
          fontWeight: 700,
          transform: `scale(${pop * pulse})`,
          opacity: pop,
          boxShadow: `0 ${18 * u}px ${50 * u}px ${sb.brand.colors.accent}55`,
        }}
      >
        {s.cta}
        <span style={{ fontSize: 40 * u }}>→</span>
      </div>
      <Rise delay={22} style={{ marginTop: 28 * u }}>
        <div style={{ fontSize: 32 * u, fontWeight: 600, color: sb.brand.colors.muted || sb.brand.colors.fg }}>{s.url.replace(/^https?:\/\//, "").replace(/\/$/, "")}</div>
      </Rise>
    </AbsoluteFill>
  );
};
