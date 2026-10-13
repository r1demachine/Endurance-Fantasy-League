"use client";

import Link from "next/link";
import ActivityCard from "@/components/ActivityCard";
import { EmptyState, Label, SectionTitle } from "@/components/ui";

type WorkoutsListProps = { weekLoading: boolean; weekActivities: any[]; selectedWeekStart: string; };

export default function WorkoutsList({ weekLoading, weekActivities, selectedWeekStart }: WorkoutsListProps) {
  return (
    {/* Тренировки */}
        <div className="border-b-2 border-black">
          <div className="grid md:grid-cols-[200px_1fr]">
            <div className="hidden md:flex flex-col justify-between p-5 border-r-2 border-black bg-[#ff4b26] text-white">
              <div>
                <p className="font-display uppercase text-xl md:text-2xl tracking-tight leading-none">Workouts</p>
                <div className="h-0.5 bg-black mt-3 mb-4"></div>
                <Label className="block text-white/80">Hover / long press for details</Label>
              </div>
              <span className="font-display text-4xl mt-auto">↓</span>
            </div>
            <div className="p-4 md:p-6">
              <div className="md:hidden mb-4">
                <SectionTitle tone="orange">Workouts</SectionTitle>
              </div>
              <p className="text-[10px] font-bold tracking-widest uppercase text-[#666] mb-3">
                {selectedWeekStart ? `Неделя с ${selectedWeekStart}` : "Выбранная неделя"}
              </p>
              {weekLoading ? <p className="text-sm text-[#666]">Загружаем тренировки недели…</p> : weekActivities.length === 0 ? (
                <EmptyState className="text-sm text-[#666]">
                  За выбранную неделю тренировок нет. Синхронизируй данные в{" "}
                  <Link href="/profile" className="text-[#5866f2] font-bold underline">профиле</Link>.
                </EmptyState>
              ) : (
                <div className="space-y-0">
                  {weekActivities.map((act: any, idx: number) => (
                    <div key={act.id ?? idx} className={idx > 0 ? "border-t-2 border-black" : ""}>
                      <ActivityCard act={act} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
  );
}
