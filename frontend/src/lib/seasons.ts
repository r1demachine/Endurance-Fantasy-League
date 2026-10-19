"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { authApi } from "@/lib/auth";

export const SEASONS = [
  { num: 0, flower: "Rose", color: "#e11d48" },
  { num: 1, flower: "Sunflower", color: "#ca8a04" },
  { num: 2, flower: "Lavender", color: "#7c3aed" },
  { num: 3, flower: "Cornflower", color: "#2563eb" },
  { num: 4, flower: "Poppy", color: "#ff4b26" },
  { num: 5, flower: "Forget-me-not", color: "#0ea5e9" },
  { num: 6, flower: "Lilac", color: "#a21caf" },
  { num: 7, flower: "Marigold", color: "#ea580c" },
  { num: 8, flower: "Hydrangea", color: "#0d9488" },
  { num: 9, flower: "Peony", color: "#db2777" },
] as const;

export type SeasonView = {
  num: number;
  flower: string;
  color: string;
  start: string;
  end: string;
};

// Stable server/client initial state avoids a timezone-dependent hydration mismatch.
// The API immediately replaces it with the real season for the user's local date.
const INITIAL_SEASON: SeasonView = {
  num: 1,
  flower: SEASONS[1].flower,
  color: SEASONS[1].color,
  start: "2026-09-01",
  end: "2026-09-30",
};

export function useSeason(): SeasonView {
  const pathname = usePathname();
  const [season, setSeason] = useState<SeasonView>(INITIAL_SEASON);

  useEffect(() => {
    let cancelled = false;
    const loadSeason = async () => {
      const timezoneName = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      try {
        const response = await authApi.get("/api/season", { params: { timezone_name: timezoneName } });
        if (cancelled) return;
        const data = response.data as Partial<SeasonView>;
        if (typeof data.num === "number" && typeof data.flower === "string" && typeof data.color === "string") {
          setSeason({
            num: data.num,
            flower: data.flower,
            color: data.color,
            start: typeof data.start === "string" ? data.start : "",
            end: typeof data.end === "string" ? data.end : "",
          });
        }
      } catch {
        // Keep the stable initial state if the API is temporarily unavailable.
      }
    };

    const handleTimezoneUpdate = () => { void loadSeason(); };
    void loadSeason();
    window.addEventListener("efl:timezone-updated", handleTimezoneUpdate);
    return () => {
      cancelled = true;
      window.removeEventListener("efl:timezone-updated", handleTimezoneUpdate);
    };
  }, [pathname]);

  return season;
}
