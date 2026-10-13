"use client";

import type { ReactNode } from "react";

export type SectionTitleTone = "default" | "yellow" | "orange" | "indigo" | "red";

export default function SectionTitle({ children, tone = "default" }: { children: ReactNode; tone?: SectionTitleTone }) {
  const tones: Record<SectionTitleTone, string> = {
    default: "bg-[#f4f4f0] text-[#111]",
    yellow: "bg-[#ffd500] text-[#111]",
    orange: "bg-[#ff4b26] text-white",
    indigo: "bg-[#5866f2] text-white",
    red: "bg-[#ff4b26] text-white",
  };
  return <div className={`px-4 py-3 border-b-2 border-black font-display uppercase text-xl md:text-2xl tracking-tight ${tones[tone]}`}>{children}</div>;
}
