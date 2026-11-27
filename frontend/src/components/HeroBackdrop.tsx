"use client";

import dynamic from "next/dynamic";

/** Motion backgrounds for Home's hero, tinted olive. Try them with ?hero=<key> in the address bar.
 *  "dark" is the original; the rest sit on a light base. */
const SoftAurora = dynamic(() => import("@/components/reactbits/SoftAurora"), { ssr: false });
const Topography = dynamic(() => import("@/components/reactbits/Topography"), { ssr: false });
const Silk = dynamic(() => import("@/components/reactbits/Silk"), { ssr: false });
const Waves = dynamic(() => import("@/components/reactbits/Waves"), { ssr: false });
const LineWaves = dynamic(() => import("@/components/reactbits/LineWaves"), { ssr: false });
const Grainient = dynamic(() => import("@/components/reactbits/Grainient"), { ssr: false });
const Threads = dynamic(() => import("@/components/reactbits/Threads"), { ssr: false });

export const HEROES = ["dark", "topo", "silk", "waves", "lines", "threads", "grain"] as const;
export type HeroKey = (typeof HEROES)[number];

export function heroFromUrl(): HeroKey {
  if (typeof window === "undefined") return "dark";
  const k = new URLSearchParams(window.location.search).get("hero");
  return (HEROES as readonly string[]).includes(k || "") ? (k as HeroKey) : "dark";
}

export function HeroBackdrop({ kind, lite }: { kind: HeroKey; lite: boolean }) {
  if (kind === "dark") {
    return (
      <>
        {lite
          ? <div className="h-full w-full bg-[radial-gradient(60%_60%_at_80%_100%,rgba(132,204,22,0.35),transparent)]" />
          : <SoftAurora color1="#d9f99d" color2="#10b981" brightness={0.9} bandHeight={0.2} noiseAmplitude={0.6} speed={0.8} />}
        <div className="absolute inset-0 bg-[linear-gradient(100deg,rgba(21,26,14,0.92)_0%,rgba(21,26,14,0.7)_45%,rgba(21,26,14,0.25)_100%)]" />
      </>
    );
  }
  // Light: the motion sits under a white wash on the left, so the headline always reads.
  const wash = <div className="absolute inset-0 bg-[linear-gradient(100deg,rgba(255,255,255,0.94)_0%,rgba(255,255,255,0.78)_42%,rgba(255,255,255,0.1)_100%)]" />;
  if (lite) {
    return <><div className="h-full w-full bg-[radial-gradient(70%_80%_at_85%_100%,rgba(188,198,133,0.55),transparent),linear-gradient(#fbfbf6,#f3f5e6)]" />{wash}</>;
  }
  const bg = (() => {
    switch (kind) {
      case "topo": return <Topography lightMode color="#556b2f" lineCount={22} lineWidth={1.2} speed={0.5} opacity={0.9} mouseInteraction hoverEffect="lift" />;
      case "silk": return <Silk lightMode color="#c9d29a" sheenColor="#f5f6ec" speed={0.6} />;
      case "waves": return <Waves lightMode lineColor="#8c9a4b" accentColor="#556b2f" backgroundColor="transparent" speed={0.6} opacity={0.8} />;
      case "lines": return <LineWaves lightMode color1="#556b2f" color2="#8c9a4b" color3="#bcc685" speed={0.4} opacity={0.9} />;
      case "grain": return <Grainient lightMode colors={["#f5f6ec", "#d6dcb0", "#8c9a4b", "#f5f6ec"]} speed={0.4} grainAmount={0.06} />;
      case "threads": return <Threads color="#556b2f" accentColor="#8c9a4b" amplitude={1} distance={0.2} enableMouseInteraction />;
      default: return null;
    }
  })();
  return <><div className="absolute inset-0 bg-[#fbfbf6]" /><div className="absolute inset-0">{bg}</div>{wash}</>;
}
