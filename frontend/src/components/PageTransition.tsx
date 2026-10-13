"use client";

import { usePathname } from "next/navigation";
import { AnimatePresence, motion, type Variants } from "framer-motion";
import { useRef, type ReactNode } from "react";

const ORDER: Record<string, number> = { "/dashboard": 1, "/profile": 2 };

type Dir = "home-in" | "home-out" | "right" | "left" | "fade";

function getDir(from: string, to: string): Dir {
  if (to === "/") return "home-in";
  if (from === "/") return "home-out";
  const o1 = ORDER[from] ?? 0;
  const o2 = ORDER[to] ?? 0;
  if (o2 > o1) return "right";
  if (o2 < o1) return "left";
  return "fade";
}

const EASE = [0.22, 1, 0.36, 1] as const;

const variants: Record<Dir, Variants> = {
  "home-in": {
    initial: { clipPath: "circle(0% at 50% 50%)", opacity: 0, filter: "blur(14px)" },
    animate: { clipPath: "circle(150% at 50% 50%)", opacity: 1, filter: "blur(0px)", transition: { duration: 0.8, ease: EASE } },
    exit: { opacity: 0, filter: "blur(12px)", transition: { duration: 0.45, ease: EASE } },
  },
  "home-out": {
    initial: { opacity: 0, filter: "blur(12px)" },
    animate: { opacity: 1, filter: "blur(0px)", transition: { duration: 0.6, ease: EASE } },
    exit: { clipPath: "circle(0% at 50% 50%)", opacity: 0, transition: { duration: 0.6, ease: EASE } },
  },
  right: {
    initial: { x: "100%" },
    animate: { x: 0, transition: { duration: 0.5, ease: EASE } },
    exit: { x: "-100%", transition: { duration: 0.5, ease: EASE } },
  },
  left: {
    initial: { x: "-100%" },
    animate: { x: 0, transition: { duration: 0.5, ease: EASE } },
    exit: { x: "100%", transition: { duration: 0.5, ease: EASE } },
  },
  fade: {
    initial: { opacity: 0 },
    animate: { opacity: 1, transition: { duration: 0.4 } },
    exit: { opacity: 0, transition: { duration: 0.3 } },
  },
};

export default function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  const pageRef = useRef<HTMLDivElement>(null);
  const lastPath = useRef(pathname);
  const dir = useRef<Dir>("fade");

  // Query-only changes keep the same pathname/key, so they update the page without
  // replaying the full-page transition. Exited routes are not kept in a custom cache.
  if (pathname !== lastPath.current) {
    dir.current = getDir(lastPath.current, pathname);
    lastPath.current = pathname;
  }

  const clearAnimationStyles = () => {
    const node = pageRef.current;
    if (!node) return;
    // transform/filter establish containing blocks for position:fixed descendants.
    // The settings modal is also portaled as an extra safeguard.
    node.style.removeProperty("transform");
    node.style.removeProperty("filter");
    node.style.removeProperty("clip-path");
  };

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        ref={pageRef}
        key={pathname}
        variants={variants[dir.current]}
        initial="initial"
        animate="animate"
        exit="exit"
        onAnimationComplete={clearAnimationStyles}
        className="w-full min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] relative overflow-hidden"
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}