"use client";

import { useState } from "react";
import Card from "@/components/ui/Card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui";
type QuestProgress = {
  current: number;
  target: number;
  unit: string;
  steps?: { slot: number; label: string; filled: boolean; date?: string | null }[];
};

type Quest = {
  slug: string;
  title: string;
  desc: string;
  reward: number;
  status: "earned" | "open" | "unavailable";
  earned_at?: string | null;
  progress?: QuestProgress | null;
  progress_reason?: string | null;
};

type Props = {
  quests: Quest[];
  loading: boolean;
  error: string;
  onRetry: () => void;
};

export default function QuestsBoard({ quests, loading, error, onRetry }: Props) {
  const [showAll, setShowAll] = useState(false);
  const visibleQuests = showAll ? quests : quests.slice(0, 4);

  return (
    <section className="border-b-2 border-black bg-white p-4 md:p-6" aria-labelledby="achievements-heading">
      <h3 id="achievements-heading" className="mb-4 font-display text-xl uppercase md:text-2xl">Достижения</h3>
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
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {visibleQuests.map((quest) => {
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
                  ) : progress && quest.slug === "sleep_connected" ? (
                    <div className="mt-3">
                      <div className="flex gap-2" role="img" aria-label={`Сон: ${current} из ${target} ${progress.unit}`}>
                        {[0, 1, 2].map((slot) => {
                          const step = progress.steps?.[slot];
                          const filled = step ? step.filled : slot < current;
                          return (
                            <span
                              key={slot}
                              title={step?.date ? `${step.label}: ${step.date}` : step?.label || `Ночь ${slot + 1}`}
                              className={`h-5 flex-1 border-2 border-black ${filled ? "bg-[#16a34a]" : "bg-white"}`}
                            />
                          );
                        })}
                      </div>
                      <p className="mt-1 text-[10px] font-bold text-[#666]">{current} / {progress.target} {progress.unit}</p>
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
                      <p className="mt-1 text-[10px] font-bold text-[#666]">{current} / {progress.target} {progress.unit}</p>
                    </div>
                  ) : null}

                  {quest.status === "earned" && quest.earned_at && (
                    <p className="mt-2 text-[10px] font-bold text-[#16a34a]">Получено {quest.earned_at}</p>
                  )}
                </Card>
              );
            })}
          </div>
          {quests.length > 4 && (
            <div className="mt-4 border-t-2 border-black/10 pt-3">
              <button type="button" onClick={() => setShowAll((value) => !value)} className="text-[10px] font-bold uppercase tracking-widest text-[#5866f2] underline">
                {showAll ? "Свернуть" : `Показать все (${quests.length})`}
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
