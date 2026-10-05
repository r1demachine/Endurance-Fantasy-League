"use client";

import { useEffect } from "react";

/* Ставит data-theme до рендера контента — без мигания светлой темы */
export default function ThemeInit() {
  useEffect(() => {
    const t = (localStorage.getItem("fl_theme") as "light" | "dark") || "light";
    document.documentElement.setAttribute("data-theme", t);
  }, []);
  return null;
}