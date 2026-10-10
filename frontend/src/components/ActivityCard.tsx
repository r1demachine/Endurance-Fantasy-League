"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

interface Act {
  id: number;
  name: string;
  sport: string;
  date: string;
  distance_km: number;
  moving_time_min: number;
  xp: number;
  base_xp: number | null;
  rate_per_hour: number;
  intensity_multiplier: number;
  intensity_category: string;
  intensity_reason: string;
  sleep_multiplier: number;
  sleep_hours: number | null;
  streak_multiplier: number;
  streak_reason: string;

  // v6 fields
  tss_estimated?: boolean;
  is_long?: boolean;
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
            {act.base_xp == null ? (
              <div className="px-4 pb-4 pt-1 bg-[#f4f4f0] border-t-2 border-black/10 space-y-0">
                <Row label="XP за нагрузку" value={`+${Math.round(act.xp ?? 0)} XP`} />
                <Row
                  label="Источник нагрузки"
                  value={act.tss_estimated ? "оценка (duration × IF)" : "TSS Intervals"}
                />
                <Row label="Интенсивность" value={act.intensity_category ?? "UNKNOWN"} accent={catColor} />
                {act.is_long && (
                  <Row label="Long workout" value="+15 XP (недельный бонус)" accent="text-[#5866f2]" />
                )}
                <p className="text-[10px] text-[#666] pt-2">
                  Цель недели, регулярность и восстановление начисляются отдельными XP-событиями.
                </p>
              </div>
            ) : (
              <div className="px-4 pb-4 pt-1 bg-[#f4f4f0] border-t-2 border-black/10">
                {/* …здесь твой существующий блок рядов v5 без изменений… */}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}