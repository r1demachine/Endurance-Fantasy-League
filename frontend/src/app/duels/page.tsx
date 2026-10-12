"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { authApi } from "@/lib/auth";

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
  i_won?: boolean | null;
};

export default function DuelsPage() {
  const [items, setItems] = useState<Duel[]>([]);
  const [friends, setFriends] = useState<Person[]>([]);
  const [loading, setLoading] = useState(true);
  const [challengeUser, setChallengeUser] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const [d, f] = await Promise.all([authApi.get("/api/duels"), authApi.get("/api/friends")]);
      setItems(d.data.items || []);
      setFriends(f.data.friends || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const challenge = async (username?: string) => {
    const u = (username || challengeUser).trim().toLowerCase();
    if (!u) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await authApi.post("/api/duels/challenge", { username: u });
      setMsg(r.data.message || "Вызов отправлен");
      setChallengeUser("");
      await load();
    } catch (err: any) {
      setMsg(err.response?.data?.detail || "Ошибка вызова");
    } finally {
      setBusy(false);
    }
  };

  const respond = async (duelId: number, accept: boolean) => {
    setBusy(true);
    try {
      await authApi.post("/api/duels/respond", { duel_id: duelId, accept });
      await load();
    } catch (err: any) {
      setMsg(err.response?.data?.detail || "Ошибка");
    } finally {
      setBusy(false);
    }
  };

  const statusLabel = (s: string) =>
    ({ pending: "Ожидает ответа", active: "Идёт", finished: "Завершена", declined: "Отклонена" } as any)[s] || s;

  return (
    <main className="min-h-screen bg-[#f4f4f0] text-[#111] pb-24 md:pb-8">
      <div className="max-w-[900px] mx-auto border-x-2 border-black min-h-screen">
        <div className="border-b-2 border-black bg-[#5866f2] text-white px-4 py-4 flex items-center justify-between gap-3">
          <div>
            <p className="font-display uppercase text-2xl md:text-3xl leading-none">Дуэли и лиги</p>
            <p className="text-[10px] font-bold tracking-widest uppercase mt-1 text-white/80">1 на 1 · клубы · командные сражения</p>
          </div>
          <Link href="/dashboard" className="px-3 py-2 border-2 border-black bg-white text-[#111] text-[10px] font-bold tracking-widest uppercase hover:bg-black hover:text-white">← Dashboard</Link>
        </div>

        <section className="border-b-2 border-black p-4 md:p-6">
          <h2 className="font-display uppercase text-xl mb-3">Вызвать на дуэль</h2>
          <p className="text-[10px] font-bold tracking-widest uppercase text-[#666] mb-3">Только друзья · очки = total_xp недели · победитель при закрытии недели</p>
          <div className="flex flex-wrap gap-2 mb-4">
            <input value={challengeUser} onChange={(e) => setChallengeUser(e.target.value)} placeholder="@username друга" className="flex-1 min-w-[160px] px-3 py-3 border-2 border-black bg-white font-bold text-sm" />
            <button type="button" disabled={busy || challengeUser.trim().length < 3} onClick={() => challenge()} className="px-4 py-3 bg-[#ff4b26] text-white border-2 border-black text-[10px] font-bold tracking-widest uppercase hover:bg-black disabled:opacity-50">Вызвать</button>
          </div>
          {friends.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {friends.slice(0, 12).map((f) => (
                <button key={f.id} type="button" disabled={busy} onClick={() => challenge(f.username)} className="px-3 py-2 border-2 border-black bg-white text-[10px] font-bold tracking-widest uppercase hover:bg-[#ffd500] disabled:opacity-50">{f.display_name}</button>
              ))}
            </div>
          )}
          {msg && <p className="mt-3 text-sm font-bold text-[#5866f2]">{msg}</p>}
        </section>

        <section className="border-b-2 border-black p-4 md:p-6">
          <h2 className="font-display uppercase text-xl mb-4">Твои дуэли</h2>
          {loading ? <p className="text-sm text-[#666]">Загрузка…</p> : items.length === 0 ? (
            <p className="text-sm text-[#666]">Пока нет дуэлей — вызови друга выше.</p>
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
                    <p className="mt-1 text-[10px] font-bold tracking-widest uppercase text-[#666]">{d.is_draw ? "Ничья" : d.i_won ? "Победа 🏆" : "Поражение"}</p>
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

        <section className="p-4 md:p-6">
          <div className="border-2 border-dashed border-black/40 bg-white px-4 py-8 text-center">
            <p className="font-display uppercase text-2xl md:text-3xl">Командные сражения</p>
            <p className="text-[10px] font-bold tracking-widest uppercase text-[#666] mt-2">в процессе разработки 🚧</p>
            <p className="text-sm text-[#666] mt-4 max-w-md mx-auto">Клуб против клуба появится позже. Клубы — во вкладке Clubs в профиле.</p>
            <Link href="/profile" className="inline-block mt-4 px-4 py-2 border-2 border-black bg-[#ffd500] text-[10px] font-bold tracking-widest uppercase hover:bg-black hover:text-white">Клубы в профиле →</Link>
          </div>
        </section>
      </div>
    </main>
  );
}
