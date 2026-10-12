"use client";

import { useEffect, useState } from "react";
import { authApi } from "@/lib/auth";

type HeartRateSettings = { lthr: number | null; max_hr: number | null; resting_hr: number | null; timezone_name: string };

export default function HeartRateSettings() {
  const [lthr, setLthr] = useState("");
  const [maxHr, setMaxHr] = useState("");
  const [restingHr, setRestingHr] = useState("");
  const [timezoneName, setTimezoneName] = useState("UTC");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    authApi.get<HeartRateSettings>("/api/profile/heart-rate")
      .then((response) => {
        if (cancelled) return;
        setLthr(response.data.lthr == null ? "" : String(response.data.lthr));
        setMaxHr(response.data.max_hr == null ? "" : String(response.data.max_hr));
        setRestingHr(response.data.resting_hr == null ? "" : String(response.data.resting_hr));
        setTimezoneName(response.data.timezone_name || "UTC");
      })
      .catch(() => {
        if (!cancelled) setMessage({ type: "error", text: "Не удалось загрузить настройки пульса." });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);
    const nextLthr = lthr.trim() === "" ? null : Number(lthr);
    const nextMaxHr = maxHr.trim() === "" ? null : Number(maxHr);
    const nextRestingHr = restingHr.trim() === "" ? null : Number(restingHr);
    if (nextLthr !== null && (!Number.isInteger(nextLthr) || nextLthr < 80 || nextLthr > 220)) {
      setMessage({ type: "error", text: "LTHR должен быть целым числом от 80 до 220 уд/мин." });
      return;
    }
    if (nextMaxHr !== null && (!Number.isInteger(nextMaxHr) || nextMaxHr < 100 || nextMaxHr > 240)) {
      setMessage({ type: "error", text: "Максимальный пульс должен быть целым числом от 100 до 240 уд/мин." });
      return;
    }
    if (nextRestingHr !== null && (!Number.isInteger(nextRestingHr) || nextRestingHr < 30 || nextRestingHr > 100)) {
      setMessage({ type: "error", text: "Пульс в покое должен быть целым числом от 30 до 100 уд/мин." });
      return;
    }
    if (nextLthr !== null && nextMaxHr !== null && nextLthr >= nextMaxHr) {
      setMessage({ type: "error", text: "LTHR должен быть ниже максимального пульса." });
      return;
    }

    setSaving(true);
    try {
      const response = await authApi.patch<HeartRateSettings & { saved: boolean }>("/api/profile/heart-rate", {
        lthr: nextLthr,
        max_hr: nextMaxHr,
        resting_hr: nextRestingHr,
        timezone_name: timezoneName.trim(),
      });
      setLthr(response.data.lthr == null ? "" : String(response.data.lthr));
      setMaxHr(response.data.max_hr == null ? "" : String(response.data.max_hr));
      setRestingHr(response.data.resting_hr == null ? "" : String(response.data.resting_hr));
      setTimezoneName(response.data.timezone_name || "UTC");
      setMessage({ type: "success", text: "Настройки пульса сохранены." });
    } catch (caught) {
      const detail = (caught as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setMessage({ type: "error", text: typeof detail === "string" ? detail : "Не удалось сохранить настройки пульса." });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="border-2 border-black bg-white">
      <div className="border-b-2 border-black bg-[#f4f4f0] px-4 py-3">
        <h3 className="font-display text-xl uppercase tracking-tight">Пульсовые пороги</h3>
        <p className="mt-1 text-xs text-[#666]">Нужны для расчёта HRSS / hrTSS и времени в зоне Z4+ при загрузке тренировок.</p>
      </div>
      <form onSubmit={save} className="space-y-4 p-4 md:p-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block text-xs font-bold uppercase tracking-wide">
            LTHR, уд/мин
            <input type="number" min={80} max={220} step={1} value={lthr}
              onChange={(event) => setLthr(event.target.value)} disabled={loading || saving}
              placeholder="Например, 170"
              className="mt-2 block w-full border-2 border-black bg-white px-3 py-3 text-base font-normal" />
            <span className="mt-1 block text-[10px] font-normal normal-case tracking-normal text-[#666]">Лактатный порог ЧСС, диапазон 80–220.</span>
          </label>
          <label className="block text-xs font-bold uppercase tracking-wide">
            Максимальный пульс, уд/мин
            <input type="number" min={100} max={240} step={1} value={maxHr}
              onChange={(event) => setMaxHr(event.target.value)} disabled={loading || saving}
              placeholder="Например, 190"
              className="mt-2 block w-full border-2 border-black bg-white px-3 py-3 text-base font-normal" />
            <span className="mt-1 block text-[10px] font-normal normal-case tracking-normal text-[#666]">Диапазон 100–240. LTHR должен быть ниже max HR.</span>
          </label>
          <label className="block text-xs font-bold uppercase tracking-wide">
            Пульс в покое, уд/мин
            <input type="number" min={30} max={100} step={1} value={restingHr}
              onChange={(event) => setRestingHr(event.target.value)} disabled={loading || saving}
              placeholder="Например, 50"
              className="mt-2 block w-full border-2 border-black bg-white px-3 py-3 text-base font-normal" />
            <span className="mt-1 block text-[10px] font-normal normal-case tracking-normal text-[#666]">Утренний пульс в покое, диапазон 30–100. Нужен для HRSS.</span>
          </label>
          <label className="block text-xs font-bold uppercase tracking-wide">
            Часовой пояс
            <input type="text" value={timezoneName}
              onChange={(event) => setTimezoneName(event.target.value)} disabled={loading || saving}
              placeholder="Europe/Stockholm" autoComplete="off"
              className="mt-2 block w-full border-2 border-black bg-white px-3 py-3 text-base font-normal" />
            <span className="mt-1 block text-[10px] font-normal normal-case tracking-normal text-[#666]">Название IANA, например Europe/Stockholm или Asia/Krasnoyarsk.</span>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" disabled={loading || saving}
            className="border-2 border-black bg-[#5866f2] px-4 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-black disabled:opacity-50">
            {loading ? "Загружаем..." : saving ? "Сохраняем..." : "Сохранить пульсовые пороги"}
          </button>
          <span className="text-[10px] text-[#666]">Для наиболее точной оценки HRSS укажи LTHR, max HR и утренний пульс в покое.</span>
        </div>
        {message && (
          <p role={message.type === "error" ? "alert" : "status"}
            className={"border px-3 py-2 text-xs font-semibold " +
              (message.type === "error" ? "border-[#ff4b26] bg-[#ff4b26]/10" : "border-[#16803c] bg-[#16803c]/10")}>
            {message.text}
          </p>
        )}
      </form>
    </section>
  );
}
