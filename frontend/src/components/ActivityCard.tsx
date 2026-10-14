"use client";

import { useCallback, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { authApi } from "@/lib/auth";
import { getApiErrorMessage } from "@/components/dialog-utils";
import XpTooltip from "@/components/XpTooltip";
import { ErrorState, Skeleton } from "@/components/ui";

interface Act {
  id: number; name: string; sport: string; date: string; distance_km: number;
  moving_time_min: number; xp: number; effort_xp?: number; activity_awards_xp?: number; base_xp: number | null;
  rate_per_hour: number; intensity_multiplier: number; intensity_category: string;
  intensity_reason: string; sleep_multiplier: number; sleep_hours: number | null;
  streak_multiplier: number; streak_reason: string; tss_estimated?: boolean; is_long?: boolean;
}
type AwardItem = { id: number; title: string; amount: number };
type Breakdown = {
  effort?: { tss?: number; day_tss?: number; effective_day_tss?: number; daily_tss_cap?: number; cap_applied?: boolean; day_total_effort_xp?: number; calculated_activity_xp?: number; xp?: number; manual_coefficient?: number };
  related?: {
    activity?: { events?: AwardItem[]; total_xp?: number };
  };
  totals?: { for_this_activity_xp?: number };
};
const CAT_COLOR: Record<string, string> = {
  LOW: "text-[#16a34a]", MEDIUM: "text-[#5866f2]", HIGH: "text-[#ff4b26]", UNKNOWN: "text-[#999]",
};
function Row({ label, value, sub, tip, accent }: { label: string; value: string; sub?: string; tip?: string; accent?: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-black/10 py-2 last:border-b-0">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <p className="text-[9px] font-bold uppercase tracking-widest text-[#666]">{label}</p>
          {tip && <XpTooltip label={label} content={tip} />}
        </div>
        {sub && <p className="mt-0.5 text-[10px] leading-snug text-[#666]">{sub}</p>}
      </div>
      <p className={`shrink-0 font-display text-lg ${accent || ""}`}>{value}</p>
    </div>
  );
}
const num = (value: unknown) => Math.round(Number(value) || 0);
const xp = (value: unknown) => `+${num(value)} XP`;

export default function ActivityCard({ act }: { act: Act }) {
  const [open, setOpen] = useState(false);
  const [breakdown, setBreakdown] = useState<Breakdown | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const catColor = CAT_COLOR[act.intensity_category] || "text-[#111]";

  const loadBreakdown = useCallback(async () => {
    if (breakdown || loading) return;
    setLoading(true);
    setError("");
    try {
      const response = await authApi.get(`/api/activities/${act.id}/xp`);
      setBreakdown(response.data as Breakdown);
    } catch (requestError: unknown) {
      setError(getApiErrorMessage(requestError, "Не удалось загрузить разбор XP."));
    } finally {
      setLoading(false);
    }
  }, [act.id, breakdown, loading]);

  const toggleOpen = () => {
    const next = !open;
    setOpen(next);
    if (next && !breakdown && !loading) void loadBreakdown();
  };
  const effort = breakdown?.effort;
  const activityAwards = breakdown?.related?.activity;
  const activityEvents = activityAwards?.events ?? [];

  return (
    <div className="border-b-2 border-black last:border-b-0">
      <button type="button" onClick={toggleOpen} aria-expanded={open} className="grid w-full grid-cols-[1fr_auto] items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-black/5">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold uppercase tracking-wide">{act.name}</p>
          <p className="mt-0.5 text-[10px] font-bold uppercase tracking-widest text-[#666]">{act.date} · {act.sport} · {act.distance_km} км · {act.moving_time_min} мин</p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className={`font-display text-xl ${catColor}`}>+{Math.round(act.xp)} XP</span>
          <span aria-hidden="true" className="text-[#666]">{open ? "▲" : "▼"}</span>
        </div>
      </button>
      <AnimatePresence initial={false}>
        {open && <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2, ease: "easeInOut" }} className="overflow-hidden">
          <div className="space-y-2 border-t-2 border-black/10 bg-[#f4f4f0] px-4 pb-4 pt-3">
            {loading && !breakdown && <Skeleton label="Загружаем разбор XP" rows={4} />}
            {error && <ErrorState message={error} onRetry={() => void loadBreakdown()} />}
            {breakdown && <>
              <Row label="За нагрузку этой тренировки" value={xp(effort?.xp ?? act.effort_xp ?? 0)} tip="XP за нагрузку, отнесённые к этой тренировке. Если за день было несколько тренировок, дневная сумма распределяется между ними пропорционально нагрузке." sub={`TSS этой тренировки: ${Number(effort?.tss ?? 0).toFixed(1)} · расчётная доля: ${num(effort?.calculated_activity_xp)} XP`} accent="text-[#ff4b26]" />
              <div className="border-b border-black/10 py-2">
                <div className="flex items-center gap-1.5">
                  <p className="text-[9px] font-bold uppercase tracking-widest text-[#666]">Достижения за эту тренировку</p>
                  <XpTooltip label="Достижения за эту тренировку" content="Здесь собраны только награды, привязанные к этой тренировке, включая бонус за длительность от 45 минут. Общие награды дня и недели в итог тренировки не входят." />
                </div>
                <p className="mt-1 font-display text-lg text-[#16a34a]">{xp(activityAwards?.total_xp)}</p>
                {activityEvents.length > 0
                  ? <ul className="mt-1 space-y-1 text-xs text-[#555]">{activityEvents.map((event) => <li key={event.id} className="flex justify-between gap-3"><span>{event.title}</span><span className="shrink-0 font-bold">{xp(event.amount)}</span></li>)}</ul>
                  : <p className="mt-1 text-xs text-[#666]">К этой тренировке не привязаны отдельные достижения.</p>}
              </div>
              <Row label="Итого" value={xp(breakdown.totals?.for_this_activity_xp ?? act.xp)} tip="Сумма XP за нагрузку этой тренировки и наград, привязанных к ней." accent="text-[#ff4b26]" />
              <div className="border-2 border-black/10 bg-white p-3 text-[11px] leading-relaxed text-[#555]">
                <p><strong>Потолок 300 TSS в день.</strong> Фактическая дневная нагрузка: {Number(effort?.day_tss ?? 0).toFixed(1)} TSS; в расчёте учитывается не более {num(effort?.daily_tss_cap ?? 300)} TSS{effort?.cap_applied ? " — потолок достигнут" : ""}.</p>
                <p className="mt-1">Нагрузка дня даёт {num(effort?.day_total_effort_xp)} XP, распределяемых между тренировками пропорционально их TSS. Поэтому XP за одну тренировку может отличаться от расчёта только по её нагрузке.</p>
                <p className="mt-1">В итог входят только нагрузка и бонусы, привязанные к этой тренировке.</p>
              </div>
            </>}
          </div>
        </motion.div>}
      </AnimatePresence>
    </div>
  );
}
