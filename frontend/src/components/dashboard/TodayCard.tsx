"use client";

import { ArrowUpRight, Check, Circle, Zap } from "lucide-react";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui";
import {
  formatTodayDate,
  formatWeeklyProgress,
  todayChecklistModel,
  type TodayWeeklyAchievement,
} from "@/lib/today-card";

type TodayXpBonus = { title: string; amount: number; type?: string };
type TodayPayload = {
  date: string;
  seconds_left_today: number;
  streak: number;
  has_source?: boolean;
  ledger?: {
    activities?: unknown[];
    xp?: { effort?: number; bonuses?: TodayXpBonus[]; total?: number };
  };
  daily_bonus?: { title?: string; amount?: number; done?: boolean; description?: string };
  sleep?: { title?: string; has_data?: boolean; done?: boolean; waiting_for_data?: boolean; description?: string };
  weekly_achievements?: TodayWeeklyAchievement[];
  achievements_today?: { slug: string; title: string; reward: number; kind: string; status: string; earned_today: boolean }[];
};

type Props = {
  data: TodayPayload | null;
  loading: boolean;
  error: string;
  onRetry: () => void;
  onOpenSources: () => void;
  level?: number;
  totalXp?: number;
};

const number = (value: unknown) => Math.round(Number(value) || 0);

