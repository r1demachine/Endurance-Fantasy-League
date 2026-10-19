"use client";

import { useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import ActivityXpDetails, { type ActivityXpContext } from "@/components/ActivityXpDetails";

type Act = ActivityXpContext & {
  date: string;
  distance_km: number;
  moving_time_min: number;
  xp: number;
  intensity_category: string;
};

const CAT_COLOR: Record<string, string> = {
  LOW: "text-[#16a34a]",
  MEDIUM: "text-[#5866f2]",
  HIGH: "text-[#ff4b26]",
  UNKNOWN: "text-[#999]",
};

export default function ActivityCard({ act }: { act: Act }) {
  const [open, setOpen] = useState(false);
  const reduceMotion = useReducedMotion();
  const catColor = CAT_COLOR[act.intensity_category] || "text-[#111]";

  return (
    <div className="border-b-2 border-black last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={`${act.name}, ${act.date}, ${act.sport}, ${act.distance_km} км, ${act.moving_time_min} мин, +${Math.round(act.xp)} XP. ${open ? "Скрыть" : "Открыть"} разбор XP`}
        className="grid w-full grid-cols-[1fr_auto] items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#5866f2] motion-reduce:transition-none"
      >
        <div className="min-w-0">
          <p className="truncate text-sm font-bold uppercase tracking-wide">{act.name}</p>
          <p className="mt-0.5 text-[10px] font-bold uppercase tracking-widest text-[#666]">
            {act.date} · {act.sport} · {act.distance_km} км · {act.moving_time_min} мин
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className={`font-display text-xl ${catColor}`}>+{Math.round(act.xp)} XP</span>
          <span aria-hidden="true" className="text-[#666]">{open ? "▲" : "▼"}</span>
        </div>
      </button>
      <motion.div
        key="activity-xp-details"
        initial={false}
        animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.2, ease: "easeInOut" }}
        className="overflow-hidden"
        aria-hidden={!open}
        inert={!open}
      >
        <ActivityXpDetails act={act} enabled={open} />
      </motion.div>
    </div>
  );
}
