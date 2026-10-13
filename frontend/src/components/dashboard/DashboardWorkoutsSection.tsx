"use client";

import WorkoutsList from "@/components/dashboard/WorkoutsList";
import { formatWeekRange } from "@/lib/format";

type WeekOption = { week_start: string; label: string };

type Props = {
  weekLoading: boolean;
  weekActivities: any[];
  weekOptions: WeekOption[];
  selectedWeekStart: string;
  onWeekChange: (weekStart: string) => void;
  onOpenSources: () => void;
};

export default function DashboardWorkoutsSection({
  weekLoading,
  weekActivities,
  weekOptions,
  selectedWeekStart,
  onWeekChange,
  onOpenSources,
}: Props) {
  const activeWeek = selectedWeekStart || weekOptions[0]?.week_start || "";
  const activeIndex = weekOptions.findIndex((week) => week.week_start === activeWeek);
  const canGoPrevious = activeIndex >= 0 && activeIndex < weekOptions.length - 1;
  const canGoNext = activeIndex > 0;

  const moveWeek = (direction: "previous" | "next") => {
    const target = weekOptions[activeIndex + (direction === "previous" ? 1 : -1)];
    if (target) onWeekChange(target.week_start);
  };

  return (
    <section className="border-b-2 border-black bg-white" aria-labelledby="dashboard-workouts-heading">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-black bg-[#f4f4f0] p-4 md:p-6">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#666]">Тренировки</p>
          <h2 id="dashboard-workouts-heading" className="font-display text-2xl uppercase">Список тренировок</h2>
          <p className="mt-1 text-xs text-[#666]">Список обновляется при выборе недели в графике или недельной сводке.</p>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            aria-label="Предыдущая неделя тренировок"
            disabled={!canGoPrevious}
            onClick={() => moveWeek("previous")}
            className="h-10 w-10 shrink-0 border-2 border-black bg-white font-bold transition-colors hover:bg-[#ffd500] disabled:opacity-30"
          >←</button>
          <select
            aria-label="Выбрать неделю для списка тренировок"
            value={activeWeek}
            onChange={(event) => onWeekChange(event.target.value)}
            className="min-w-0 max-w-[270px] border-2 border-black bg-white px-3 py-2 text-sm font-bold"
          >
            {weekOptions.length === 0 && <option value="">Нет недель</option>}
            {weekOptions.map((week) => (
              <option key={week.week_start} value={week.week_start}>{formatWeekRange(week.week_start)}</option>
            ))}
          </select>
          <button
            type="button"
            aria-label="Следующая неделя тренировок"
            disabled={!canGoNext}
            onClick={() => moveWeek("next")}
            className="h-10 w-10 shrink-0 border-2 border-black bg-white font-bold transition-colors hover:bg-[#ffd500] disabled:opacity-30"
          >→</button>
        </div>
      </header>
      <WorkoutsList
        weekLoading={weekLoading}
        weekActivities={weekActivities}
        selectedWeekStart={activeWeek}
        onOpenSources={onOpenSources}
      />
    </section>
  );
}
