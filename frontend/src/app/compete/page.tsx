"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Tabs } from "@/components/ui";
import DuelsPanel from "@/components/compete/DuelsPanel";

type CompeteTab = "rating" | "duels" | "clubs" | "teams";
const tabs = [
  { value: "rating", label: "Рейтинг" },
  { value: "duels", label: "Дуэли" },
  { value: "clubs", label: "Клубы" },
  { value: "teams", label: "Командные сражения" },
] as const;
function isCompeteTab(value: string | null): value is CompeteTab {
  return value === "rating" || value === "duels" || value === "clubs" || value === "teams";
}

export default function CompetePage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<CompeteTab>("rating");

  useEffect(() => {
    const queryTab = new URLSearchParams(window.location.search).get("tab");
    if (isCompeteTab(queryTab)) setActiveTab(queryTab);
  }, []);

  const changeTab = (tab: CompeteTab) => {
    setActiveTab(tab);
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
        {activeTab === "duels" ? (
          <DuelsPanel />
        ) : (
          <section className="p-5 md:p-8">
            <p className="font-display text-2xl uppercase">
              {activeTab === "rating" ? "Рейтинг" : activeTab === "clubs" ? "Клубы" : "Командные сражения"}
            </p>
            <p className="mt-2 text-sm text-[#666]">
              {activeTab === "teams"
                ? "Командные сражения скоро появятся."
                : "Этот раздел будет подключён на следующем этапе обновления интерфейса."}
            </p>
          </section>
        )}
      </div>
    </main>
  );
}
