"use client";

import { useState } from "react";

import { num } from "@/lib/api";

type Point = { value: number; recorded_at: string };

/** Single-series line chart of the primary metric over time. */
export function MetricChart({ points, label }: { points: Point[]; label: string }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length === 0) {
    return <div className="grid h-44 place-items-center text-sm text-muted">No readings of “{label}” yet. Autopilot records it every cycle.</div>;
  }
  const W = 640;
  const H = 180;
  const P = { l: 44, r: 12, t: 12, b: 24 };
  const xs = points.map((p) => new Date(p.recorded_at).getTime());
  const ys = points.map((p) => p.value);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  let [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  if (y0 === y1) {
    y0 -= 1;
    y1 += 1;
  }
  const pad = (y1 - y0) * 0.1;
  y0 -= pad;
  y1 += pad;
  const sx = (x: number) => P.l + (x1 === x0 ? (W - P.l - P.r) / 2 : ((x - x0) / (x1 - x0)) * (W - P.l - P.r));
  const sy = (y: number) => P.t + (1 - (y - y0) / (y1 - y0)) * (H - P.t - P.b);
  const path = points.map((p, i) => `${i ? "L" : "M"}${sx(xs[i]).toFixed(1)},${sy(p.value).toFixed(1)}`).join(" ");
  const ticks = [y0 + pad, (y0 + y1) / 2, y1 - pad];
  const fmtDate = (t: number) => new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-48 w-full" onMouseLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={sy(t)} y2={sy(t)} stroke="#e5e7eb" strokeDasharray="3 3" />
            <text x={P.l - 6} y={sy(t) + 4} textAnchor="end" fontSize="11" fill="#65676b">
              {num(Math.round(t * 100) / 100)}
            </text>
          </g>
        ))}
        <text x={P.l} y={H - 6} fontSize="11" fill="#65676b">
          {fmtDate(x0)}
        </text>
        <text x={W - P.r} y={H - 6} fontSize="11" fill="#65676b" textAnchor="end">
          {fmtDate(x1)}
        </text>
        <path d={path} fill="none" stroke="#18181b" strokeWidth="2.25" strokeLinejoin="round" />
        {points.map((p, i) => (
          <circle
            key={i}
            cx={sx(xs[i])}
            cy={sy(p.value)}
            r={hover === i ? 5 : 3.5}
            fill="#18181b"
            stroke="white"
            strokeWidth="1.5"
            onMouseEnter={() => setHover(i)}
          />
        ))}
      </svg>
      {hover !== null && (
        <div className="pointer-events-none absolute right-2 top-1 rounded-md border border-line bg-white px-2 py-1 text-xs shadow-sm">
          <b className="tabular">{num(points[hover].value)}</b> {label} · {new Date(points[hover].recorded_at).toLocaleString()}
        </div>
      )}
    </div>
  );
}
