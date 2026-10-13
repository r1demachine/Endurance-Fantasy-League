"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Tabs, Skeleton } from "@/components/ui";
import RatingPanel from "@/components/compete/RatingPanel";
import DuelsPanel from "@/components/compete/DuelsPanel";

type CompeteTab = "rating" | "duels" | "teams";
const tabs: { value: CompeteTab; label: string }[] = [
  { value: "rating", label: "Рейтинг" },
  { value: "duels", label: "Дуэли" },
  { value: "teams", label: "Командные сражения" },
];

function isCompeteTab(value: string | null): value is CompeteTab {
  return value === "rating" || value === "duels" || value === "teams";
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
    <main className="relative flex min-h-screen flex-col overflow-hidden bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] px-2 pb-24 text-[#111] sm:px-4 md:px-6 md:pb-6">
      <div aria-hidden="true" className="pointer-events-none absolute left-[8%] top-[12%] h-3 w-3 animate-pulse rounded-full bg-[#ffd500]" />
      <div aria-hidden="true" className="pointer-events-none absolute right-[10%] top-[26%] h-2 w-2 rounded-full bg-white/80" />
      <div aria-hidden="true" className="pointer-events-none absolute bottom-[18%] right-[15%] h-4 w-4 animate-pulse rounded-full bg-white/70" />
      <div className="breathe-table relative mx-auto flex w-full max-w-[1400px] flex-1 flex-col border-2 border-t-0 border-black bg-[#f4f4f0]">
        <header className="border-b-2 border-black bg-[#5866f2] px-5 py-6 text-white md:px-8">
          <p className="font-display text-4xl uppercase leading-none md:text-6xl">Соревнования.</p>
          <p className="mt-3 text-[10px] font-bold uppercase tracking-widest text-white/80">Рейтинг · дуэли · команды</p>
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
            {visitedTabs.teams && (
              <div hidden={activeTab !== "teams"} className="p-4 md:p-6">
                <section className="border-2 border-black bg-white p-6 md:p-8">
                  <h2 className="font-display text-2xl uppercase md:text-3xl">Командные сражения</h2>
                  <p className="mt-2 text-sm text-[#666]">Скоро. Командные сражения появятся в одном из следующих обновлений.</p>
                </section>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}
