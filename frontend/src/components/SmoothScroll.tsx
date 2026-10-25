"use client";

import { useEffect } from "react";
import Lenis from "lenis";

export type SmoothScrollMode = "auto" | "enabled" | "disabled";

export const SMOOTH_SCROLL_STORAGE_KEY = "efl:smooth-scroll-mode";
export const SMOOTH_SCROLL_MODE_CHANGE_EVENT = "efl:smooth-scroll-mode-change";

let activeLenis: Lenis | null = null;
let modalPauseCount = 0;

function isSmoothScrollMode(value: unknown): value is SmoothScrollMode {
  return value === "auto" || value === "enabled" || value === "disabled";
}

export function readSmoothScrollMode(): SmoothScrollMode {
  if (typeof window === "undefined") return "auto";

  try {
    const saved = window.localStorage.getItem(SMOOTH_SCROLL_STORAGE_KEY);
    return isSmoothScrollMode(saved) ? saved : "auto";
  } catch {
    return "auto";
  }
}

export function applySmoothScrollMode(mode: SmoothScrollMode): void {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.setItem(SMOOTH_SCROLL_STORAGE_KEY, mode);
  } catch {
    // Storage can be blocked; the change event still applies this choice in this tab.
  }

  window.dispatchEvent(
    new CustomEvent<SmoothScrollMode>(SMOOTH_SCROLL_MODE_CHANGE_EVENT, { detail: mode }),
  );
}

export function getActiveLenis(): Lenis | null {
  return activeLenis;
}

export function pauseSmoothScroll(): void {
  modalPauseCount += 1;
  activeLenis?.stop();
}

export function resumeSmoothScroll(): void {
  modalPauseCount = Math.max(0, modalPauseCount - 1);
  if (modalPauseCount === 0) activeLenis?.start();
}

export default function SmoothScroll() {
  useEffect(() => {
    let mode = readSmoothScrollMode();
    let reducedMotionQuery: MediaQueryList | null = null;
    let rafId = 0;

    const stopFrameLoop = () => {
      if (rafId) window.cancelAnimationFrame(rafId);
      rafId = 0;
    };

    const destroyLenis = () => {
      stopFrameLoop();
      activeLenis?.destroy();
      activeLenis = null;
    };

    const configure = (nextMode: SmoothScrollMode) => {
      mode = nextMode;

      if (mode === "auto") {
        if (!reducedMotionQuery) {
          reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
          reducedMotionQuery.addEventListener("change", onReducedMotionChange);
        }
      } else if (reducedMotionQuery) {
        reducedMotionQuery.removeEventListener("change", onReducedMotionChange);
        reducedMotionQuery = null;
      }

      destroyLenis();

      if (mode === "disabled" || (mode === "auto" && reducedMotionQuery?.matches)) {
        return;
      }

      activeLenis = new Lenis({
        lerp: 0.085,
        wheelMultiplier: 1,
        smoothWheel: true,
        syncTouch: false,
        anchors: true,
        autoRaf: false,
        stopInertiaOnNavigate: true,
        respectReducedMotion: mode !== "enabled",
      });

      if (modalPauseCount > 0) activeLenis.stop();

      const tick = (time: number) => {
        activeLenis?.raf(time);
        rafId = window.requestAnimationFrame(tick);
      };
      rafId = window.requestAnimationFrame(tick);
    };

    const onReducedMotionChange = () => {
      if (mode === "auto") configure("auto");
    };

    const onModeChange = (event: Event) => {
      const requestedMode = (event as CustomEvent<unknown>).detail;
      configure(isSmoothScrollMode(requestedMode) ? requestedMode : readSmoothScrollMode());
    };

    configure(mode);
    window.addEventListener(SMOOTH_SCROLL_MODE_CHANGE_EVENT, onModeChange);

    return () => {
      window.removeEventListener(SMOOTH_SCROLL_MODE_CHANGE_EVENT, onModeChange);
      reducedMotionQuery?.removeEventListener("change", onReducedMotionChange);
      reducedMotionQuery = null;
      destroyLenis();
    };
  }, []);

  return null;
}
