"use client";

import { useEffect, useState } from "react";

/* 🌸 Сезоны: у каждого свой цветок и его цвет.
   Пока — демо-ротация каждые 3 сек (0→9).
   Потом настоящая смена раз в месяц — в useSeason замени тело на:
     const d = new Date();
     return SEASONS[(d.getFullYear() * 12 + d.getMonth()) % SEASONS.length]; */
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
];

export function useSeason() {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % SEASONS.length), 3000);
    return () => clearInterval(t);
  }, []);
  return SEASONS[idx];
}