"use client";

import { useEffect } from "react";
import Lenis from "lenis";

export default function SmoothScroll() {
  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let lenis: Lenis | null = null;
    let rafId = 0;

    const stop = () => {
      if (rafId) window.cancelAnimationFrame(rafId);
      rafId = 0;
      lenis?.destroy();
      lenis = null;
    };

    const start = () => {
      if (reducedMotion.matches || lenis) return;

      lenis = new Lenis({
        duration: 1.35,
        easing: (t) => t < 0.5
          ? 4 * t * t * t
          : 1 - Math.pow(-2 * t + 2, 3) / 2,
        smoothWheel: true,
        wheelMultiplier: 0.85,
        touchMultiplier: 1.1,
        syncTouch: true,
        anchors: true,
        autoRaf: false,
        allowNestedScroll: true,
        stopInertiaOnNavigate: true,
        respectReducedMotion: true,
      });

      const tick = (time: number) => {
        lenis?.raf(time);
        rafId = window.requestAnimationFrame(tick);
      };
      rafId = window.requestAnimationFrame(tick);
    };

    const sync = () => {
      stop();
      start();
    };

    sync();
    reducedMotion.addEventListener("change", sync);

    return () => {
      reducedMotion.removeEventListener("change", sync);
      stop();
    };
  }, []);

  return null;
}
