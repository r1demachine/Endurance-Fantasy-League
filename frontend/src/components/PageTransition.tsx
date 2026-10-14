"use client";

import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion, type Variants } from "framer-motion";

type TransitionDirection = 1 | -1;

// Order follows the primary navigation in Header.tsx.
const ROUTE_ORDER: Record<string, number> = {
  "/": 0,
  "/dashboard": 1,
  "/compete": 2,
  "/profile": 3,
  "/login": 4,
};

const TransitionDirectionContext = createContext<TransitionDirection>(1);

export function useTransitionDirection(): TransitionDirection {
  return useContext(TransitionDirectionContext);
}

function routeOrder(pathname: string): number | null {
  if (Object.prototype.hasOwnProperty.call(ROUTE_ORDER, pathname)) {
    return ROUTE_ORDER[pathname];
  }
  if (pathname.startsWith("/u/")) return 5;
  return null;
}

function getTransitionDirection(from: string, to: string): TransitionDirection {
  const fromOrder = routeOrder(from);
  const toOrder = routeOrder(to);
  if (fromOrder !== null && toOrder !== null && fromOrder !== toOrder) {
    return toOrder > fromOrder ? 1 : -1;
  }
  return 1;
}

const EASE = [0.22, 1, 0.36, 1] as const;

// Main navigation pages coordinate their child containers instead of moving
// the whole page. Other routes retain a short fade as a fallback.
const containerPageVariants: Variants = {
  initial: { opacity: 1 },
  animate: { opacity: 1, transition: { when: "beforeChildren" } },
  exit: { opacity: 1, transition: { when: "afterChildren" } },
};

const fadePageVariants: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.2, ease: EASE } },
  exit: { opacity: 0, transition: { duration: 0.16, ease: EASE, when: "afterChildren" } },
};

export const sectionStaggerVariants: Variants = {
  initial: {
    transition: { when: "beforeChildren", staggerChildren: 0.075, delayChildren: 0.02 },
  },
  animate: {
    transition: { when: "beforeChildren", staggerChildren: 0.075, delayChildren: 0.02 },
  },
  exit: {
    transition: { when: "afterChildren", staggerChildren: 0.05, staggerDirection: 1 },
  },
};

export const sectionItemVariants: Variants = {
  initial: (direction: TransitionDirection = 1) => ({
    opacity: 0,
    x: direction > 0 ? "100%" : "-100%",
  }),
  animate: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.26, ease: EASE },
  },
  exit: (direction: TransitionDirection = 1) => ({
    opacity: 0,
    x: direction > 0 ? "-100%" : "100%",
    transition: { duration: 0.18, ease: EASE },
  }),
};

export default function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const pageRef = useRef<HTMLDivElement>(null);
  const lastPath = useRef(pathname);
  const directionRef = useRef<TransitionDirection>(1);

  // Smooth out mouse-wheel steps; touch, keyboard, zoom, and nested scroll panels
  // keep their native browser behavior. Respect the OS reduced-motion preference.
  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (reducedMotion.matches) return;

    const root = document.documentElement;
    let animationFrame = 0;
    let targetY = window.scrollY;
    let animating = false;
    let savedScrollBehavior = false;
    let previousScrollBehavior = "";
    let previousScrollBehaviorPriority = "";

    const restoreScrollBehavior = () => {
      if (!savedScrollBehavior) return;
      if (previousScrollBehavior) {
        root.style.setProperty(
          "scroll-behavior",
          previousScrollBehavior,
          previousScrollBehaviorPriority
        );
      } else {
        root.style.removeProperty("scroll-behavior");
      }
      savedScrollBehavior = false;
    };

    const animateScroll = () => {
      const currentY = window.scrollY;
      const distance = targetY - currentY;

      if (Math.abs(distance) < 0.75) {
        window.scrollTo(0, targetY);
        animationFrame = 0;
        animating = false;
        restoreScrollBehavior();
        return;
      }

      window.scrollTo(0, currentY + distance * 0.22);
      animationFrame = window.requestAnimationFrame(animateScroll);
    };

    const canInnerPanelScroll = (path: EventTarget[], deltaY: number) => {
      for (const item of path) {
        if (!(item instanceof HTMLElement) || item === root || item === document.body) continue;
        const overflowY = window.getComputedStyle(item).overflowY;
        if (!/(auto|scroll|overlay)/.test(overflowY)) continue;
        if (item.scrollHeight <= item.clientHeight + 1) continue;

        const canScroll = deltaY > 0
          ? item.scrollTop + item.clientHeight < item.scrollHeight - 1
          : item.scrollTop > 1;
        if (canScroll) return true;
      }
      return false;
    };

    const onWheel = (event: WheelEvent) => {
      if (
        event.defaultPrevented ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        event.deltaY === 0 ||
        Math.abs(event.deltaX) > Math.abs(event.deltaY)
      ) return;

      const path = event.composedPath();
      const usesNativeWheel = path.some((item) =>
        item instanceof HTMLElement &&
        item.matches("input, textarea, select, [contenteditable='true'], [contenteditable=''], [role='textbox'], [data-native-wheel-scroll]")
      );
      if (usesNativeWheel) return;

      let deltaY = event.deltaY;
      if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) deltaY *= 24;
      if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) deltaY *= window.innerHeight;
      if (canInnerPanelScroll(path, deltaY)) return;

      const maxY = Math.max(0, root.scrollHeight - window.innerHeight);
      if (maxY <= 0) return;
      const startingY = animating ? targetY : window.scrollY;
      const nextTarget = Math.max(0, Math.min(maxY, startingY + deltaY));
      if (Math.abs(nextTarget - startingY) < 0.5) return;

      event.preventDefault();

      if (!animating) {
        previousScrollBehavior = root.style.getPropertyValue("scroll-behavior");
        previousScrollBehaviorPriority = root.style.getPropertyPriority("scroll-behavior");
        savedScrollBehavior = true;
        root.style.setProperty("scroll-behavior", "auto", "important");
        targetY = window.scrollY;
        animating = true;
      }

      targetY = nextTarget;
      if (!animationFrame) animationFrame = window.requestAnimationFrame(animateScroll);
    };

    window.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      window.removeEventListener("wheel", onWheel);
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      animationFrame = 0;
      animating = false;
      restoreScrollBehavior();
    };
  }, [pathname]);

  // The pathname key intentionally ignores query-only updates (settings, tabs,
  // and stat ranges), so they don't replay the page transition.
  if (pathname !== lastPath.current) {
    directionRef.current = getTransitionDirection(lastPath.current, pathname);
    lastPath.current = pathname;
  }

  const isContainerPage =
    pathname === "/dashboard" || pathname === "/compete" || pathname === "/profile";

  const clearAnimationStyles = () => {
    const node = pageRef.current;
    if (!node) return;
    // Keep this cleanup so transform/filter/clip-path never trap fixed descendants.
    // Settings and pause dialogs are portaled as an extra safeguard.
    node.style.removeProperty("transform");
    node.style.removeProperty("filter");
    node.style.removeProperty("clip-path");
  };

  return (
    <TransitionDirectionContext.Provider value={directionRef.current}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          ref={pageRef}
          key={pathname}
          variants={isContainerPage ? containerPageVariants : fadePageVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          onAnimationComplete={clearAnimationStyles}
          className="relative z-10 w-full min-h-screen"
        >
          {children}
        </motion.div>
      </AnimatePresence>
    </TransitionDirectionContext.Provider>
  );
}
