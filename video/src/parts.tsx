import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

/** Ease in/out for camera moves: slow start, slow settle. */
export const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);
export const easeOut = Easing.bezier(0.16, 1, 0.3, 1);

export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Text that arrives word by word: each word rises, sharpens and fades in, a few frames apart. */
export const Words: React.FC<{
  text: string;
  delay?: number;
  stagger?: number;
  style?: React.CSSProperties;
  accentWords?: number[]; // indexes of words drawn in the accent colour
  accent?: string;
}> = ({ text, delay = 0, stagger = 3, style, accentWords = [], accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = text.split(/\s+/).filter(Boolean);
  return (
    <span style={{ display: "inline", ...style }}>
      {words.map((w, i) => {
        const t = spring({ frame: frame - delay - i * stagger, fps, config: { damping: 16, stiffness: 140, mass: 0.7 } });
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              whiteSpace: "pre",
              opacity: t,
              transform: `translateY(${(1 - t) * 0.45}em)`,
              filter: `blur(${(1 - t) * 10}px)`,
              color: accentWords.includes(i) ? accent : undefined,
            }}
          >
            {w}
            {i < words.length - 1 ? " " : ""}
          </span>
        );
      })}
    </span>
  );
};

/** Fade and rise for a whole block. */
export const Rise: React.FC<{ delay?: number; children: React.ReactNode; style?: React.CSSProperties; distance?: number }> = ({
  delay = 0,
  children,
  style,
  distance = 30,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = spring({ frame: frame - delay, fps, config: { damping: 18, stiffness: 120 } });
  return <div style={{ opacity: t, transform: `translateY(${(1 - t) * distance}px)`, ...style }}>{children}</div>;
};

/** The brand's background: its own colour, two soft light sources drifting slowly, a faint dot grid and grain. */
export const Backdrop: React.FC<{ bg: string; accent: string; accent2: string; dark: boolean }> = ({ bg, accent, accent2, dark }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const a = frame / 90;
  // Soft light sources as radial gradients (cheap to render, unlike blur filters).
  const blob = (color: string, x: number, y: number, size: number, alpha: number) => (
    <div
      style={{
        position: "absolute",
        left: x - size / 2,
        top: y - size / 2,
        width: size,
        height: size,
        background: `radial-gradient(circle at center, ${color} 0%, transparent 65%)`,
        opacity: alpha,
      }}
    />
  );
  return (
    <AbsoluteFill style={{ background: bg, overflow: "hidden" }}>
      {blob(accent, width * (0.18 + 0.06 * Math.sin(a)), height * (0.22 + 0.05 * Math.cos(a * 0.8)), Math.max(width, height) * 0.55, dark ? 0.35 : 0.22)}
      {blob(accent2, width * (0.85 + 0.05 * Math.cos(a * 0.7)), height * (0.8 + 0.06 * Math.sin(a * 0.9)), Math.max(width, height) * 0.5, dark ? 0.3 : 0.18)}
      <AbsoluteFill
        style={{
          backgroundImage: `radial-gradient(${dark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.06)"} 1.2px, transparent 1.2px)`,
          backgroundSize: "28px 28px",
          maskImage: "radial-gradient(ellipse at center, black 30%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse at center, black 30%, transparent 75%)",
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at center, transparent 55%, ${dark ? "rgba(0,0,0,0.45)" : "rgba(0,0,0,0.08)"} 100%)`,
        }}
      />
      <Grain />
    </AbsoluteFill>
  );
};

/** Film grain: one small noise tile (made once), shifted every frame. Subtle; keeps flat colours from looking cheap. */
const GRAIN = (() => {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='256' height='256' filter='url(#n)'/></svg>`;
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`;
})();

const Grain: React.FC = () => {
  const frame = useCurrentFrame();
  const dx = ((frame * 73) % 256) - 128;
  const dy = ((frame * 151) % 256) - 128;
  return (
    <AbsoluteFill
      style={{ opacity: 0.07, mixBlendMode: "overlay", pointerEvents: "none", backgroundImage: GRAIN, backgroundSize: "256px 256px", backgroundPosition: `${dx}px ${dy}px` }}
    />
  );
};

/** A browser window around a screenshot. */
export const BrowserFrame: React.FC<{
  url: string;
  dark: boolean;
  width: number;
  height: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ url, dark, width, height, children, style }) => {
  const bar = Math.round(width * 0.034);
  return (
    <div
      style={{
        width,
        height,
        borderRadius: Math.round(width * 0.014),
        overflow: "hidden",
        background: dark ? "#16181d" : "#ffffff",
        boxShadow: dark
          ? "0 40px 120px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.08)"
          : "0 40px 120px rgba(16,24,40,0.22), 0 0 0 1px rgba(16,24,40,0.08)",
        display: "flex",
        flexDirection: "column",
        ...style,
      }}
    >
      <div
        style={{
          height: bar,
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          gap: bar * 0.22,
          padding: `0 ${bar * 0.45}px`,
          background: dark ? "#1f2229" : "#f3f4f6",
          borderBottom: `1px solid ${dark ? "rgba(255,255,255,0.06)" : "rgba(16,24,40,0.06)"}`,
        }}
      >
        {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
          <span key={c} style={{ width: bar * 0.3, height: bar * 0.3, borderRadius: "50%", background: c }} />
        ))}
        <span
          style={{
            marginLeft: bar * 0.4,
            flex: 1,
            maxWidth: width * 0.45,
            height: bar * 0.56,
            borderRadius: bar,
            background: dark ? "rgba(255,255,255,0.06)" : "#ffffff",
            color: dark ? "rgba(255,255,255,0.55)" : "#667085",
            fontSize: bar * 0.32,
            display: "flex",
            alignItems: "center",
            padding: `0 ${bar * 0.4}px`,
            fontWeight: 500,
          }}
        >
          {url.replace(/^https?:\/\//, "").replace(/\/$/, "")}
        </span>
      </div>
      <div style={{ position: "relative", flex: 1, overflow: "hidden" }}>{children}</div>
    </div>
  );
};

/** A mouse pointer that glides to a point and clicks (with a ripple). */
export const Cursor: React.FC<{ from: { x: number; y: number }; to: { x: number; y: number }; start: number; travel: number; size: number }> = ({
  from,
  to,
  start,
  travel,
  size,
}) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [start, start + travel], [0, 1], { ...clamp, easing: easeInOut });
  // A slight arc, the way a hand moves.
  const x = from.x + (to.x - from.x) * t;
  const y = from.y + (to.y - from.y) * t - Math.sin(t * Math.PI) * size * 1.2;
  const clickAt = start + travel + 2;
  const press = interpolate(frame, [clickAt, clickAt + 3, clickAt + 7], [1, 0.82, 1], clamp);
  const ripple = interpolate(frame, [clickAt, clickAt + 16], [0, 1], clamp);
  const appear = interpolate(frame, [start - 6, start], [0, 1], clamp);
  return (
    <>
      {frame >= clickAt && (
        <div
          style={{
            position: "absolute",
            left: to.x - size * 1.6 * ripple,
            top: to.y - size * 1.6 * ripple,
            width: size * 3.2 * ripple,
            height: size * 3.2 * ripple,
            borderRadius: "50%",
            border: `${Math.max(2, size * 0.12)}px solid rgba(255,255,255,${0.9 * (1 - ripple)})`,
            boxShadow: `0 0 0 ${size * 0.1}px rgba(0,0,0,${0.25 * (1 - ripple)})`,
          }}
        />
      )}
      <svg
        width={size}
        height={size * 1.3}
        viewBox="0 0 20 26"
        style={{ position: "absolute", left: x, top: y, opacity: appear, transform: `scale(${press})`, transformOrigin: "0 0", filter: "drop-shadow(0 3px 6px rgba(0,0,0,0.35))" }}
      >
        <path d="M1 1 L1 20 L6 15.5 L9.5 24 L13 22.5 L9.6 14.3 L16.5 14.3 Z" fill="#111" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    </>
  );
};

/** Readable text on any background: pick black or white against a colour. */
export function onColor(hex: string): string {
  const m = hex.replace("#", "").match(/^([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i);
  if (!m) return "#ffffff";
  const [r, g, b] = [m[1], m[2], m[3]].map((h) => parseInt(h, 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return lum > 0.45 ? "#0c111d" : "#ffffff";
}

function luminance(hex: string): number {
  const m = hex.replace("#", "").match(/^([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i);
  if (!m) return 0;
  const [r, g, b] = [m[1], m[2], m[3]].map((h) => parseInt(h, 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** The logo, cut from a screenshot of the site. An app-icon-shaped logo gets rounded corners (so the
 * header's colour in its corners disappears); a wordmark on a background that would clash sits on a
 * small chip of that background, like a sticker, instead of a hard rectangle. */
export const Logo: React.FC<{ brand: { logo?: string; logoAspect?: number; logoBg?: string; colors: { bg: string } }; height: number; style?: React.CSSProperties }> = ({
  brand,
  height,
  style,
}) => {
  if (!brand.logo) return null;
  const aspect = brand.logoAspect || 1;
  const img = <Img src={staticFile(brand.logo)} style={{ height, width: height * aspect, display: "block", objectFit: "contain" }} />;
  if (aspect > 0.8 && aspect < 1.25) {
    return <div style={{ borderRadius: height * 0.24, overflow: "hidden", boxShadow: "0 10px 40px rgba(0,0,0,0.25)", ...style }}>{img}</div>;
  }
  const bg = brand.logoBg;
  const la = bg ? luminance(bg) : 0, lb = luminance(brand.colors.bg);
  const clash = bg && (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05) > 1.6;
  if (!clash) return <div style={style}>{img}</div>;
  return (
    <div style={{ background: bg, padding: `${height * 0.28}px ${height * 0.45}px`, borderRadius: height * 0.36, boxShadow: "0 10px 40px rgba(0,0,0,0.25)", ...style }}>
      {img}
    </div>
  );
};