function StatusMark({ done, waiting = false }: { done: boolean; waiting?: boolean }) {
  if (waiting) {
    return <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center border-2 border-black/20 bg-[#f4f4f0] text-[10px] font-black text-[#666]" aria-label="Ждём данные">…</span>;
  }
  if (done) {
    return <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center border-2 border-black bg-[#b9f6ca] text-[#166534]" aria-label="Выполнено сегодня"><Check size={15} strokeWidth={3} /></span>;
  }
  return <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center border-2 border-black/30 bg-white text-[#777]" aria-label="Ещё не выполнено"><Circle size={11} /></span>;
}

function checklistTitle(quest: TodayWeeklyAchievement): string {
  switch (quest.slug) {
    case "long_workout_2h": return "Длинная тренировка · 2 ч";
    case "long_workout_3h": return "Тренировка · 3 ч";
    case "high_intensity": return "Высокая интенсивность";
    case "trainer_week": return "Тренировка на станке";
    case "qualifying_days_5": return "Дни с тренировками";
    case "good_sleep_5": return "Ночи хорошего сна";
    default: return quest.title;
  }
}

function ChecklistRow({
  title,
  description,
  done,
  waiting = false,
  trailing,
  accent = false,
}: {
  title: string;
  description?: string;
  done: boolean;
  waiting?: boolean;
  trailing?: string;
  accent?: boolean;
}) {
  return (
    <li className={`flex min-w-0 items-start gap-3 border-b border-black/10 px-3 py-3 last:border-b-0 ${done ? "bg-[#f1fbf3]" : ""}`}>
      <StatusMark done={done} waiting={waiting} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <p className="break-words text-sm font-bold">{title}</p>
          {trailing && <span className={`text-xs font-black ${accent ? "text-[#16803c]" : "text-[#5866f2]"}`}>{trailing}</span>}
        </div>
        {description && <p className="mt-1 text-xs leading-relaxed text-[#666]">{description}</p>}
      </div>
    </li>
  );
}

export default function TodayCard({ data, loading, error, onRetry, onOpenSources, level = 1, totalXp = 0 }: Props) {
  const ledger = data?.ledger;
  const xp = ledger?.xp;
  const bonuses = Array.isArray(xp?.bonuses) ? xp.bonuses : [];
  const dailyBonus = bonuses
    .filter((bonus) => bonus.type === "activity_bonus")
    .reduce((sum, bonus) => sum + Number(bonus.amount || 0), 0);
  const achievementBonuses = bonuses.filter((bonus) => bonus.type === "quest" || bonus.type === "achievement");
  const checklist = todayChecklistModel({
    weekly_achievements: data?.weekly_achievements,
    achievements_today: data?.achievements_today,
  });
  const alternativeSlugs = new Set(["long_workout_2h", "long_workout_3h", "high_intensity"]);
  const alternativeQuests = (data?.weekly_achievements ?? []).filter(
    (quest) => alternativeSlugs.has(quest.slug) &&
      (quest.actionable_today || quest.completed_today || quest.completed_before_today),
  );
  const alternativeDone = alternativeQuests.some((quest) => {
    const target = Number(quest.progress?.target) || 0;
    const current = Number(quest.progress?.current) || 0;
    return quest.status === "earned" || Boolean(quest.completed_today || quest.completed_before_today) ||
      (target > 0 && current >= target);
  });
  const visibleWeekly = checklist.visibleWeekly.filter(
    (quest) => quest.slug !== "goal_100" && !alternativeSlugs.has(quest.slug),
  );
  const completedEarlier = checklist.completedEarlier.filter(
    (quest) => quest.slug !== "goal_100" && !alternativeSlugs.has(quest.slug),
  );
  const dailyBonusDone = Boolean(data?.daily_bonus?.done || dailyBonus > 0);
  const sleep = data?.sleep;
  const hasActivities = (ledger?.activities?.length ?? 0) > 0;
  const showSourcePrompt = Boolean(data && !data.has_source && !hasActivities);

  return (
    <section data-tour="dashboard-streak" aria-labelledby="today-card-title" className="flex h-full min-w-0 flex-col bg-white">
      <header className="flex h-[58px] min-h-[58px] shrink-0 items-center border-b-2 border-black bg-[#ffd500] px-4 md:px-5">
        <h2 id="today-card-title" className="font-display text-2xl uppercase md:text-3xl">
          Сегодня{data?.date ? ` · ${formatTodayDate(data.date)}` : ""}
        </h2>
      </header>

      {loading && !data && <div className="p-4 md:p-6"><Skeleton label="Загружаем сводку за сегодня" rows={5} /></div>}
      {error && !data && <div className="p-4 md:p-6"><ErrorState message={error} onRetry={onRetry} /></div>}

      {data && (
        <div className="grid min-w-0 flex-1 grid-cols-1">
          <section aria-labelledby="today-xp-heading" className="min-w-0 border-b-2 border-black bg-[#f4f4f0] px-4 py-3 md:px-5 md:py-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[10px] font-black uppercase tracking-widest text-[#666]">Заработано сегодня</p>
                <h3 id="today-xp-heading" className="font-display text-3xl text-[#ff4b26]">+{number(xp?.total)} XP</h3>
                <p className="mt-1 text-xs font-bold uppercase tracking-wide text-[#555]">Уровень {Math.max(1, number(level))} · {number(totalXp)} XP всего</p>
              </div>
              <span className="flex h-10 w-10 items-center justify-center border-2 border-black bg-white" aria-hidden="true"><Zap size={19} /></span>
            </div>
            {achievementBonuses.length > 0 && (
              <div className="mt-3 border-t border-black/20 pt-3">
                <p className="text-[9px] font-black uppercase tracking-widest text-[#666]">Награды, начисленные сегодня</p>
                <ul className="mt-2 space-y-2">
                  {achievementBonuses.map((bonus, index) => (
                    <li key={`${bonus.title}-${index}`} className="flex items-start justify-between gap-2 text-xs">
                      <span className="min-w-0 break-words">{bonus.title}</span>
                      <strong className="shrink-0">+{number(bonus.amount)} XP</strong>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <section aria-labelledby="today-checklist-heading" className="min-w-0">
            <div className="border-b-2 border-black px-4 py-2 md:px-5">
              <h3 id="today-checklist-heading" className="font-display text-lg uppercase">Доступные задачи</h3>
            </div>

            {showSourcePrompt ? (
              <div className="p-4 md:p-5">
                <EmptyState>Подключи источник, чтобы получать данные о тренировках и восстановлении.</EmptyState>
                <button
                  type="button"
                  onClick={onOpenSources}
                  className="mt-3 inline-flex items-center gap-2 border-2 border-black bg-[#ff4b26] px-4 py-3 text-xs font-black uppercase tracking-widest text-white transition-colors hover:bg-[#5866f2] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2] motion-reduce:transition-none"
                >
                  Подключить источник <ArrowUpRight size={15} />
                </button>
              </div>
            ) : (
              <>
                <ul>
                  <ChecklistRow
                    title={data.daily_bonus?.title || "Дневной бонус +20 XP"}
                    description={data.daily_bonus?.description || "Тренировка от 45 минут, не ручная."}
                    done={dailyBonusDone}
                    trailing={dailyBonusDone ? "получено +20 XP" : "+20 XP"}
                    accent
                  />
                  <ChecklistRow
                    title={sleep?.title || "Хороший сон"}
                    description={sleep?.waiting_for_data ? "Ждём данные о сне за сегодня." : sleep?.description || "Не менее 6 часов сна или Sleep Score ≥60."}
                    done={Boolean(sleep?.done)}
                    waiting={Boolean(sleep?.waiting_for_data)}
                    trailing={sleep?.waiting_for_data ? "ждём данные" : sleep?.done ? "выполнено" : undefined}
                    accent={Boolean(sleep?.done)}
                  />
                  {alternativeQuests.length > 0 && (
                    <ChecklistRow
                      key="workout-alternatives"
                      title="Ключевая тренировка"
                      description="Длинная тренировка · 2 ч, тренировка · 3 ч или высокая интенсивность — достаточно выполнить любую одну."
                      done={alternativeDone}
                      trailing={alternativeDone ? "1/1" : "0/1"}
                      accent={alternativeDone}
                    />
                  )}
                  {visibleWeekly.map((quest) => {
                    const done = Boolean(quest.completed_today);
                    const progress = formatWeeklyProgress(quest);
                    return (
                      <ChecklistRow
                        key={quest.slug}
                        title={checklistTitle(quest)}
                        description={quest.slug === "trainer_week" && !quest.progress?.season_active ? "Доступно только в сезон станка: с октября по апрель." : undefined}
                        done={done}
                        trailing={progress || (done ? "получено" : undefined)}
                        accent={done}
                      />
                    );
                  })}
                  {checklist.lifetimeReceivedToday.map((achievement) => (
                    <ChecklistRow
                      key={achievement.slug}
                      title={achievement.title}
                      description="⭐ Получено сегодня"
                      done
                      trailing={`+${number(achievement.reward)} XP`}
                      accent
                    />
                  ))}
                </ul>

                {completedEarlier.length > 0 && (
                  <details className="border-t-2 border-black">
                    <summary className="cursor-pointer list-none bg-[#f4f4f0] px-4 py-3 text-sm font-bold hover:bg-[#fff3ad] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#5866f2]">
                      Уже получено на этой неделе ({completedEarlier.length})
                    </summary>
                    <ul className="border-t border-black/10">
                      {completedEarlier.map((quest) => (
                        <ChecklistRow
                          key={quest.slug}
                          title={checklistTitle(quest)}
                          description={quest.progress?.season_active === false ? "Зачтено по истории текущей недели." : undefined}
                          done
                          trailing={`+${number(quest.reward)} XP`}
                          accent
                        />
                      ))}
                    </ul>
                  </details>
                )}
              </>
            )}
            {error && data && <p role="status" className="border-t border-black/10 px-4 py-2 text-xs text-[#9a3412]">{error}</p>}
          </section>
        </div>
      )}
    </section>
  );
}
