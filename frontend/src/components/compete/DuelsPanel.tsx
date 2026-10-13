"use client";

import { useCallback, useEffect, useState } from "react";
import { authApi } from "@/lib/auth";
import { getApiErrorMessage } from "@/components/dialog-utils";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui";

type Person = { id: number; username: string; display_name: string; level?: number };
type Duel = {
  id: number;
  week_start: string | null;
  status: string;
  my_role: string;
  other: Person | null;
  my_xp: number | null;
  other_xp: number | null;
  is_draw?: boolean;
  is_no_activity_draw?: boolean;
  i_won?: boolean | null;
};

export default function DuelsPanel() {
  const [items, setItems] = useState<Duel[]>([]);
  const [friends, setFriends] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [challengeUser, setChallengeUser] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [loadError, setLoadError] = useState("");
  const [friendsError, setFriendsError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    const [duelResult, friendsResult] = await Promise.allSettled([
      authApi.get("/api/duels"),
      authApi.get("/api/friends"),
    ]);

    if (duelResult.status === "fulfilled") {
      setItems(Array.isArray(duelResult.value.data.items) ? duelResult.value.data.items : []);
      setLoadError("");
    } else {
      setLoadError(getApiErrorMessage(duelResult.reason, "Не удалось загрузить список дуэлей."));
    }

    if (friendsResult.status === "fulfilled") {
      setFriends(Array.isArray(friendsResult.value.data.friends) ? friendsResult.value.data.friends : []);
      setFriendsError("");
    } else {
      // A friends endpoint failure must not discard the successfully loaded duel list.
      setFriendsError(getApiErrorMessage(friendsResult.reason, "Не удалось загрузить друзей. Можно ввести логин вручную."));
      setFriends([]);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const challenge = async (username?: string) => {
    setMsg("");
    setLoadError("");
    const u = (username ?? challengeUser).trim().replace(/^@+/, "").toLowerCase();
    if (!u) {
      setMsg("Введи логин друга без символа @.");
      return;
    }
    setBusy(true);
    try {
      const response = await authApi.post("/api/duels/challenge", { username: u });
      setMsg(typeof response.data.message === "string" ? response.data.message : "Вызов отправлен.");
      setChallengeUser("");
      await load();
    } catch (error: unknown) {
      setMsg(getApiErrorMessage(error, "Не удалось отправить вызов."));
    } finally {
      setBusy(false);
    }
  };

  const respond = async (duelId: number, accept: boolean) => {
    setMsg("");
    setLoadError("");
    setBusy(true);
    try {
      const response = await authApi.post("/api/duels/respond", { duel_id: duelId, accept });
      setMsg(typeof response.data.message === "string" ? response.data.message : "");
      await load();
    } catch (error: unknown) {
      setMsg(getApiErrorMessage(error, "Не удалось обработать ответ на дуэль."));
      await load();
    } finally {
      setBusy(false);
    }
  };

  const statusLabels: Record<string, string> = {
    pending: "Ожидает ответа",
    active: "Идёт",
    finished: "Завершена",
    declined: "Отклонена",
  };
  const statusLabel = (status: string) => statusLabels[status] ?? status;

  return (
    <div className="space-y-0 bg-[#f4f4f0] text-[#111]">
        <section className="border-b-2 border-black p-4 md:p-6">
          <h2 className="font-display uppercase text-xl mb-3">Вызвать на дуэль</h2>
          <p className="text-[10px] font-bold tracking-widest uppercase text-[#666] mb-3">Только друзья · очки = total_xp недели · победитель при закрытии недели</p>
          <div className="flex flex-wrap gap-2 mb-4">
            <input value={challengeUser} onChange={(e) => setChallengeUser(e.target.value)} placeholder="@username друга" className="flex-1 min-w-[160px] px-3 py-3 border-2 border-black bg-white font-bold text-sm" />
            <button type="button" disabled={busy || challengeUser.trim().length < 3} onClick={() => challenge()} className="px-4 py-3 bg-[#ff4b26] text-white border-2 border-black text-[10px] font-bold tracking-widest uppercase hover:bg-black disabled:opacity-50">Вызвать</button>
          </div>
          {friendsError && <ErrorState message={friendsError} onRetry={() => { setLoading(true); void load(); }} retryLabel="Повторить загрузку" />}
          {friends.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {friends.slice(0, 12).map((f) => (
                <button key={f.id} type="button" disabled={busy} onClick={() => challenge(f.username)} className="px-3 py-2 border-2 border-black bg-white text-[10px] font-bold tracking-widest uppercase hover:bg-[#ffd500] disabled:opacity-50">{f.display_name}</button>
              ))}
            </div>
          )}
          {msg && <p role="status" className="mt-3 text-sm font-bold text-[#5866f2]">{msg}</p>}
        </section>

        <section className="border-b-2 border-black p-4 md:p-6">
          <h2 className="font-display uppercase text-xl mb-4">Твои дуэли</h2>
          {loading ? <Skeleton label="Загружаем дуэли" rows={3} /> : loadError ? (
            <ErrorState message={loadError} onRetry={() => { setLoading(true); void load(); }} retryLabel="Повторить загрузку" />
          ) : items.length === 0 ? (
            <EmptyState>Пока нет дуэлей — вызови друга выше.</EmptyState>
          ) : (
            <div className="space-y-3">
              {items.map((d) => (
                <div key={d.id} className="border-2 border-black bg-white p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                    <span className="text-[10px] font-bold tracking-widest uppercase px-2 py-1 bg-[#ffd500]">{statusLabel(d.status)}</span>
                    <span className="text-[10px] font-bold tracking-widest uppercase text-[#666]">неделя {d.week_start || "—"}</span>
                  </div>
                  <p className="font-bold uppercase tracking-wide">vs {d.other?.display_name || "?"}</p>
                  {(d.status === "active" || d.status === "finished") && (
                    <p className="mt-2 font-display text-2xl">{d.my_xp ?? 0} <span className="text-base text-[#666]">:</span> {d.other_xp ?? 0} <span className="text-sm text-[#666]">XP</span></p>
                  )}
                  {d.status === "finished" && (
                    <p className="mt-1 text-[10px] font-bold tracking-widest uppercase text-[#666]">{d.is_no_activity_draw ? "Ничья 0:0 — за неделю не было тренировок" : d.is_draw ? "Ничья" : d.i_won ? "Победа 🏆" : "Поражение"}</p>
                  )}
                  {d.status === "pending" && d.my_role === "opponent" && (
                    <div className="flex gap-2 mt-3">
                      <button type="button" disabled={busy} onClick={() => respond(d.id, true)} className="px-3 py-2 bg-[#ffd500] border-2 border-black text-[10px] font-bold tracking-widest uppercase">Принять</button>
                      <button type="button" disabled={busy} onClick={() => respond(d.id, false)} className="px-3 py-2 bg-white border-2 border-black text-[10px] font-bold tracking-widest uppercase">Отклонить</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
    </div>
  );
}
