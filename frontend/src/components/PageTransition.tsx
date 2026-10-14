"use client";

import { usePathname } from "next/navigation";
import { AnimatePresence, motion, type Variants } from "framer-motion";
import { useRef, type ReactNode } from "react";

const EASE = [0.22, 1, 0.36, 1] as const;

const pageVariants: Variants = {
  initial: { opacity: 0 },
  animate: {
    opacity: 1,
    transition: { duration: 0.18, ease: EASE, when: "beforeChildren" },
  },
  exit: {
    opacity: 0,
    transition: { duration: 0.14, ease: EASE, when: "afterChildren" },
  },
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
  initial: { opacity: 0, y: 16 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.26, ease: EASE },
  },
  exit: {
    opacity: 0,
    y: -12,
    transition: { duration: 0.16, ease: EASE },
  },
};

export default function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const pageRef = useRef<HTMLDivElement>(null);

  // Query-only changes keep the same pathname/key, so they update the page without
  // replaying the full-page transition. Exited routes are not kept in a custom cache.
  const clearAnimationStyles = () => {
    const node = pageRef.current;
    if (!node) return;
    // Keep this cleanup for any motion styles that could establish a containing block.
    // Settings and pause dialogs are portaled as an extra safeguard.
    node.style.removeProperty("transform");
    node.style.removeProperty("filter");
    node.style.removeProperty("clip-path");
  };

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        ref={pageRef}
        key={pathname}
        variants={pageVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        onAnimationComplete={clearAnimationStyles}
        className="relative z-10 w-full min-h-screen"
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
