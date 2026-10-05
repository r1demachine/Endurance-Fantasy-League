"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";

/* Живая пыль: мерцающие искры + быстрый туман.
   Каждый шар после завершения цикла ПЕРЕРОЖДАЕТСЯ:
   новая случайная позиция, новое случайное направление. */

interface Spark {
  id: number; left: string; top: string; size: number;
  delay: number; dur: number; color: string;
}

interface Frame {
  left: number; top: number; size: number;
  dur: number; delay: number;
  dx: number; dy: number;   // конечное смещение
  mx: number; my: number;   // промежуточная точка (кривизна траектории)
}

const SPARK_COLORS = ["#ffffff", "#ffd500", "#f6b8d0", "#c7d2fe"];
const BLOB_COLORS = [
  "rgba(88,102,242,0.20)",
  "rgba(246,184,208,0.16)",
  "rgba(255,213,0,0.12)",
  "rgba(255,255,255,0.10)",
  "rgba(88,102,242,0.14)",
  "rgba(246,184,208,0.12)",
];

function rand(min: number, max: number) {
  return Math.random() * (max - min) + min;
}

/* 🎲 Случайный кадр жизни шара: позиция + направление под любым углом */
function makeFrame(first: boolean): Frame {
  const angle = rand(0, Math.PI * 2);          // направление: любой угол 0–360°
  const dist = rand(80, 240);                  // дальность полёта
  const midAngle = angle + rand(-1.4, 1.4);    // отклонение середины → кривая траектория
  const midDist = dist * rand(0.35, 0.8);
  return {
    left: rand(-15, 95),
    top: rand(-15, 95),
    size: rand(140, 340),
    dur: rand(9, 15),
    delay: first ? rand(0, 3) : rand(0, 1.2),
    dx: Math.cos(angle) * dist,
    dy: Math.sin(angle) * dist,
    mx: Math.cos(midAngle) * midDist,
    my: Math.sin(midAngle) * midDist,
  };
}

/* 💨 Один шар: отжил цикл → переродился с новым рандомом */
function FastBlob({ color }: { color: string }) {
  const [cycle, setCycle] = useState(0);
  const f = useMemo(() => makeFrame(cycle === 0), [cycle]);

  return (
    <motion.div
      key={cycle}
      className="absolute rounded-full"
      style={{
        left: `${f.left}%`,
        top: `${f.top}%`,
        width: f.size,
        height: f.size,
        backgroundColor: color,
        filter: "blur(40px)",
      }}
      initial={{ x: 0, y: 0, opacity: 0, scale: 0.8 }}
      animate={{
        x: [0, f.mx, f.dx],
        y: [0, f.my, f.dy],
        opacity: [0, 0.9, 0],
        scale: [0.8, 1.1, 0.9],
      }}
      transition={{ duration: f.dur, delay: f.delay, ease: "easeInOut" }}
      onAnimationComplete={() => setCycle((c) => c + 1)}
    />
  );
}

export default function DreamDust() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const sparks = useMemo<Spark[]>(
    () =>
      Array.from({ length: 26 }, (_, i) => ({
        id: i,
        left: `${rand(0, 100)}%`,
        top: `${rand(0, 100)}%`,
        size: rand(2, 5),
        delay: rand(0, 3),
        dur: rand(1.2, 2.6),
        color: SPARK_COLORS[Math.floor(rand(0, SPARK_COLORS.length))],
      })),
    []
  );

  if (!mounted) return null;

  return (
    <div className="fixed inset-0 z-[55] pointer-events-none overflow-hidden" aria-hidden="true">
      {/* ✨ искры */}
      {sparks.map((s) => (
        <motion.span
          key={`s${s.id}`}
          className="absolute rounded-full"
          style={{ left: s.left, top: s.top, width: s.size, height: s.size, backgroundColor: s.color }}
          animate={{ opacity: [0, 1, 0], scale: [0.6, 1.2, 0.6] }}
          transition={{ duration: s.dur, delay: s.delay, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}

      {/* 💨 шары тумана — каждый со своим жизненным циклом и рандомом */}
      {BLOB_COLORS.map((color, i) => (
        <FastBlob key={i} color={color} />
      ))}
    </div>
  );
}