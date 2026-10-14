"use client";

import { createContext, useContext, useRef, type ReactNode } from "react";
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
