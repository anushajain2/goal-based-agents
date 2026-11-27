"use client";

import dynamic from "next/dynamic";

/** The landing page's hero background. "dark" is the original (green northern lights on near-black);
 *  the rest are olive motion on a light base. Try them with ?hero=<key> in the address bar. */
const SoftAurora = dynamic(() => import("@/components/reactbits/SoftAurora"), { ssr: false });
const Topography = dynamic(() => import("@/components/reactbits/Topography"), { ssr: false });
const Silk = dynamic(() => import("@/components/reactbits/Silk"), { ssr: false });
const Waves = dynamic(() => import("@/components/reactbits/Waves"), { ssr: false });
const LineWaves = dynamic(() => import("@/components/reactbits/LineWaves"), { ssr: false });
const Grainient = dynamic(() => import("@/components/reactbits/Grainient"), { ssr: false });
const Threads = dynamic(() => import("@/components/reactbits/Threads"), { ssr: false });

export const HEROES = ["dark", "topo", "silk", "waves", "lines", "threads", "grain"] as const;
export type HeroKey = (typeof HEROES)[number];

/** The light base the motion sits on; the hero fades into it at the bottom. */
export const LIGHT_BASE = "#fbfbf6";

export function heroFromUrl(): HeroKey {
  if (typeof window === "undefined") return "dark";
  const k = new URLSearchParams(window.location.search).get("hero");
  return (HEROES as readonly string[]).includes(k || "") ? (k as HeroKey) : "dark";
}

export function HeroBackdrop({ kind, lite }: { kind: HeroKey; lite: boolean }) {
  if (kind === "dark") {
    return (
      <div aria-hidden className="absolute inset-0 overflow-hidden bg-ink">
        {lite
          ? <div className="h-full w-full bg-[radial-gradient(70%_40%_at_50%_45%,rgba(16,185,129,0.45),transparent)]" />
          : <SoftAurora color1="#d9f99d" color2="#10b981" brightness={1.15} bandHeight={0.45} noiseAmplitude={0.7} />}
        {/* Shade behind the headline only, so the aurora band below it stays bright. */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(42%_22%_at_50%_33%,rgba(0,0,0,0.5),transparent)]" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-b from-transparent to-ink" />
      </div>
    );
  }
  const bg = lite ? (
    <div className="h-full w-full bg-[radial-gradient(70%_50%_at_50%_100%,rgba(188,198,133,0.5),transparent)]" />
  ) : (() => {
    switch (kind) {
      case "topo": return <Topography lightMode color="#455824" lineCount={26} lineWidth={1.8} speed={0.5} opacity={1} mouseInteraction hoverEffect="lift" />;
      case "silk": return <Silk lightMode color="#c9d29a" sheenColor="#f5f6ec" speed={0.6} />;
      case "waves": return <Waves lightMode lineColor="#8c9a4b" accentColor="#556b2f" backgroundColor="transparent" speed={0.6} opacity={0.8} />;
      case "lines": return <LineWaves lightMode color1="#556b2f" color2="#8c9a4b" color3="#bcc685" speed={0.4} opacity={0.9} />;
      case "grain": return <Grainient lightMode colors={["#f5f6ec", "#d6dcb0", "#8c9a4b", "#f5f6ec"]} speed={0.4} grainAmount={0.06} />;
      case "threads": return <Threads color="#556b2f" accentColor="#8c9a4b" amplitude={1} distance={0.2} enableMouseInteraction />;
      default: return null;
    }
  })();
  return (
    <div aria-hidden className="absolute inset-0 overflow-hidden" style={{ background: LIGHT_BASE }}>
      <div className="absolute inset-0">{bg}</div>
      {/* A soft white glow behind the headline and the website box, so they always read. */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(46%_34%_at_50%_38%,rgba(255,255,255,0.9),transparent)]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24" style={{ background: `linear-gradient(to bottom, transparent, ${LIGHT_BASE})` }} />
    </div>
  );
}
