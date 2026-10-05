"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { KonamiArrows, Runner, useKonami } from "@/components/KonamiRunner";
import { useSeason } from "@/lib/seasons";
import { useTheme } from "@/lib/theme";

/* ✦ Звезда-искорка (Dream) */
function Star({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden>
      <path d="M12 0c1 8 4 11 12 12-8 1-11 4-12 12-1-8-4-11-12-12 8-1 11-4 12-12z" />
    </svg>
  );
}

/* 🏷 Стикер Caveat — нарушает строгую рамку (Dream-вставка в BRUT) */
function Sticker({ className = "", children }: { className?: string; children: ReactNode }) {
  return (
    <motion.div
      animate={{ y: [0, -5, 0] }}
      transition={{ repeat: Infinity, duration: 4, ease: "easeInOut" }}
      className={`font-sticker absolute z-30 px-3 py-0.5 rounded-lg border-2 border-black shadow-[3px_4px_0_rgba(0,0,0,0.35)] text-lg md:text-xl font-bold whitespace-nowrap ${className}`}
    >
      {children}
    </motion.div>
  );
}

/* 💭 Пузырь сна */
function DreamBubble({ emoji, className = "", delay = 0 }: { emoji: string; className?: string; delay?: number }) {
  return (
    <motion.div
      animate={{ y: [0, -9, 0] }}
      transition={{ repeat: Infinity, duration: 3.5, delay, ease: "easeInOut" }}
      className={`absolute z-20 flex items-center justify-center rounded-full bg-[#f4f4f0] border-2 border-black shadow-[3px_3px_0_rgba(0,0,0,0.4)] ${className}`}
    >
      <span>{emoji}</span>
    </motion.div>
  );
}

/* 🌐 Глобус (BRUT) */
function GlobeIcon() {
  return (
    <svg viewBox="0 0 100 100" className="w-9 h-9 md:w-12 md:h-12" fill="none" stroke="#111" strokeWidth="5">
      <circle cx="50" cy="50" r="44" />
      <ellipse cx="50" cy="50" rx="20" ry="44" />
      <line x1="6" y1="50" x2="94" y2="50" />
      <line x1="13" y1="28" x2="87" y2="28" />
      <line x1="13" y1="72" x2="87" y2="72" />
    </svg>
  );
}

