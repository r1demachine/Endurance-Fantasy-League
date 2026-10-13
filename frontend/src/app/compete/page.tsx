"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Tabs, Skeleton } from "@/components/ui";
import RatingPanel from "@/components/compete/RatingPanel";
import DuelsPanel from "@/components/compete/DuelsPanel";
import { ClubsPanel } from "@/components/SocialHub";

type CompeteTab = "rating" | "duels" | "clubs" | "teams";
const tabs: { value: CompeteTab; label: string }[] = [
  { value: "rating", label: "Рейтинг" },
  { value: "duels", label: "Дуэли" },
  { value: "clubs", label: "Клубы" },
  { value: "teams", label: "Командные сражения" },
];

function isCompeteTab(value: string | null): value is CompeteTab {
  return value === "rating" || value === "duels" || value === "clubs" || value === "teams";
}

export default function CompetePage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<CompeteTab>("rating");
  const [visitedTabs, setVisitedTabs] = useState<Partial<Record<CompeteTab, boolean>>>({});
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    const queryTab = new URLSearchParams(window.location.search).get("tab");
    const initialTab: CompeteTab = isCompeteTab(queryTab) ? queryTab : "rating";
    setActiveTab(initialTab);
    setVisitedTabs({ [initialTab]: true });
    setInitialized(true);
    if (!isCompeteTab(queryTab)) router.replace(`/compete?tab=${initialTab}`, { scroll: false });
  }, [router]);

  const changeTab = (tab: CompeteTab) => {
    setActiveTab(tab);
    setVisitedTabs((previous) => ({ ...previous, [tab]: true }));
    router.replace(`/compete?tab=${tab}`, { scroll: false });
  };

  return (
    <main className="min-h-screen bg-[#f4f4f0] px-2 pb-24 text-[#111] sm:px-4 md:px-6 md:pb-8">
      <div className="mx-auto min-h-screen max-w-[1400px] border-2 border-t-0 border-black bg-white">
        <header className="border-b-2 border-black bg-[#5866f2] px-5 py-6 text-white md:px-8">
          <p className="font-display text-4xl uppercase leading-none md:text-6xl">Соревнования.</p>
          <p className="mt-3 text-[10px] font-bold uppercase tracking-widest text-white/80">Рейтинг · дуэли · клубы · команды</p>
        </header>

        <Tabs
          ariaLabel="Раздел соревнований"
          value={activeTab}
          onChange={changeTab}
          className="flex flex-wrap border-b-2 border-black"
          tabClassName="min-w-0 flex-1 border-r-2 border-black px-3 py-4 text-[10px] font-bold uppercase tracking-wide transition-colors md:px-5 md:text-xs"
          activeClassName="bg-[#ffd500] text-[#111]"
          inactiveClassName="hover:bg-black/5"
          items={tabs.map((tab) => ({ ...tab, className: tab.value === "teams" ? "border-r-0" : "" }))}
        />

        {!initialized ? (
          <div className="p-5 md:p-8"><Skeleton label="Открываем соревнования" rows={4} /></div>
        ) : (
          <>
            {visitedTabs.rating && <div hidden={activeTab !== "rating"}><RatingPanel /></div>}
            {visitedTabs.duels && <div hidden={activeTab !== "duels"}><DuelsPanel /></div>}
            {visitedTabs.clubs && <div hidden={activeTab !== "clubs"}><ClubsPanel /></div>}
            {visitedTabs.teams && (
              <div hidden={activeTab !== "teams"} className="p-4 md:p-6">
                <section className="border-2 border-black bg-white p-6 md:p-8">
                  <h2 className="font-display text-2xl uppercase md:text-3xl">Командные сражения</h2>
                  <p className="mt-2 text-sm text-[#666]">Скоро. Сражения клубов появятся в одном из следующих обновлений.</p>
                </section>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
