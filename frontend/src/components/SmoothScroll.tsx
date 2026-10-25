"use client";

import { useEffect } from "react";
import Lenis from "lenis";

export default function SmoothScroll() {
  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let lenis: Lenis | null = null;

    const syncMotionPreference = () => {
      if (reducedMotion.matches) {
        lenis?.destroy();
        lenis = null;
        return;
      }

      if (lenis) return;
      lenis = new Lenis({
        autoRaf: true,
        anchors: true,
        allowNestedScroll: true,
        duration: 1.1,
        easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
        smoothWheel: true,
        stopInertiaOnNavigate: true,
        respectReducedMotion: true,
      });
    };

    syncMotionPreference();
    reducedMotion.addEventListener("change", syncMotionPreference);

    return () => {
      reducedMotion.removeEventListener("change", syncMotionPreference);
      lenis?.destroy();
    };
  }, []);

  return null;
}
