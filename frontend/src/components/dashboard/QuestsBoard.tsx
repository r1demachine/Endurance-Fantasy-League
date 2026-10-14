"use client";

import { useState } from "react";
import Card from "@/components/ui/Card";
import { EmptyState, ErrorState, HelpTip, Skeleton } from "@/components/ui";
import { formatWeekRange } from "@/lib/format";

type QuestStep = { slot: number; label: string; filled: boolean; date?: string | null };
type QuestProgress = {
  current: number;
  target: number;
  unit: string;
  steps?: QuestStep[];
  season_active?: boolean;
  season_window?: { starts_month: number; ends_month: number };
};
type Quest = {
  slug: string;
  title: string;
  desc: string;
  reward: number;
  kind: "weekly" | "lifetime";
  week_start?: string;
  status: "earned" | "open" | "unavailable";
  earned_at?: string | null;
  progress?: QuestProgress | null;
  progress_reason?: string | null;
};

type Props = {
  quests: Quest[];
  loading: boolean;
  error: string;
  dailyBonusDays: number;
  onRetry: () => void;
};

export default function QuestsBoard({ quests, loading, error, dailyBonusDays, onRetry }: Props) {
  const [showAll, setShowAll] = useState(true);
  const dailyBonusCount = Math.min(7, Math.max(0, Number(dailyBonusDays) || 0));
  const weeklyQuests = quests.filter((quest) => quest.kind === "weekly");
  const lifetimeQuests = quests.filter((quest) => quest.kind !== "weekly");
  const visibleLifetimeQuests = showAll ? lifetimeQuests : lifetimeQuests.slice(0, 4);
  const weekStart = weeklyQuests.find((quest) => quest.week_start)?.week_start;

  const renderCards = (items: Quest[]) => (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((quest) => {
        const progress = quest.progress ?? null;
        const target = Math.max(1, Number(progress?.target) || 1);
        const current = Math.max(0, Number(progress?.current) || 0);
        const percentage = Math.min(100, (current / target) * 100);
        const unavailable = quest.status === "unavailable" || progress === null;

        return (
          <Card
            key={quest.slug}
            className={`border-2 p-3 ${
              quest.status === "earned"
                ? "border-[#16a34a] bg-[#16a34a]/10"
                : unavailable
                ? "border-black/10 bg-black/5"
                : "border-black/20"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="min-w-0 break-words font-bold text-sm uppercase">
                <span aria-hidden="true">{quest.status === "earned" ? "⭐" : unavailable ? "🔒" : "🏆"}</span>{" "}
                {quest.title}
              </p>
              <span className="shrink-0 font-display text-[#16a34a]">+{quest.reward}</span>
            </div>
            <p className="mt-1 text-[9px] font-bold uppercase tracking-widest text-[#666]">{quest.desc}</p>

            {unavailable ? (
              <p className="mt-3 flex items-start gap-2 text-xs text-[#666]">
                <span aria-hidden="true">🔒</span>
                <span>{quest.progress_reason || "Необходимые данные пока недоступны."}</span>
              </p>
            ) : progress?.steps && progress.steps.length > 0 ? (
              <div className="mt-3">
                <div className="flex gap-2" role="img" aria-label={`${quest.title}: ${current} из ${target} ${progress.unit}`}>
                  {progress.steps.map((step) => (
                    <span
                      key={step.slot}
                      title={step.date ? `${step.label}: ${step.date}` : step.label}
                      className={`h-5 flex-1 border-2 border-black ${step.filled ? "bg-[#16a34a]" : "bg-white"}`}
                    />
                  ))}
                </div>
                <p className="mt-1 text-[10px] font-bold text-[#666]">{current} / {target} {progress.unit}</p>
              </div>
            ) : progress ? (
              <div className="mt-3">
                <div
                  className="h-2 overflow-hidden border border-black/20 bg-black/10"
                  role="progressbar"
                  aria-label={`Прогресс: ${quest.title}`}
                  aria-valuemin={0}
                  aria-valuemax={target}
                  aria-valuenow={Math.min(current, target)}
                >
                  <div className="h-full bg-[#5866f2] transition-all" style={{ width: `${percentage}%` }} />
                </div>
                <p className="mt-1 text-[10px] font-bold text-[#666]">{current} / {target} {progress.unit}</p>
              </div>
            ) : null}

            {quest.status === "earned" && quest.earned_at && (
              <p className="mt-2 text-[10px] font-bold text-[#16a34a]">Получено {quest.earned_at}</p>
            )}
          </Card>
        );
      })}
    </div>
  );

  return (
    <section className="border-b-2 border-black bg-white p-4 md:p-6" aria-labelledby="achievements-heading">
      <h3 id="achievements-heading" className="mb-4 font-display text-xl uppercase md:text-2xl">Достижения</h3>
      <div className="mb-4 border-2 border-black/10 p-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Дневные бонусы за выбранную неделю</p>
            <HelpTip label="Как работают дневные бонусы">
              Один бонус +20 XP в день получает одна не ручная тренировка длительностью от 45 минут. Если тренировок несколько, выбирается тренировка с максимальным TSS; при равенстве — более ранняя.
            </HelpTip>
          </div>
          <p className="shrink-0 font-display text-lg">{dailyBonusCount} / 7</p>
        </div>
        <div
          className="mt-2 h-2 overflow-hidden border border-black/20 bg-black/10"
          role="progressbar"
          aria-label="Дневные бонусы"
          aria-valuemin={0}
          aria-valuemax={7}
          aria-valuenow={dailyBonusCount}
        >
          <div className="h-full bg-[#16a34a] transition-all" style={{ width: `${(dailyBonusCount / 7) * 100}%` }} />
        </div>
        <p className="mt-1 text-[10px] text-[#666]">Один бонус +20 XP в день для одной не ручной тренировки от 45 минут.</p>
      </div>
      {loading && quests.length === 0 ? (
        <Skeleton label="Загружаем достижения" rows={3} />
      ) : error && quests.length === 0 ? (
        <ErrorState message={error} onRetry={onRetry} />
      ) : quests.length === 0 ? (
        <EmptyState>Достижения пока не доступны. Попробуй обновить список.</EmptyState>
      ) : (
        <>
          {loading && <p role="status" className="mb-3 text-xs font-bold uppercase tracking-widest text-[#666]">Обновляем достижения…</p>}
          {error && <div className="mb-3"><ErrorState message={error} onRetry={onRetry} /></div>}

          {weeklyQuests.length > 0 && (
            <section aria-labelledby="weekly-achievements-heading" className="mb-5">
              <div className="mb-3 border-b-2 border-black pb-2">
                <div className="flex items-center gap-2">
                  <h4 id="weekly-achievements-heading" className="font-display text-lg uppercase md:text-xl">Недельные достижения</h4>
                  <HelpTip label="О прогрессе недельных достижений">
                    Прогресс считается по выбранной неделе и сбрасывается каждый понедельник. Начисленные награды за прошлые недели остаются в истории XP.
                  </HelpTip>
                </div>
                {weekStart && <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-[#666]">{formatWeekRange(weekStart)}</p>}
              </div>
              {renderCards(weeklyQuests)}
            </section>
          )}

          {lifetimeQuests.length > 0 && (
            <section aria-labelledby="lifetime-achievements-heading">
              <div className="mb-3 border-b-2 border-black pb-2">
                <div className="flex items-center gap-2">
                  <h4 id="lifetime-achievements-heading" className="font-display text-lg uppercase md:text-xl">Разовые достижения</h4>
                  <HelpTip label="О разовых достижениях">
                    Разовые достижения рассчитываются по всей доступной истории тренировок и восстановления.
                  </HelpTip>
                </div>
              </div>
              {renderCards(visibleLifetimeQuests)}
              {lifetimeQuests.length > 4 && (
                <div className="mt-4 border-t-2 border-black/10 pt-3">
                  <button type="button" onClick={() => setShowAll((value) => !value)} className="text-[10px] font-bold uppercase tracking-widest text-[#5866f2] underline">
                    {showAll ? "Свернуть" : `Показать все (${lifetimeQuests.length})`}
                  </button>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </section>
  );
}
