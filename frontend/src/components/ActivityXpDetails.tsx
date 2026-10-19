"use client";

import { useCallback, useEffect, type ReactNode } from "react";
import { authApi } from "@/lib/auth";
import { getApiErrorMessage } from "@/components/dialog-utils";
import XpTooltip from "@/components/XpTooltip";
import { ErrorState, Skeleton } from "@/components/ui";
import { useState } from "react";

export type ActivityXpContext = {
  id: number;
  name?: string;
  sport?: string;
  date?: string;
  distance_km?: number;
  moving_time_min?: number;
  xp?: number;
  effort_xp?: number;
  base_xp?: number | null;
  rate_per_hour?: number;
  intensity_multiplier?: number;
  intensity_category?: string;
  intensity_reason?: string;
  sleep_multiplier?: number;
  sleep_hours?: number | null;
  streak_multiplier?: number;
  streak_reason?: string;
  tss?: number | null;
  tss_estimated?: boolean;
  is_manual?: boolean;
  is_indoor?: boolean;
};

type AwardItem = { id: number; title: string; amount: number };
type Breakdown = {
  effort?: {
    tss?: number;
    day_tss?: number;
    effective_day_tss?: number;
    daily_tss_cap?: number;
    cap_applied?: boolean;
    day_total_effort_xp?: number;
    calculated_activity_xp?: number;
    xp?: number;
    manual_coefficient?: number;
  };
  related?: { activity?: { events?: AwardItem[]; total_xp?: number } };
  totals?: { for_this_activity_xp?: number };
};

function Row({
  label,
  value,
  sub,
  tip,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  tip?: ReactNode;
  accent?: string;
}) {
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

function awardExplanation(title: string): string {
  const normalized = title.toLowerCase();
  if (normalized.includes("дневной бонус")) {
    return "Один дневной бонус начисляется за календарный день одной не ручной тренировке длительностью от 45 минут. Если таких тренировок несколько, бонус получает тренировка с наибольшим TSS; при равенстве выбирается более ранняя. За день этот бонус начисляется только один раз.";
  }
  if (normalized.includes("тренировка 3 часа+") || normalized.includes("3 часа+")) {
    return "Дополнительная награда за не ручную тренировку продолжительностью не менее трёх часов. Она привязана к конкретной тренировке и может выдаваться вместе с наградой за тренировку от двух часов.";
  }
  if (normalized.includes("длинная тренировка") || normalized.includes("2 часа")) {
    return "Недельное достижение за одну не ручную тренировку продолжительностью не менее двух часов. Прогресс учитывает тренировки выбранной календарной недели и обновляется после синхронизации данных.";
  }
  if (normalized.includes("высокая интенсивность")) {
    return "Недельное достижение за не ручную тренировку с реальной интенсивностью IF не ниже 0,75 либо с накоплением не менее пяти минут в зоне пульса Z4 или выше. Оценочная нагрузка сама по себе не заменяет эти условия.";
  }
  if (normalized.includes("станок")) {
    return "Недельная награда за тренировку на велостанке длительностью не менее 30 минут. Достижение учитывается в сезон станка — с 1 октября по 30 апреля; для зачёта в данных тренировки должен определяться indoor/trainer-режим.";
  }
  if (normalized.includes("45 минут")) {
    return "Этот прежний бонус за длительность тренировки больше не начисляется. Награда за нагрузку, дневной бонус и отдельные достижения продолжат рассчитываться по своим правилам.";
  }
  return "Отдельная награда, привязанная к этой тренировке. Она учитывается в разделе достижений за тренировку отдельно от XP за нагрузку.";
}

export default function ActivityXpDetails({ act, enabled = true }: { act: ActivityXpContext; enabled?: boolean }) {
  const [breakdown, setBreakdown] = useState<Breakdown | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadBreakdown = useCallback(async () => {
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
  }, [act.id]);

  useEffect(() => {
    if (!enabled || breakdown || loading || error) return;
    const request = window.setTimeout(() => {
      void loadBreakdown();
    }, 0);
    return () => window.clearTimeout(request);
  }, [enabled, breakdown, loading, error, loadBreakdown]);

  const effort = breakdown?.effort;
  const activityAwards = breakdown?.related?.activity;
  const activityEvents = (activityAwards?.events ?? []).filter(
    (event) => !event.title.toLowerCase().includes("тренировка ≥45 минут"),
  );
  const activityAwardsTotal = activityEvents.reduce(
    (total, event) => total + (Number(event.amount) || 0),
    0,
  );

  return (
    <div className="space-y-2 border-t-2 border-black/10 bg-[#f4f4f0] px-4 pb-4 pt-3">
      {loading && !breakdown && <Skeleton label="Загружаем разбор XP" rows={4} />}
      {error && <ErrorState message={error} onRetry={() => void loadBreakdown()} />}
      {breakdown && (
        <>
          <Row
            label="За нагрузку этой тренировки"
            value={xp(effort?.xp ?? act.effort_xp ?? 0)}
            tip="XP за нагрузку, отнесённые к этой тренировке. Если за день было несколько тренировок, дневная сумма распределяется между ними пропорционально нагрузке."
            sub={`TSS этой тренировки: ${Number(effort?.tss ?? act.tss ?? 0).toFixed(1)} · расчётная доля: ${num(effort?.calculated_activity_xp)} XP`}
            accent="text-[#ff4b26]"
          />
          <div className="border-b border-black/10 py-2">
            <p className="text-[9px] font-bold uppercase tracking-widest text-[#666]">Достижения за эту тренировку</p>
            <p className="mt-1 font-display text-lg text-[#16a34a]">{xp(activityAwardsTotal)}</p>
            {activityEvents.length > 0 ? (
              <ul className="mt-1 space-y-1 text-sm text-[#555]">
                {activityEvents.map((event) => (
                  <li key={event.id} className="flex justify-between gap-3">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span>{event.title}</span>
                      <XpTooltip label={event.title} content={awardExplanation(event.title)} />
                    </span>
                    <span className="shrink-0 font-bold">{xp(event.amount)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-sm text-[#666]">К этой тренировке не привязаны отдельные достижения.</p>
            )}
          </div>
          <Row
            label="Итого"
            value={xp(Number(effort?.xp ?? act.effort_xp ?? 0) + activityAwardsTotal)}
            tip={
              <div className="space-y-2">
                <p>
                  <strong>Потолок — 300 TSS в день.</strong> Фактическая дневная нагрузка:{" "}
                  {Number(effort?.day_tss ?? 0).toFixed(1)} TSS. В расчёте учитывается не более{" "}
                  {num(effort?.daily_tss_cap ?? 300)} TSS{effort?.cap_applied ? " — потолок достигнут" : ""}.
                </p>
                <p>
                  Нагрузка всего дня даёт {num(effort?.day_total_effort_xp)} XP. Эта сумма распределяется
                  между тренировками пропорционально их TSS, поэтому доля конкретной тренировки может
                  отличаться от расчёта только по её нагрузке.
                </p>
                <p>
                  В итог этой карточки входят XP за нагрузку данной тренировки и награды, привязанные
                  именно к ней. Общие награды дня и недели, которые принадлежат другой тренировке или не
                  привязаны к этой записи, в эту сумму не включаются.
                </p>
              </div>
            }
            accent="text-[#ff4b26]"
          />
        </>
      )}
    </div>
  );
}
