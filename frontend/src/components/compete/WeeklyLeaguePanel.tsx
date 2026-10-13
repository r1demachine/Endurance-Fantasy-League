"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { authApi } from "@/lib/auth";
import { getApiErrorMessage } from "@/components/dialog-utils";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui";

type Entry = {
  id?: number;
  username?: string | null;
  display_name?: string | null;
  rank?: number | null;
  level?: number | null;
  score?: number | null;
  is_you?: boolean;
  division?: string | null;
  division_source?: string | null;
};
type Payload = {
  entries?: Entry[];
  your_rank?: number | null;
  formed?: boolean;
  min_size?: number;
  week?: string;
};

export default function WeeklyLeaguePanel() {
  const [board, setBoard] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadWeekly = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await authApi.get("/api/leaderboard", { params: { scope: "weekly", limit: 10 } });
      const payload = response.data as Payload;
      setBoard({
        ...payload,
        entries: Array.isArray(payload.entries) ? payload.entries.slice(0, 10) : [],
      });
    } catch (requestError: unknown) {
      setError(getApiErrorMessage(requestError, "Не удалось загрузить Weekly League."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadWeekly();
  }, [loadWeekly]);

  const entries = board?.entries ?? [];
  const yourRank = typeof board?.your_rank === "number" ? board.your_rank : null;

  return (
    <section className="border-2 border-black bg-white" aria-labelledby="weekly-league-heading">
      <header className="border-b-2 border-black bg-[#171a38] px-4 py-4 text-white md:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-white/60">Weekly leaderboard</p>
            <h2 id="weekly-league-heading" className="font-display text-2xl uppercase">Weekly League</h2>
          </div>
          {board?.week && <span className="text-xs font-bold text-white/75">{board.week}</span>}
        </div>
        <p className="mt-2 max-w-3xl text-xs leading-relaxed text-white/80">
          Недельный League Score с группировкой по дивизионам. Пока участников меньше минимального состава, лига формируется.
        </p>
      </header>
      <div className="p-4 md:p-6">
        {loading ? (
          <Skeleton label="Загружаем Weekly League" rows={4} />
        ) : error ? (
          <ErrorState message={error} onRetry={() => void loadWeekly()} />
        ) : entries.length === 0 ? (
          <EmptyState>Лига формируется: недельных результатов пока недостаточно для таблицы.</EmptyState>
        ) : (
          <>
            {!board?.formed && (
              <p className="mb-3 border-2 border-black bg-[#ffd500]/25 px-3 py-2 text-[10px] font-bold uppercase tracking-widest">
                Лига формируется: {entries.length}/{board?.min_size ?? 5} атлетов
              </p>
            )}
            <div className="space-y-0">
              {entries.map((entry, index) => (
                <div key={entry.id ?? entry.username ?? index}>
                  {(index === 0 || entries[index - 1]?.division !== entry.division) && (
                    <div className="flex flex-wrap justify-between gap-2 bg-[#171a38] px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-white">
                      <span>{entry.division ?? "Open · provisional"}</span>
                      {entry.division_source && <span className="text-white/60">{entry.division_source}</span>}
                    </div>
                  )}
                  <div className={`flex items-center justify-between gap-3 border-b border-black/10 px-3 py-3 ${entry.is_you ? "bg-[#ffd500]/20" : "hover:bg-black/5"}`}>
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="w-8 shrink-0 font-display text-lg text-[#999]">{String(entry.rank ?? index + 1).padStart(2, "0")}</span>
                      <div className="min-w-0">
                        {entry.username ? (
                          <Link href={`/u/${encodeURIComponent(entry.username)}`} className="block truncate text-sm font-bold uppercase hover:text-[#5866f2]">
                            {entry.display_name || entry.username}{entry.is_you ? " (ТЫ)" : ""}
                          </Link>
                        ) : (
                          <p className="truncate text-sm font-bold uppercase">{entry.display_name || "Атлет"}{entry.is_you ? " (ТЫ)" : ""}</p>
                        )}
                      </div>
                    </div>
                    <span className="shrink-0 font-display text-lg text-[#ff4b26]">{Math.round(Number(entry.score) || 0).toLocaleString()}</span>
                  </div>
                </div>
              ))}
            </div>
            {yourRank !== null && yourRank > 10 && (
              <div className="mt-3 flex items-center justify-between border-2 border-black bg-[#ffd500]/25 px-4 py-3">
                <span className="text-sm font-bold uppercase">Ты — место {yourRank}</span>
                <span className="font-display text-xl">{yourRank}</span>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
