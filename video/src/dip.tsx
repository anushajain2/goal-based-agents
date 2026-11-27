import React from "react";
import { AbsoluteFill } from "remotion";
import type { TransitionPresentation, TransitionPresentationComponentProps } from "@remotion/transitions";

/**
 * A dip: the old scene leaves completely (fade, slight lift and blur), then the new one arrives.
 * Nothing overlaps, so two busy layouts never become a muddy double exposure.
 */
const Dip: React.FC<TransitionPresentationComponentProps<Record<string, never>>> = ({ children, presentationDirection, presentationProgress }) => {
  const p = presentationProgress;
  const leaving = presentationDirection === "exiting";
  const t = leaving ? Math.max(0, 1 - p * 2) : Math.max(0, p * 2 - 1); // first half out, second half in
  const offset = leaving ? -(1 - t) * 24 : (1 - t) * 24;
  return (
    <AbsoluteFill style={{ opacity: t, transform: `translateY(${offset}px) scale(${0.985 + 0.015 * t})`, filter: `blur(${(1 - t) * 6}px)` }}>
      {children}
    </AbsoluteFill>
  );
};

export const dip = (): TransitionPresentation<Record<string, never>> => ({ component: Dip, props: {} });
