"use client";

import Link from "next/link";
import { Sticker } from "@/components/DreamBits";
import { Label, SectionTitle, Skeleton, Tabs } from "@/components/ui";

type LeaderboardTab = "global" | "friends" | "weekly";
type RatingBoardProps = {
  leaderboardTab: LeaderboardTab; setLeaderboardTab: (value: LeaderboardTab) => void;
  isAuthed: boolean; boardsLoaded: boolean; rows: any[]; yourRank: number | null;
  weeklyEntries: any[]; weeklyBoard: any; handleInvite: () => void; inviteMessage: string;
};

export default function RatingBoard({
  leaderboardTab, setLeaderboardTab, isAuthed, boardsLoaded, rows, yourRank,
  weeklyEntries, weeklyBoard, handleInvite, inviteMessage,
}: RatingBoardProps) {
  return (
    
        <div className="border-b-2 border-black">
          <div className="relative grid md:grid-cols-[200px_1fr]">
            <Sticker className="-top-3 right-4 bg-[#5866f2] text-white rotate-[3deg] z-30">who's here? 👀</Sticker>
            <div className="hidden md:flex flex-col justify-between p-5 border-r-2 border-black bg-[#5866f2] text-white">
              <div>
                <p className="font-display uppercase text-xl md:text-2xl tracking-tight leading-none">Rating</p>
                <div className="h-0.5 bg-black mt-3 mb-4"></div>
                <Label className="block text-white/80">Global & Friends</Label>
              </div>
              <span className="font-display text-4xl mt-auto">↓</span>
            </div>
            <div>
              <div className="md:hidden">
                <SectionTitle tone="indigo">Rating</SectionTitle>
              </div>
              <Tabs
                ariaLabel="Рейтинг"
                value={leaderboardTab}
                onChange={setLeaderboardTab}
                className="flex border-b-2 border-black"
                tabClassName="flex-1 px-4 py-3 text-[10px] md:text-xs font-bold tracking-widest uppercase transition-colors"
                inactiveClassName="hover:bg-black/5"
                items={[
                  { value: "global", label: "Global", activeClassName: "bg-[#5866f2] text-white" },
                  { value: "friends", label: "Friends", className: "border-l-2 border-black", activeClassName: "bg-[#5866f2] text-white" },
                  { value: "weekly", label: "Week", className: "border-l-2 border-black", activeClassName: "bg-[#ffd500] text-[#111]" },
                ]}
              />

              <div>
                {!boardsLoaded ? (
                  <Skeleton label="Loading rating..." rows={3} className="px-4 py-6" />
                ) : leaderboardTab !== "weekly" && rows.length === 0 ? (
                  <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-6">
                    {leaderboardTab === "friends"
                      ? isAuthed
                        ? "No friends yet — find athletes in your profile 👥"
                        : "Login to see your friends rating 🔐"
                      : "Be the first on the leaderboard! 🏆"}
                  </p>
                ) : leaderboardTab === "weekly" ? (
                  <div>
                    {weeklyEntries.length === 0 && (
                      <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-6">
                        Weekly league пуста — синхронизируй тренировку на этой неделе 🏁
                      </p>
                    )}
                    {!weeklyBoard?.formed && (
                      <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-3 bg-[#ffd500]/20">
                        Лига формируется: {weeklyEntries.length}/{weeklyBoard?.min_size ?? 5} атлетов
                      </p>
                    )}
                    {weeklyEntries.map((p: any, idx: number) => (
                      <div key={p.id}>
                        {(idx === 0 || weeklyEntries[idx - 1].division !== p.division) && (
                          <div className="px-4 py-2 bg-[#171a38] text-white text-[10px] font-bold tracking-widest uppercase flex justify-between">
                            <span>{p.division ?? "Open · provisional"}</span>
                            <span className="text-white/60">{p.division_source}</span>
                          </div>
                        )}
                        <div className={`flex justify-between items-center px-4 py-3 border-t border-black/10 ${p.is_you ? "bg-[#ffd500]/20" : "hover:bg-black/5"} transition-colors`}>
                          <div className="flex items-center gap-3 min-w-0">
                            <span className="font-display text-lg w-8 text-[#999]">
                              {String(p.rank).padStart(2, "0")}
                            </span>
                            <Link href={`/u/${p.username}`} className="font-bold uppercase tracking-wide text-sm hover:text-[#5866f2] transition-colors truncate">
                              {p.display_name} {p.is_you && "(YOU)"}
                            </Link>
                          </div>
                          <span className="font-display text-[#171a38]">{p.score}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <>
                  {rows.slice(0, 10).map((player, idx) => (
                    <div
                      key={player.id}
                      className={`flex justify-between items-center px-4 py-3 ${
                        idx > 0 ? "border-t border-black/20" : ""
                      } ${player.is_you ? "bg-[#5866f2]/15 border-l-4 border-l-[#5866f2]" : "hover:bg-black/5"} transition-colors`}
                    >
                      <div className="flex items-center gap-3 md:gap-4">
                        <span className={`font-display text-lg w-8 ${player.rank <= 3 ? "text-[#ff4b26]" : "text-[#999]"}`}>
                          {String(player.rank).padStart(2, "0")}
                        </span>
                        <div className="min-w-0">
                          <Link
                            href={`/u/${player.username}`}
                            className={`font-bold uppercase tracking-wide text-sm hover:text-[#5866f2] transition-colors truncate block ${player.is_you ? "text-[#5866f2]" : ""}`}
                          >
                            {player.display_name} {player.is_you && "(YOU)"}
                          </Link>
                          <Label className="text-[#666]">LVL {player.level}</Label>
                        </div>
                      </div>
                      <span className="font-display text-[#ff4b26]">
                        {Math.round(player.total_xp).toLocaleString()}
                      </span>
                    </div>
                  ))}
                  {yourRank !== null && yourRank > 10 && (
                    <>
                      <div className="border-t border-black/20 px-4 py-2 text-center font-display text-xl text-[#999]">…</div>
                      <div className="flex justify-between items-center px-4 py-3 border-t-2 border-black bg-[#ffd500]/20">
                        <span className="font-bold uppercase tracking-wide text-sm">Ты — место {yourRank}</span>
                        <span className="font-display text-[#ff4b26]">{yourRank}</span>
                      </div>
                    </>
                  )}
                  </>
                )}
              </div>

              {leaderboardTab === "friends" && (
                <div className="border-t-2 border-black">
                  {isAuthed ? (
                    <button
                      onClick={handleInvite}
                      className="w-full px-4 py-3 text-[10px] md:text-xs font-bold tracking-widest uppercase hover:bg-[#5866f2] hover:text-white transition-colors"
                    >
                      + Invite friends
                    </button>
                  ) : (
                    <Link
                      href="/login"
                      className="block w-full px-4 py-3 text-[10px] md:text-xs font-bold tracking-widest uppercase hover:bg-[#5866f2] hover:text-white transition-colors"
                    >
                      🔐 Login to see friends
                    </Link>
                  )}
                  {inviteMessage && (
                    <p className="text-[10px] font-bold text-[#5866f2] text-center py-2 bg-[#5866f2]/10">{inviteMessage}</p>
                  )}
                </div>
              )}

              <Label className="text-[#999] text-center py-3 border-t border-black/20">
                * Live rating · real athletes data
              </Label>
            </div>
          </div>
        </div>
  );
}
