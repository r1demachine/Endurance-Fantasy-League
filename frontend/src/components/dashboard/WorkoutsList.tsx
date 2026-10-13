"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import ActivityCard from "@/components/ActivityCard";
import { formatWeekRange } from "@/lib/format";
import { EmptyState } from "@/components/ui";

type WorkoutsListProps = {
  weekLoading: boolean;
  weekActivities: any[];
  selectedWeekStart: string;
};

export default function WorkoutsList({ weekLoading, weekActivities, selectedWeekStart }: WorkoutsListProps) {
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    setShowAll(false);
  }, [selectedWeekStart, weekActivities]);

  const visibleActivities = showAll ? weekActivities : weekActivities.slice(0, 5);

  return (
    <section className="bg-white">
      {weekLoading ? (
        <p className="p-4 text-sm text-[#666]">Загружаем тренировки недели…</p>
      ) : weekActivities.length === 0 ? (
        <div className="p-4 md:p-6">
          <EmptyState>За выбранную неделю тренировок нет. Синхронизируй данные во вкладке Источники.</EmptyState>
          <Link href="/profile?settings=sources" className="mt-3 inline-block text-sm font-bold text-[#5866f2] underline">Открыть источники данных →</Link>
        </div>
      ) : (
        <>
          <div className="space-y-0">
            {visibleActivities.map((activity: any, index: number) => (
              <div key={activity.id ?? index} className={index > 0 ? "border-t-2 border-black" : ""}>
                <ActivityCard act={activity} />
              </div>
            ))}
          </div>
          {weekActivities.length > 5 && (
            <div className="border-t-2 border-black px-4 py-3">
              <button type="button" onClick={() => setShowAll((value) => !value)} className="text-[10px] font-bold uppercase tracking-widest text-[#5866f2] underline">
                {showAll ? "Показать меньше" : `Показать всё (${weekActivities.length})`}
              </button>
            </div>
          )}
        </>
      )}
      <p className="border-t border-black/10 px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-[#666]">
        {selectedWeekStart ? formatWeekRange(selectedWeekStart) : "Выбранная неделя"}
      </p>
    </section>
  );
}
