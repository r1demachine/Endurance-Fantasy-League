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

const QUEST_EXPLANATIONS: Record<string, string> = {
  qualifying_days_5:
    "Нужно провести тренировки в пяти разных календарных днях выбранной недели. День засчитывается по суммарной квалифицирующей нагрузке (не менее 20 TSS по правилам системы), а несколько тренировок в один день не увеличивают счётчик. Прогресс начинается заново с новой недели.",
  good_sleep_5:
    "Засчитывается каждая ночь, для которой синхронизированы данные сна и выполнено хотя бы одно условие: длительность не менее 6 часов или sleep score не ниже 60. Одна ночь учитывается максимум один раз. Если источник не передаёт сон, ночь не засчитывается.",
  long_workout_2h:
    "Нужна хотя бы одна не ручная тренировка продолжительностью от двух часов в выбранной календарной неделе. Учитывается длительность самой тренировки, а не сумма нескольких коротких занятий. Награда доступна один раз за неделю.",
  long_workout_3h:
    "Дополнительная награда за одну не ручную тренировку длительностью не менее трёх часов в выбранной неделе. Такая тренировка также подходит под достижение «Длинная тренировка» от двух часов; это отдельная дополнительная награда.",
  high_intensity:
    "Нужна не ручная тренировка с реальной IF не ниже 0,75 либо с подтверждёнными пятью и более минутами в пульсовой зоне Z4 или выше. Оценочная IF или одна лишь длительность не заменяют эти условия. Награда начисляется максимум один раз за неделю.",
  trainer_week:
    "Нужна тренировка на станке продолжительностью от 30 минут. Достижение активно в сезон станка — с 1 октября по 30 апреля. Для зачёта в данных тренировки должен присутствовать признак indoor/trainer; ручная запись без такого признака не считается.",
  first_three_day_week:
    "Разовое достижение открывается, когда хотя бы в одной календарной неделе есть три разных дня с квалифицирующей нагрузкой. Несколько тренировок в один день считаются одним тренировочным днём. После выполнения награда не сбрасывается.",
  goal_met:
    "Разовая награда за полностью выполненную персональную недельную цель. Сравнивается фактическое выполнение с индивидуальной целью недели; неделя должна быть финализирована системой.",
  goal_streak_3:
    "Нужно выполнить персональную цель на трёх финализированных неделях подряд без пропуска недели. Прогресс основывается на сохранённых итогах недель, а не на количестве тренировок за один отдельный день.",
  first_50km_ride_week:
    "Нужно набрать не менее 50 км на велотренировках за одну календарную неделю. Суммируются дистанции всех подходящих велотренировок этой недели; расстояния разных недель не складываются.",
  record_duration:
    "Достижение проверяет историю длительности тренировок: после как минимум трёх предыдущих записей нужно превысить прежний максимум более чем на 10%. Ручные тренировки не участвуют в сравнении. После выполнения награда остаётся в истории.",
  sleep_connected:
    "Разовая награда за наличие данных о сне минимум за три разные ночи. Данные могут содержать продолжительность сна или sleep score и должны поступить через подключённый источник восстановления.",
  power_record_20m:
    "Пока недоступно: для честной оценки двадцатиминутного рекорда нужны реальные данные мощности в ваттах. Система не подменяет их расчётной интенсивностью или пульсом.",
  ftp_growth_8w:
    "Пока недоступно: для сравнения FTP за восемь недель нужны подтверждённые значения FTP и массы тела для расчёта Вт/кг. Пока эти данные не поступают, достижение не имитируется по TSS или длительности.",
};

function questExplanation(quest: Quest): string {
  const detail = QUEST_EXPLANATIONS[quest.slug] || quest.desc;
  if (quest.status === "unavailable" && quest.progress_reason) {
    return `${detail} ${quest.progress_reason}`;
  }
  return detail;
}

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
            tabIndex={0}
            role="group"
            aria-label={quest.title}
            className={`group relative border-2 p-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2] ${
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
            <span className="sr-only">{quest.desc} {questExplanation(quest)}</span>

            {unavailable ? (
              <p className="sr-only">{quest.progress_reason || "Необходимые данные пока недоступны."}</p>
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
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 z-40 flex items-start overflow-y-auto bg-white/95 p-3 text-[#171a38] opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus:opacity-100"
            >
              <p className="text-sm leading-relaxed">{questExplanation(quest)}</p>
            </div>
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
