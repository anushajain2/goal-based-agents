"use client";

import { useEffect, useRef, useState } from "react";

/** Motion helpers shared by the homepage and the sign-in pages. */

/** True once the element has scrolled into view (and stays true), so bars grow in when seen. */
export function useInView<T extends Element>() {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return setSeen(true);
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } }, { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return [ref, seen] as const;
}

/** Touch screens (phones, tablets) and people who asked their system for less motion get still backgrounds and no
 *  tilt. Decided by the device, not the window width, so a narrow desktop window still moves. */
export function useLiteMotion() {
  const [lite, setLite] = useState(true);
  useEffect(() => {
    const q = window.matchMedia("(pointer: coarse), (prefers-reduced-motion: reduce)");
    const update = () => setLite(q.matches);
    update();
    q.addEventListener("change", update);
    return () => q.removeEventListener("change", update);
  }, []);
  return lite;
}

/** Steps through a little story once it's on screen (step goes 1, 2, 3... at the given times), holds the end,
 *  then plays it again. People who asked for less motion see the end straight away. */
export function useStory(times: number[], hold = 4000) {
  const [ref, seen] = useInView<HTMLDivElement>();
  const [step, setStep] = useState(0);
  const key = times.join(",");
  useEffect(() => {
    if (!seen) return;
    const at = key.split(",").map(Number);
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return setStep(at.length);
    let timers: number[] = [];
    const play = () => {
      setStep(0);
      timers = at.map((t, i) => window.setTimeout(() => setStep(i + 1), t));
      timers.push(window.setTimeout(play, at[at.length - 1] + hold));
    };
    play();
    return () => timers.forEach(clearTimeout);
  }, [seen, key, hold]);
  return [ref, step] as const;
}

/** Counts up to a number once it's on screen (eased), so stats feel live. Less motion: the number straight away. */
export function useCountUp(to: number, duration = 1100) {
  const [ref, seen] = useInView<HTMLSpanElement>();
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!seen) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return setV(to);
    let raf = 0;
    const start = performance.now();
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / duration);
      setV(to * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [seen, to, duration]);
  return [ref, v] as const;
}
