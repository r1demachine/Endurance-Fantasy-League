"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "framer-motion";

/* 🎮 Пасхалка главной: ↑ ↓ ← → (или WASD / ц ы ф в, или тапы по стрелкам)
   → человечек бежит через экран справа налево. */

const SEQ = ["up", "down", "left", "right"] as const;
type Dir = (typeof SEQ)[number];

const KEYMAP: Record<string, Dir> = {
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
  w: "up", s: "down", a: "left", d: "right",
  W: "up", S: "down", A: "left", D: "right",
  // русская раскладка (те же клавиши)
  ц: "up", ы: "down", ф: "left", в: "right",
  Ц: "up", Ы: "down", Ф: "left", В: "right",
};

const ARROWS: { dir: Dir; sym: string }[] = [
  { dir: "up", sym: "↑" },
  { dir: "down", sym: "↓" },
  { dir: "left", sym: "←" },
  { dir: "right", sym: "→" },
];

export function useKonami() {
  const [progress, setProgress] = useState(0);
  const [running, setRunning] = useState(false);
  const progressRef = useRef(0);

  const feed = (dir: Dir) => {
    const p = progressRef.current;
    let next = dir === SEQ[p] ? p + 1 : dir === SEQ[0] ? 1 : 0;
    if (next === SEQ.length) {
      next = 0;
      setRunning(true); // 🏃 погнал!
    }
    progressRef.current = next;
    setProgress(next);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const dir = KEYMAP[e.key];
      if (dir) feed(dir);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return { progress, running, done: () => setRunning(false), press: feed };
}

/* Столбик стрелок: загорается оранжевым по мере ввода комбо; тапабельный на мобилке */
export function KonamiArrows({ progress, onPress }: { progress: number; onPress: (d: Dir) => void }) {
  return (
    <div className="flex flex-col items-center gap-1.5 py-2 text-base leading-none select-none">
      {ARROWS.map((a, i) => (
        <button
          key={a.dir}
          type="button"
          tabIndex={-1}
          onClick={() => onPress(a.dir)}
          className={`transition-colors duration-150 hover:text-[#5866f2] ${
            i < progress ? "text-[#ff4b26]" : "text-[#111]/30"
          }`}
          aria-label={a.dir}
        >
          {a.sym}
        </button>
      ))}
    </div>
  );
}

/* Человечек v3: чистый CSS-анимацией — без framer (надёжно как топор) */
export function Runner({ running, onDone }: { running: boolean; onDone: () => void }) {
  useEffect(() => {
    if (!running) return;
    console.log("🏃 RUNNER GO!");
    const t = setTimeout(onDone, 3000); // страховка: уберётся даже если animationend не стрельнёт
    return () => clearTimeout(t);
  }, [running]);

  if (!running) return null;

  return createPortal(
    <>
      <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[999] px-5 py-2 bg-[#ffd500] border-2 border-black font-display uppercase text-xl shadow-[4px_4px_0_#000]">
        Go! Go! Go!
      </div>
      <div
        className="runner-track fixed left-0 z-[999] pointer-events-none"
        style={{ top: "45%" }}
      >
        <span
          className="runner-bounce inline-block text-6xl md:text-7xl"
          style={{ filter: "drop-shadow(4px 4px 0 #000)" }}
        >
          🏃💨
        </span>
      </div>
    </>,
    document.body
  );
}