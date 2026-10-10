"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { authApi, isAuthenticated } from "@/lib/auth";
import ActivityCard from "@/components/ActivityCard";
import XpTooltip from "@/components/XpTooltip";
import { Star, Sticker } from "@/components/DreamBits";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";

type Tone = "default" | "yellow" | "orange" | "indigo";

function SectionTitle({ children, tone = "default" }: { children: ReactNode; tone?: Tone }) {
  const tones: Record<Tone, string> = {
    default: "bg-[#f4f4f0] text-[#111]",
    yellow: "bg-[#ffd500] text-[#111]",
    orange: "bg-[#ff4b26] text-white",
    indigo: "bg-[#5866f2] text-white",
  };
  return (
    <div className={`px-4 py-3 border-b-2 border-black font-display uppercase text-xl md:text-2xl tracking-tight ${tones[tone]}`}>
      {children}
    </div>
  );
}

function Label({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <p className={`text-[9px] md:text-[10px] font-bold tracking-widest uppercase ${className}`}>{children}</p>;
}



export default function PublicProfilePage() {
  const params = useParams();
  const router = useRouter();
  const username = String(params.username || "");

  const [profile, setProfile] = useState<any>(null);
  const [activities, setActivities] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [notFound, setNotFound] = useState(false);

  const [relation, setRelation] = useState<string | null>(null);
  const [friendshipId, setFriendshipId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!username) return;
    (async () => {
      try {
        const p = await authApi.get(`/api/users/${username}`);
        setProfile(p.data);
        setRelation(p.data.user.relation ?? null);
        setFriendshipId(p.data.user.friendship_id ?? null);
        const a = await authApi.get(`/api/users/${username}/activities`, { params: { offset: 0, limit: 20 } });
        setActivities(a.data.activities);
        setTotal(a.data.total);
      } catch (e: any) {
        if (e?.response?.status === 404) setNotFound(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [username]);

  const flash = (text: string) => {
    setMsg(text);
    setTimeout(() => setMsg(""), 3000);
  };

  const addFriend = async () => {
    if (!profile) return;
    setBusy(true);
    try {
      const r = await authApi.post("/api/friends/add", { username: profile.user.username });
      setRelation(r.data.status === "accepted" ? "friends" : "sent");
      flash(r.data.message);
    } catch (e: any) {
      flash(e?.response?.data?.detail || "Ошибка заявки");
    } finally {
      setBusy(false);
    }
  };

  const acceptFriend = async () => {
    setBusy(true);
    try {
      await authApi.post("/api/friends/accept", { friendship_id: friendshipId });
      setRelation("friends");
      flash("Друг добавлен!");
    } catch {
      flash("Ошибка принятия");
    } finally {
      setBusy(false);
    }
  };

  const removeFriendship = async () => {
    setBusy(true);
    try {
      await authApi.post("/api/friends/remove", { friendship_id: friendshipId });
      setRelation(null);
      setFriendshipId(null);
      flash("Заявка удалена");
    } catch {
      flash("Ошибка удаления");
    } finally {
      setBusy(false);
    }
  };

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const a = await authApi.get(`/api/users/${username}/activities`, {
        params: { offset: activities.length, limit: 20 },
      });
      setActivities((prev) => [...prev, ...a.data.activities]);
    } catch {} finally {
      setLoadingMore(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] flex items-center justify-center">
        <p className="font-display uppercase text-2xl text-white animate-pulse">Loading athlete...</p>
      </div>
    );
  }

  if (notFound || !profile) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] flex items-center justify-center p-4">
        <div className="bg-[#f4f4f0] border-2 border-black p-8 text-center max-w-md">
          <p className="font-display uppercase text-3xl mb-2">404</p>
          <Label className="text-[#666] mb-4 block">Athlete @{username} not found</Label>
          <Link href="/" className="inline-block px-5 py-2 bg-[#ff4b26] text-white text-xs font-bold tracking-widest uppercase hover:bg-[#5866f2] transition-colors">
            ← Home
          </Link>
        </div>
      </div>
    );
  }

  const u = profile.user;
  const stats = profile.season_stats;

  const chartData = [...activities]
    .slice()
    .reverse()
    .map((act: any) => ({
      date: act.date || "",
      xp: Math.round(Number(act.xp) || 0),
      name: act.name || "workout",
      sport: act.sport || "",
      distance: act.distance_km ?? 0,
      intensityMult: act.intensity_multiplier ?? 1,
      base_xp: act.base_xp ?? 0,
      intensity_category: act.intensity_category ?? "UNKNOWN",
      streakMult: act.streak_multiplier ?? 1,
      tss_estimated: act.tss_estimated ?? false,      
    }));

  return (
    <main className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] px-2 sm:px-4 md:px-6 pb-6 text-[#111] relative overflow-hidden">
      <Star className="absolute w-6 h-6 text-white/80 top-[6%] left-[3%] animate-pulse" />
      <Star className="absolute w-5 h-5 text-[#ffd500] bottom-[10%] right-[6%] animate-pulse" />

      <div className="relative max-w-[1400px] w-full mx-auto border-2 border-t-0 border-black bg-[#f4f4f0]">
        {/* ── Шапка как в собственном профиле ── */}
        <div className="grid md:grid-cols-[200px_1fr] border-b-2 border-black">
          {/* тёмный сайдбар с буквой */}
          <div className="relative hidden md:flex items-center justify-center bg-[#171a38] text-white border-r-2 border-black min-h-[180px]">
            <Sticker className="top-2 right-2 bg-white text-black">😴</Sticker>
            <Sticker className="bottom-2 left-2 bg-white text-black">⚡</Sticker>
            <span className="font-display lowercase text-7xl">{u.display_name.charAt(0)}</span>
          </div>

          <div>
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b-2 border-black">
              <p className="font-display uppercase text-xl md:text-2xl tracking-tight">Athlete</p>
              <button
                onClick={() => router.back()}
                className="text-[10px] font-bold tracking-widest uppercase text-[#666] hover:text-[#5866f2] transition-colors"
              >
                ← Back
              </button>
            </div>
            <div className="p-5 md:p-6">
              <h1 className="font-display uppercase text-3xl md:text-5xl leading-none mb-3">{u.display_name}</h1>
              <div className="flex flex-wrap items-center gap-2">
                <span className="px-2 py-1 bg-[#171a38] text-white text-[10px] font-bold tracking-widest uppercase">LVL {u.level}</span>
                <span className="px-2 py-1 bg-[#ff4b26] text-white text-[10px] font-bold tracking-widest uppercase">
                  {Math.round(u.total_xp).toLocaleString()} XP
                </span>
                <span className="px-2 py-1 border border-black/30 text-[#666] text-[10px] font-bold tracking-widest uppercase">
                  {u.friends_count} friends
                </span>
              </div>
              <Label className="text-[#666] mt-3">@{u.username}</Label>

              {/* ── Кнопки дружбы ── */}
              {!u.is_you && isAuthenticated() && (
                <div className="mt-4">
                  <div className="flex flex-wrap items-center gap-2">
                    {relation === "friends" ? (
                      <>
                        <span className="inline-block px-5 py-3 bg-[#16a34a] text-white text-[11px] font-bold tracking-widest uppercase">
                          Friends ✓
                        </span>
                        <button
                          onClick={removeFriendship}
                          disabled={busy}
                          className="px-4 py-3 bg-white border-2 border-black text-[11px] font-bold tracking-widest uppercase hover:bg-[#ff4b26] hover:text-white transition-colors disabled:opacity-50"
                        >
                          Unfriend ✕
                        </button>
                      </>
                    ) : relation === "sent" ? (
                      <>
                        <span className="inline-block px-5 py-3 border-2 border-black/30 text-[#666] text-[11px] font-bold tracking-widest uppercase">
                          Requested
                        </span>
                        <button
                          onClick={removeFriendship}
                          disabled={busy}
                          className="px-4 py-3 bg-white border-2 border-black text-[11px] font-bold tracking-widest uppercase hover:bg-[#ff4b26] hover:text-white transition-colors disabled:opacity-50"
                        >
                          Cancel ✕
                        </button>
                      </>
                    ) : relation === "incoming" ? (
                      <>
                        <button
                          onClick={acceptFriend}
                          disabled={busy}
                          className="px-5 py-3 bg-[#ffd500] border-2 border-black text-[11px] font-bold tracking-widest uppercase hover:bg-black hover:text-white transition-colors disabled:opacity-50"
                        >
                          {busy ? "..." : "Accept ✓"}
                        </button>
                        <button
                          onClick={removeFriendship}
                          disabled={busy}
                          className="px-4 py-3 bg-white border-2 border-black text-[11px] font-bold tracking-widest uppercase hover:bg-[#ff4b26] hover:text-white transition-colors disabled:opacity-50"
                        >
                          Reject ✕
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={addFriend}
                        disabled={busy}
                        className="px-5 py-3 bg-[#ff4b26] text-white text-[11px] font-bold tracking-widest uppercase hover:bg-[#5866f2] transition-colors disabled:opacity-50"
                      >
                        {busy ? "..." : "+ Add friend"}
                      </button>
                    )}
                  </div>
                  {msg && <p className="text-[10px] font-bold text-[#5866f2] mt-2">{msg}</p>}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Season Stats ── */}
        <SectionTitle>Season Stats</SectionTitle>
        <div className="p-4 md:p-6">
          <Label className="text-[#666] mb-4 block">Since {stats.season_start}</Label>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 w-full">
            {[
              { label: "Distance", value: stats.total_km, unit: "km" },
              { label: "Time", value: stats.total_hours, unit: "h" },
              { label: "Climb", value: stats.total_elevation, unit: "m" },
              { label: "Workouts", value: stats.total_workouts, unit: "" },
              { label: "XP", value: Math.round(stats.total_xp), unit: "" },
            ].map((s) => (
              <div key={s.label} className="p-3 md:p-4 text-center">
                <p className="font-display text-xl md:text-3xl">
                  {s.value}<span className="text-xs text-[#666] ml-0.5">{s.unit}</span>
                </p>
                <Label className="text-[#666] mt-1">{s.label}</Label>
              </div>
            ))}
          </div>
        </div>

        {/* ── XP Dynamics (как на дашборде) ── */}
        {chartData.length > 0 && (
          <div className="border-t-2 border-black">
            <SectionTitle tone="orange">XP Dynamics</SectionTitle>
            <div className="p-4 md:p-6 bg-white">
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="xpFillPub" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#ff4b26" stopOpacity={0.3} />
                        <stop offset="100%" stopColor="#ff4b26" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#00000015" />
                    <XAxis dataKey="date" tick={{ fill: "#666", fontSize: 10 }} axisLine={{ stroke: "#000" }} tickLine={false} />
                    <YAxis tick={{ fill: "#666", fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
                    <Tooltip content={<XpTooltip chartData={chartData} showSleep={false} />} />
                    <Area
                      type="monotone"
                      dataKey="xp"
                      stroke="#ff4b26"
                      strokeWidth={2.5}
                      fill="url(#xpFillPub)"
                      activeDot={{ r: 5, fill: "#171a38", stroke: "#ffd500", strokeWidth: 2 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}

        {/* ── Тренировки ── */}
        <div className="border-t-2 border-black">
          <SectionTitle tone="indigo">Workouts</SectionTitle>
          <div className="p-4 md:p-6">
            <Label className="text-[#666] mb-3 block">Last workouts · {total} total</Label>
            {activities.length === 0 ? (
              <p className="text-sm text-[#666]">No workouts yet.</p>
            ) : (
              <div className="space-y-0">
                {activities.map((act: any, idx: number) => (
                  <div key={act.id} className={idx > 0 ? "border-t-2 border-black" : ""}>
                    <ActivityCard act={act} />
                  </div>
                ))}
              </div>
            )}
            {activities.length < total && (
              <button
                onClick={loadMore}
                disabled={loadingMore}
                className="w-full mt-4 px-4 py-3 border-2 border-black text-[10px] md:text-xs font-bold tracking-widest uppercase hover:bg-[#5866f2] hover:text-white transition-colors disabled:opacity-50"
              >
                {loadingMore ? "Loading..." : `Load more (${total - activities.length} left)`}
              </button>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}