export default function Home() {
  const { progress, running, done, press } = useKonami();
  const season = useSeason();
  const { theme, toggle } = useTheme();
  const mechanics = [
    { n: "01", title: "Sync data", tag: "Strava / Garmin / Wahoo", cell: "bg-[#ffd500]", icon: "🔌" },
    { n: "02", title: "XP = Load × IF × Sleep", tag: "Quality over quantity", cell: "bg-[#ff4b26] text-white", icon: "⚡" },
    { n: "03", title: "Global rating", tag: "Friends & streaks", cell: "bg-[#5866f2] text-white", icon: "🏆" },
  ];

  return (
    <main className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] p-2 sm:p-4 md:p-6 text-[#111] relative overflow-hidden flex flex-col">
      {/* ✦ Звёзды на мечтательном фоне (Dream) */}
      <Star className="absolute w-6 h-6 text-white/80 top-[5%] left-[4%] animate-pulse" />
      <Star className="absolute w-4 h-4 text-white/70 top-[14%] right-[7%] animate-pulse" />
      <Star className="absolute w-5 h-5 text-white/80 bottom-[12%] left-[9%] animate-pulse" />
      <Star className="absolute w-7 h-7 text-[#ffd500] bottom-[6%] right-[5%] animate-pulse" />
      <Star className="absolute w-3 h-3 text-white/60 top-[40%] left-[2%] animate-pulse" />

      {/* 📰 Газетная рамка (BRUT) поверх сна */}
      <div className="relative max-w-[1400px] w-full mx-auto border-2 border-black bg-[#f4f4f0] flex-1 flex flex-col breathe-table">

        {/* ===== ВЕРХНЯЯ ПАНЕЛЬ (BRUT) ===== */}
        <div className="flex md:grid md:grid-cols-[auto_1fr_1fr_1fr_auto] border-b-2 border-black">
          <div className="px-4 py-4 md:border-r-2 border-black font-display text-2xl md:text-3xl">
            FANTASY<span className="text-[#ff4b26]">.</span>
          </div>
          <div className="hidden md:flex flex-col justify-center px-4 border-r-2 border-black text-[10px] font-bold tracking-widest uppercase leading-relaxed">
            <span>
              Season {String(season.num).padStart(3, "0")} {" "}
              <span
                className="transition-colors duration-700"
                style={{ color: season.color }}
              >
                {season.flower} ✿
              </span>
            </span>
            <span>Endurance Fantasy league</span>
          </div>
          <Link href="/dashboard" className="hidden md:flex items-center px-4 border-r-2 border-black text-[10px] font-bold tracking-widest uppercase hover:bg-black hover:text-white transition-colors">
            Dashboard
          </Link>
          <Link href="/profile" className="hidden md:flex items-center px-4 border-r-2 border-black text-[10px] font-bold tracking-widest uppercase hover:bg-black hover:text-white transition-colors">
            Profile
          </Link>
          <Link href="/dashboard" className="ml-auto md:ml-0 bg-[#ffd500] px-4 py-4 text-[10px] font-bold tracking-widest uppercase flex items-center gap-2 border-l-2 border-black hover:bg-black hover:text-white transition-colors">
            Start playing ↗
          </Link>
        </div>

        {/* ===== HERO ===== */}
        <div className="relative grid md:grid-cols-2 border-b-2 border-black flex-1">

          {/* Сонные стикеры вылезают за строгую рамку (гибрид) */}
          <Sticker className="-top-3 left-4 md:left-8 bg-[#f6b8d0] text-black rotate-[-4deg]">RideMachineCC</Sticker>
          <Sticker className="bottom-6 right-4 md:right-8 bg-[#5866f2] text-white rotate-[3deg] z-30">xp капает за сон!</Sticker>

          {/* Левая колонка */}
          <div className="p-5 md:p-10 flex flex-col gap-6 md:border-r-2 border-black justify-center">
            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
              className="font-display uppercase leading-[0.88] text-6xl sm:text-7xl lg:text-8xl"
            >
              train <span className="text-[#5866f2]">hard</span><br />rest<br />harder<span className="text-[#ff4b26]">.</span>
            </motion.h1>

            <div className="flex items-center gap-3 text-[11px] font-bold tracking-widest uppercase">
              <span className="w-3 h-3 bg-[#f6b8d0] border-2 border-black inline-block shrink-0"></span>
              RideMachine Endurance Fantasy league.
            </div>

            <div className="flex flex-wrap gap-3">
              <Link href="/dashboard" className="inline-flex items-center gap-3 border-2 border-black px-5 py-3 text-[11px] font-bold tracking-widest uppercase hover:bg-black hover:text-white transition-colors">
                View dashboard ↗
              </Link>
              <Link href="/profile" className="inline-flex items-center gap-3 bg-[#5866f2] text-white px-5 py-3 text-[11px] font-bold tracking-widest uppercase border-2 border-black hover:bg-black transition-colors">
                Connect source ⚡
              </Link>
            </div>
          </div>

          {/* Правая колонка: оранжевый блок + спящий атлет + пузыри снов */}
          <div className="relative flex flex-col min-h-[300px] md:min-h-0">
            <div className="p-5 md:p-8 flex items-start justify-between gap-4 border-b-2 border-black">
              <p className="text-xs md:text-sm font-bold uppercase tracking-wide max-w-[240px]">
                A fantasy league where training plan and rest multiplies your workout.
              </p>
              <div className="flex items-center gap-3 shrink-0">
                <span className="w-9 h-9 border-2 border-black flex items-center justify-center font-bold text-lg">+</span>
                <span className="w-16 h-16 md:w-20 md:h-20 bg-[#ff4b26] border-2 border-black flex items-center justify-center">
                  <GlobeIcon />
                </span>
              </div>
            </div>

            {/* "Фото" атлета в оранжевом (BRUT) с мечтательными пузырями (Dream) */}
                        
                        {/* "Фото" атлета в оранжевом (BRUT) с мечтательными пузырями (Dream) */}
            <div className="relative flex-1 bg-[#ff4b26] overflow-hidden flex items-center justify-center">
              {/* розовые облака-пятна (Dream) — фон по углам */}
              <div className="absolute -left-6 top-6 w-28 h-32 bg-[#f6b8d0] rounded-[50%_50%_40%_60%] opacity-90 z-0" />
              <div className="absolute right-4 top-10 w-16 h-16 bg-[#f6b8d0] rounded-[60%_40%_55%_45%] opacity-90 z-0" />

              {/* ЕДИНАЯ КОМПОЗИЦИЯ: атлет + пузыри */}
              <div className="relative z-10 flex flex-col items-center justify-center">
                
                {/* 💭 Пузыри снов — дуга над головой внутри композиции */}
                <div className="relative w-full h-24 md:h-32 mb-[-1rem] md:mb-[-2rem]">
                  <DreamBubble emoji="🚴" className="w-12 h-12 md:w-16 md:h-16 text-2xl md:text-3xl left-[-10%] bottom-[10%]" delay={0.2} />
                  <DreamBubble emoji="🏃" className="w-10 h-10 md:w-14 md:h-14 text-xl md:text-2xl left-1/2 -translate-x-1/2 bottom-[60%]" delay={1} />
                  <DreamBubble emoji="🏆" className="w-12 h-12 md:w-16 md:h-16 text-2xl md:text-3xl right-[-10%] bottom-[10%]" delay={0.6} />
                  
                  {/* ✦ Звёзды вокруг головы */}
                  <Star className="absolute w-5 h-5 text-white left-[-25%] bottom-[40%] animate-pulse" />
                  <Star className="absolute w-4 h-4 text-[#ffd500] right-[-25%] bottom-[45%] animate-pulse" />
                </div>

                {/* Спящий атлет ч/б (BRUT-обработка) */}
                <motion.span
                  animate={{ scale: [1, 1.04, 1] }}
                  transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
                  className="text-[8rem] md:text-[11rem] leading-none contrast-125 select-none"
                >
                  😴
                </motion.span>
              </div>
            </div>
          </div>
        </div>

        {/* ===== ЛЕНТА (BRUT-структура + Dream-цвета) ===== */}
        <div className="grid md:grid-cols-[auto_1fr_auto] border-b-2 border-black">
          <div className="px-2 border-r-2 border-black flex items-center justify-center bg-[#f4f4f0]">
            <KonamiArrows progress={progress} onPress={press} />
          </div>
          <div className="px-5 py-5 md:py-6 flex items-center justify-between gap-4 text-sm md:text-lg font-bold uppercase tracking-wide">
            <span>We don't follow chaos.<br />We set the plan.</span>
            <span className="text-2xl">→</span>
          </div>
          <div className="bg-[#5866f2] text-white border-t-2 md:border-t-0 md:border-l-2 border-black px-5 py-4 flex items-center justify-between gap-6 text-[11px] font-bold tracking-widest uppercase">
            <span>Change theme?<br />over here!</span>
            <button
              type="button"
              onClick={toggle}
              title="Переключить тему"
              className="w-9 h-9 bg-[#ffd500] text-black rounded-full inline-flex items-center justify-center shrink-0 border-2 border-black hover:rotate-45 transition-transform"
            >
              {theme === "dark" ? "☀" : "🌙"}
            </button>
          </div>
        </div>

        {/* ===== МЕХАНИКИ 01/02/03 (BRUT-сетка, Dream-палитра ячеек) ===== */}
        <div className="grid md:grid-cols-3">
          {mechanics.map((m, i) => (
            <div key={m.n} className={`flex items-center gap-4 p-5 md:p-6 ${i < mechanics.length - 1 ? "border-b-2 md:border-b-0 md:border-r-2" : ""} border-black ${m.cell}`}>
              <span className="font-display text-5xl md:text-6xl shrink-0">{m.n}</span>
              <div className="min-w-0">
                <p className="font-bold uppercase tracking-wide text-sm md:text-base truncate">{m.title}</p>
                <p className="text-[10px] font-bold tracking-widest uppercase mt-1 opacity-80">{m.tag}</p>
              </div>
              <span className="text-2xl ml-auto shrink-0">{m.icon}</span>
            </div>
          ))}
        </div>
      </div>
      <Runner running={running} onDone={done} />
    </main>
  );
}