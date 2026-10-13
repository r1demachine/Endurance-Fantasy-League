"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { authApi, isAuthenticated } from "@/lib/auth";
import { getApiErrorMessage } from "@/components/dialog-utils";
import { EmptyState, ErrorState, Label, Skeleton, Tabs } from "@/components/ui";

type Scope = "global" | "friends" | "weekly";
type LeaderboardEntry = {
  id?: number;
  username?: string | null;
  display_name?: string | null;
  rank?: number | null;
  level?: number | null;
  total_xp?: number | null;
  score?: number | null;
  is_you?: boolean;
  division?: string | null;
  division_source?: string | null;
};
type LeaderboardPayload = {
  entries?: LeaderboardEntry[];
  your_rank?: number | null;
  formed?: boolean;
  min_size?: number;
};

const scopeTabs: { value: Scope; label: string }[] = [
  { value: "global", label: "Global" },
  { value: "friends", label: "Друзья" },
  { value: "weekly", label: "Weekly" },
];

export default function RatingPanel() {
  const [scope, setScope] = useState<Scope>("global");
  const [boards, setBoards] = useState<Partial<Record<Scope, LeaderboardPayload>>>({});
  const [attempted, setAttempted] = useState<Record<Scope, boolean>>({
    global: false, friends: false, weekly: false,
  });
  const [loading, setLoading] = useState<Record<Scope, boolean>>({
    global: true, friends: false, weekly: false,
  });
  const [errors, setErrors] = useState<Partial<Record<Scope, string>>>({});

  const loadScope = useCallback(async (requestedScope: Scope) => {
    setAttempted((previous) => ({ ...previous, [requestedScope]: true }));
    setErrors((previous) => ({ ...previous, [requestedScope]: "" }));
    setLoading((previous) => ({ ...previous, [requestedScope]: true }));

    if (requestedScope === "friends" && !isAuthenticated()) {
      setBoards((previous) => ({ ...previous, friends: { entries: [] } }));
      setLoading((previous) => ({ ...previous, friends: false }));
      return;
    }

    try {
      const params = requestedScope === "weekly"
        ? { scope: requestedScope }
        : { scope: requestedScope, limit: 10 };
      const response = await authApi.get("/api/leaderboard", { params });
      const payload = response.data as LeaderboardPayload;
      setBoards((previous) => ({
        ...previous,
        [requestedScope]: {
          ...payload,
          entries: Array.isArray(payload.entries) ? payload.entries.slice(0, 10) : [],
        },
      }));
    } catch (error: unknown) {
      setErrors((previous) => ({
        ...previous,
        [requestedScope]: getApiErrorMessage(error, "Не удалось загрузить рейтинг."),
      }));
    } finally {
      setLoading((previous) => ({ ...previous, [requestedScope]: false }));
    }
  }, []);

  useEffect(() => {
    if (!attempted[scope]) void loadScope(scope);
  }, [attempted, loadScope, scope]);

  const board = boards[scope];
  const entries = board?.entries ?? [];
  const yourRank = typeof board?.your_rank === "number" ? board.your_rank : null;

  return (
    <section className="bg-white">
      <div className="border-b-2 border-black bg-[#f4f4f0] p-4 md:p-6">
        <h2 className="font-display text-2xl uppercase">Рейтинг</h2>
        <p className="mt-1 text-sm text-[#666]">Первые 10 участников и твоё место в таблице.</p>
      </div>
      <Tabs
        ariaLabel="Рейтинг"
        value={scope}
        onChange={setScope}
        className="flex border-b-2 border-black"
        tabClassName="flex-1 border-r-2 border-black px-3 py-3 text-[10px] font-bold uppercase tracking-widest md:px-5 md:text-xs"
        activeClassName="bg-[#5866f2] text-white"
        inactiveClassName="hover:bg-black/5"
        items={scopeTabs}
      />

      <div className="p-4 md:p-6">
        {scope === "friends" && !isAuthenticated() ? (
          <EmptyState>Чтобы видеть рейтинг друзей, <Link href="/login" className="font-bold text-[#5866f2] underline">войдите в аккаунт</Link>.</EmptyState>
        ) : loading[scope] ? (
          <Skeleton label="Загружаем рейтинг" rows={5} />
        ) : errors[scope] ? (
          <ErrorState message={errors[scope] || "Не удалось загрузить рейтинг."} onRetry={() => void loadScope(scope)} />
        ) : entries.length === 0 ? (
          <EmptyState>
            {scope === "friends" ? "Нет данных для рейтинга друзей. Добавь друзей в профиле." : scope === "weekly" ? "Недельная лига ещё формируется или в ней пока нет участников." : "Рейтинг пока пуст."}
          </EmptyState>
        ) : (
          <div>
            {scope === "weekly" && !board?.formed && (
              <p className="mb-3 border-2 border-black bg-[#ffd500]/25 px-3 py-2 text-[10px] font-bold uppercase tracking-widest">
                Лига формируется: {entries.length}/{board?.min_size ?? 5} атлетов
              </p>
            )}
            <div className="space-y-0">
              {entries.map((entry, index) => (
                <div key={entry.id ?? entry.username ?? index}>
                  {scope === "weekly" && (index === 0 || entries[index - 1]?.division !== entry.division) && (
                    <div className="flex justify-between gap-2 bg-[#171a38] px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-white">
                      <span>{entry.division ?? "Open · provisional"}</span>
                      {entry.division_source && <span className="text-white/60">{entry.division_source}</span>}
                    </div>
                  )}
                  <div className={`flex items-center justify-between gap-3 border-b border-black/10 px-3 py-3 ${entry.is_you ? "bg-[#ffd500]/20" : "hover:bg-black/5"}`}>
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="w-8 shrink-0 font-display text-lg text-[#999]">{String(entry.rank ?? index + 1).padStart(2, "0")}</span>
                      <div className="min-w-0">
                        {entry.username ? (
                          <Link href={`/u/${entry.username}`} className="block truncate text-sm font-bold uppercase hover:text-[#5866f2]">
                            {entry.display_name || entry.username}{entry.is_you ? " (ТЫ)" : ""}
                          </Link>
                        ) : (
                          <p className="truncate text-sm font-bold uppercase">{entry.display_name || "Атлет"}</p>
                        )}
                        {scope !== "weekly" && <Label className="mt-1 text-[#666]">LVL {entry.level ?? "—"}</Label>}
                      </div>
                    </div>
                    <span className="shrink-0 font-display text-lg text-[#ff4b26]">
                      {Math.round(Number(scope === "weekly" ? entry.score : entry.total_xp ?? entry.score) || 0).toLocaleString()}
                    </span>
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
          </div>
        )}
      </div>
    </section>
  );
}
