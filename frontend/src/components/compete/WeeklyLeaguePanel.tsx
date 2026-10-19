"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { authApi } from "@/lib/auth";
import { getApiErrorMessage } from "@/components/dialog-utils";
import { EmptyState, ErrorState, HelpTip, Skeleton } from "@/components/ui";

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
  beta?: boolean;
  participants?: number;
  min_size?: number;
  week?: string;
};

type ClubInvite = {
  name: string;
  invite_code: string;
};

const DIVISION_LABELS: Record<string, string> = {
  Foundation: "Основа",
  Builder: "Развитие",
  Contender: "Претенденты",
  Elite: "Элита",
  Legend: "Легенда",
  "Open · provisional": "Открытый · предварительный",
  Open: "Открытый",
};

function divisionLabel(value: string | null | undefined): string {
  if (!value) return "Открытый · предварительный";
  return DIVISION_LABELS[value] || value;
}

function divisionSourceLabel(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "beta") return "единая лига";
  if (normalized === "ctl" || normalized === "training_load") return "по CTL";
  if (normalized === "load" || normalized === "weekly_load" || normalized === "tss") return "по недельному TSS";
  if (normalized === "provisional") return "предварительный";
  return value;
}

export default function WeeklyLeaguePanel() {
  const [board, setBoard] = useState<Payload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [copyMessage, setCopyMessage] = useState("");
  const [clubInvite, setClubInvite] = useState<ClubInvite | null>(null);

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
  const isSoloBeta = Boolean(board?.beta && (board.participants ?? entries.length) === 1);

  useEffect(() => {
    if (!isSoloBeta) {
      setClubInvite(null);
      return;
    }
    let cancelled = false;
    authApi.get("/api/clubs/mine").then((response) => {
      if (cancelled) return;
      const clubs = Array.isArray(response.data?.clubs) ? response.data.clubs : [];
      const inviteClub = clubs.find((club: { name?: unknown; invite_code?: unknown }) =>
        typeof club.invite_code === "string" && club.invite_code.length > 0
      );
      setClubInvite(inviteClub ? {
        name: typeof inviteClub.name === "string" ? inviteClub.name : "клуба",
        invite_code: inviteClub.invite_code,
      } : null);
    }).catch(() => {
      if (!cancelled) setClubInvite(null);
    });
    return () => { cancelled = true; };
  }, [isSoloBeta]);

  const copyInviteLink = useCallback(async () => {
    const inviteLink = `${window.location.origin}/`;
    const inviteText = clubInvite
      ? `Endurance Fantasy League: ${inviteLink}\\nКод клуба «${clubInvite.name}»: ${clubInvite.invite_code}`
      : inviteLink;
    try {
      await navigator.clipboard.writeText(inviteText);
      setCopyMessage(clubInvite
        ? "Ссылка и код клуба скопированы. Позови друзей!"
        : "Ссылка скопирована. Позови друзей в лигу!");
    } catch {
      setCopyMessage(`Скопируй вручную: ${inviteText}`);
    }
  }, [clubInvite]);

  return (
    <section className="border-2 border-black bg-white" aria-labelledby="weekly-league-heading">
      <header className="border-b-2 border-black bg-[#171a38] px-4 py-4 text-white md:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-white/60">Таблица лидеров недели</p>
            <div className="flex items-center gap-2">
              <h2 id="weekly-league-heading" className="font-display text-2xl uppercase">Лига недели</h2>
              {board?.beta && <span className="border-2 border-[#ffd500] bg-[#ffd500] px-2 py-1 text-[10px] font-black tracking-widest text-[#111]">БЕТА</span>}
              <HelpTip label="Как работает Weekly League">
                Пока в недельной лиге меньше 20 участников, все соревнуются вместе в одной Бета-лиге без деления по дивизионам. При росте сообщества включатся обычные дивизионы.
              </HelpTip>
            </div>
          </div>
          {board?.week && <span className="text-xs font-bold text-white/75">{board.week}</span>}
        </div>
      </header>
      <div className="p-4 md:p-6">
        {loading ? (
          <Skeleton label="Загружаем Weekly League" rows={4} />
        ) : error ? (
          <ErrorState message={error} onRetry={() => void loadWeekly()} />
        ) : entries.length === 0 ? (
          <EmptyState>Пока нет результатов недели.</EmptyState>
        ) : (
          <>
            {isSoloBeta && (
              <div className="mb-4 border-2 border-black bg-[#ffd500]/25 p-4">
                <p className="font-display text-xl uppercase">Ты первый, позови друзей</p>
                <p className="mt-1 text-sm text-[#555]">Скопируй ссылку на Endurance Fantasy League и пригласи друзей соревноваться вместе.</p>
                <button type="button" onClick={() => void copyInviteLink()} className="mt-3 border-2 border-black bg-[#ffd500] px-4 py-3 text-xs font-bold uppercase tracking-wide hover:bg-black hover:text-white">
                  <span aria-hidden="true">↗ </span>{clubInvite ? "Скопировать ссылку и код клуба" : "Скопировать ссылку"}
                </button>
                {copyMessage && <p role="status" className="mt-2 text-xs font-semibold text-[#333]">{copyMessage}</p>}
              </div>
            )}
            <div className="space-y-0">
              {entries.map((entry, index) => (
                <div key={entry.id ?? entry.username ?? index}>
                  {(index === 0 || entries[index - 1]?.division !== entry.division) && (
                    <div className="flex flex-wrap justify-between gap-2 bg-[#171a38] px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-white">
                      <span>{divisionLabel(entry.division)}</span>
                      {entry.division_source && <span className="text-white/60">{divisionSourceLabel(entry.division_source)}</span>}
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
