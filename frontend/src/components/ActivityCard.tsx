"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

interface Act {
  name: string; sport: string; distance_km: number; moving_time_min: number;
  xp: number; base_xp: number; rate_per_hour: number;
  intensity_multiplier: number; intensity_category: string; intensity_reason: string;
  sleep_multiplier: number; sleep_hours: number | null;
  streak_multiplier: number; streak_reason: string; date: string;
}

const CAT_COLOR: Record<string, string> = {
  LOW: "text-[#16a34a]", MEDIUM: "text-[#5866f2]", HIGH: "text-[#ff4b26]",
  UNKNOWN: "text-[#999]",
};
const nonOne = (v: number) => Math.abs((v ?? 1) - 1) > 0.001;

function Row({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-2 border-b border-black/10 last:border-b-0">
      <div className="min-w-0">
        <p className="text-[9px] font-bold tracking-widest uppercase text-[#666]">{label}</p>
        {sub && <p className="text-[10px] text-[#666] mt-0.5 leading-snug">{sub}</p>}
      </div>
      <p className={`font-display text-lg shrink-0 ${accent || ""}`}>{value}</p>
    </div>
  );
}

export default function ActivityCard({ act }: { act: Act }) {
  const [open, setOpen] = useState(false);
  const catColor = CAT_COLOR[act.intensity_category] || "text-[#111]";

  return (
    <div className="border-b-2 border-black last:border-b-0">
      {/* строка тренировки */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full grid grid-cols-[1fr_auto] items-center gap-3 px-4 py-3 text-left hover:bg-black/5 transition-colors"
      >
        <div className="min-w-0">
          <p className="font-bold uppercase tracking-wide text-sm truncate">{act.name}</p>
          <p className="text-[10px] text-[#666] font-bold tracking-widest uppercase mt-0.5">
            {act.date} · {act.sport} · {act.distance_km} km · {act.moving_time_min} мин
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className={`font-display text-xl ${catColor}`}>+{Math.round(act.xp)} XP</span>
          <span className="text-[#666]">{open ? "▲" : "▼"}</span>
        </div>
      </button>

      {/* разбивка */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-1 bg-[#f4f4f0] border-t-2 border-black/10">
              

              
              {/* Длительность: формула + результат */}
              <div className="flex items-center justify-between gap-3 py-2 border-b border-black/10">
                <p className="text-[9px] font-bold tracking-widest uppercase text-[#666]">Длительность</p>
                <div className="text-right">
                  <p className="font-display text-sm">
                    {act.moving_time_min} мин × {act.rate_per_hour} XP/ч
                  </p>
                  <p className="font-display text-lg text-[#ff4b26]">
                    = {act.base_xp} XP
                  </p>
                </div>
              </div>
              <Row
                label="Сон"
                value={`×${act.sleep_multiplier.toFixed(2)}`}
                sub={act.sleep_hours != null ? `${act.sleep_hours}ч` : "нет данных → ×1.0"}
                accent={nonOne(act.sleep_multiplier) ? "text-[#5866f2]" : undefined}
              />
              
              {/* Интенсивность: категория + множитель */}
              <div className="flex items-center justify-between gap-3 py-2 border-b border-black/10">
                <div className="min-w-0">
                  <p className="text-[9px] font-bold tracking-widest uppercase text-[#666]">Интенсивность</p>
                  {act.intensity_reason && (
                    <p className="text-[10px] text-[#666] mt-0.5 leading-snug">{act.intensity_reason}</p>
                  )}
                </div>
                <div className="text-right shrink-0">
                  <p className={`font-display text-sm ${catColor}`}>
                    {act.intensity_category}
                  </p>
                  <p className={`font-display text-lg ${catColor}`}>
                    ×{act.intensity_multiplier.toFixed(2)}
                  </p>
                </div>
              </div>
              <Row
                label="Streak"
                value={`×${act.streak_multiplier.toFixed(2)}`}
                sub={act.streak_reason}
                accent={nonOne(act.streak_multiplier) ? "text-[#16a34a]" : undefined}
              />

              <div className="mt-3 pt-3 border-t-2 border-black">
                <p className="text-[10px] font-bold tracking-widest uppercase text-[#666]">Итог</p>
                <p className="font-display text-lg leading-tight mt-1">
                  {act.base_xp} × {act.sleep_multiplier.toFixed(2)} × {act.intensity_multiplier.toFixed(2)} × {act.streak_multiplier.toFixed(2)} = <span className="text-[#ff4b26]">{Math.round(act.xp)} XP</span>
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}