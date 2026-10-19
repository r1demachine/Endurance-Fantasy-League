"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { authApi, isAuthenticated } from "@/lib/auth";
import { getApiErrorMessage } from "@/components/dialog-utils";

type TimezoneStatus = {
  authenticated?: boolean;
  timezone_name?: string;
  timezone_confirmed?: boolean;
};

export default function TimezoneConfirmation() {
  const pathname = usePathname();
  const [choice, setChoice] = useState<{ current: string; detected: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isAuthenticated()) return;
    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    let cancelled = false;

    authApi.get("/api/timezone").then(async (response) => {
      if (cancelled) return;
      const status = response.data as TimezoneStatus;
      if (!status.authenticated) return;
      const current = status.timezone_name || "UTC";
      if (status.timezone_confirmed) return;
      if (current === "UTC" && detected !== "UTC") {
        setChoice({ current, detected });
        return;
      }
      try {
        await authApi.patch("/api/timezone", { timezone_name: current, confirmed: true });
        if (!cancelled && typeof window !== "undefined") {
          window.dispatchEvent(new Event("efl:timezone-updated"));
        }
      } catch {
        // Keep timezone_confirmed=false so the next page visit can retry.
      }
    }).catch(() => {
      // Do not interrupt the page when the timezone-status request is unavailable.
    });

    return () => { cancelled = true; };
  }, [pathname]);

  const saveChoice = async (applyDetected: boolean) => {
    if (!choice) return;
    setSaving(true);
    setError("");
    try {
      await authApi.patch("/api/timezone", {
        timezone_name: applyDetected ? choice.detected : choice.current,
        confirmed: true,
      });
      setChoice(null);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("efl:timezone-updated"));
      }
    } catch (saveError: unknown) {
      setError(getApiErrorMessage(saveError, "Не удалось сохранить часовой пояс. Попробуй ещё раз."));
    } finally {
      setSaving(false);
    }
  };

  if (!choice) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 p-4" role="presentation">
      <section role="dialog" aria-modal="true" aria-labelledby="timezone-dialog-title" className="w-full max-w-lg border-2 border-black bg-[#f4f4f0] p-5 text-[#111] shadow-[8px_8px_0_rgba(0,0,0,0.35)] sm:p-7">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#5866f2]">Настройка аккаунта</p>
        <h2 id="timezone-dialog-title" className="mt-2 font-display text-2xl uppercase sm:text-3xl">Проверим часовой пояс?</h2>
        <p className="mt-3 text-sm leading-relaxed text-[#444]">
          В аккаунте установлен UTC, а браузер сообщает <strong>{choice.detected}</strong>. Часовой пояс влияет на локальные даты, сезон и будущие напоминания.
        </p>
        {error && <p role="alert" className="mt-3 border-2 border-[#ff4b26] bg-[#ff4b26]/10 p-3 text-sm text-[#a62910]">{error}</p>}
        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
          <button type="button" disabled={saving} onClick={() => void saveChoice(true)} className="flex-1 border-2 border-black bg-[#ffd500] px-4 py-3 text-xs font-bold uppercase tracking-wide hover:bg-black hover:text-white disabled:opacity-50">
            {saving ? "Сохраняем…" : `Применить ${choice.detected}`}
          </button>
          <button type="button" disabled={saving} onClick={() => void saveChoice(false)} className="flex-1 border-2 border-black bg-white px-4 py-3 text-xs font-bold uppercase tracking-wide hover:bg-black hover:text-white disabled:opacity-50">
            Оставить UTC
          </button>
        </div>
      </section>
    </div>
  );
}
