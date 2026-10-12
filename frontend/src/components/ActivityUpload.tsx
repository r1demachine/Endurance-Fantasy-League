"use client";

import { useRef, useState } from "react";
import { authApi } from "@/lib/auth";
import { refreshUser } from "@/lib/apiCache";

type ParsedActivity = {
  name: string;
  sport_type: string;
  start_date: string;
  moving_time: number;
  elapsed_time: number;
  distance: number;
  elevation_gain: number;
  average_heartrate: number | null;
  max_heartrate: number | null;
  training_load: number;
  intensity: number;
  hard_secs: number;
  load_method: string;
};
type PreviewResponse = { preview_token: string; preview: ParsedActivity };

const ALLOWED_EXTENSIONS = [".fit", ".gpx", ".tcx"];
const MAX_BYTES = 5 * 1024 * 1024;

function formatDuration(seconds: number) {
  const total = Math.max(0, Math.round(seconds || 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = total % 60;
  return hours > 0
    ? String(hours) + ":" + String(minutes).padStart(2, "0") + ":" + String(remainder).padStart(2, "0")
    : String(minutes) + ":" + String(remainder).padStart(2, "0");
}
function formatStart(value: string) {
  const date = new Date(value.replace(/Z$/, "") + "Z");
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("ru-RU");
}
function getErrorMessage(error: unknown) {
  const response = (error as { response?: { data?: { detail?: unknown } } })?.response;
  const detail = response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => String((item as { msg?: unknown }).msg ?? item)).join("; ");
  }
  return "Не удалось загрузить тренировку. Проверь файл и попробуй ещё раз.";
}
const LOAD_METHODS: Record<string, string> = {
  lthr: "по указанному LTHR",
  max_hr_estimate: "по max HR (оценка порога)",
  duration_hr_estimate: "по длительности и среднему пульсу (оценка)",
  duration_sport_estimate: "по длительности и виду спорта (оценка)",
};

export default function ActivityUpload() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [parsing, setParsing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const selectFile = (nextFile: File | null) => {
    setError("");
    setSuccess("");
    setPreview(null);
    if (!nextFile) return;
    const extension = nextFile.name.slice(nextFile.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      setFile(null);
      setError("Поддерживаются только файлы .fit, .gpx и .tcx.");
      return;
    }
    if (nextFile.size > MAX_BYTES) {
      setFile(null);
      setError("Файл больше 5 МБ. Экспортируй тренировку без лишних данных или выбери другой файл.");
      return;
    }
    if (nextFile.size === 0) {
      setFile(null);
      setError("Выбранный файл пустой.");
      return;
    }
    setFile(nextFile);
  };

  const handlePreview = async () => {
    if (!file) return;
    setParsing(true);
    setError("");
    setSuccess("");
    setPreview(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await authApi.post<PreviewResponse>("/api/upload/activity", body);
      setPreview(response.data);
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setParsing(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const response = await authApi.post("/api/upload/activity/confirm", {
        preview_token: preview.preview_token,
      });
      setSuccess(String(response.data.message) + " Начислено XP: " + String(Math.round(response.data.new_xp ?? 0)) + ".");
      setFile(null);
      setPreview(null);
      if (inputRef.current) inputRef.current.value = "";
      await refreshUser(true);
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setSaving(false);
    }
  };

  const clearSelection = () => {
    setFile(null);
    setPreview(null);
    setError("");
    if (inputRef.current) inputRef.current.value = "";
  };

  const metrics = preview?.preview;
  return (
    <section className="border-2 border-black bg-white">
      <div className="border-b-2 border-black bg-[#ffd500] px-4 py-3">
        <h3 className="font-display text-xl uppercase tracking-tight">Загрузить тренировку</h3>
        <p className="mt-1 text-xs text-black/70">FIT, GPX или TCX · до 5 МБ · файл разбирается на сервере и не сохраняется</p>
      </div>
      <div className="space-y-4 p-4 md:p-5">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={(event) => { event.preventDefault(); setDragging(false); }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            selectFile(event.dataTransfer.files?.[0] ?? null);
          }}
          className={"w-full border-2 border-dashed px-4 py-7 text-left transition-colors " +
            (dragging ? "border-[#5866f2] bg-[#5866f2]/10" : "border-black/40 bg-[#f4f4f0] hover:bg-[#ffd500]/20")}
        >
          <span className="block font-bold uppercase tracking-wide">
            {file ? file.name : "Перетащи файл сюда или нажми для выбора"}
          </span>
          <span className="mt-2 block text-xs text-[#666]">
            {file ? (String((file.size / 1024).toFixed(0)) + " КБ · готов к проверке") : "Архивы ZIP/GZIP не поддерживаются"}
          </span>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".fit,.gpx,.tcx"
          className="hidden"
          onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
        />
        {file && !preview && (
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={handlePreview} disabled={parsing}
              className="border-2 border-black bg-[#ff4b26] px-4 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-black disabled:opacity-50">
              {parsing ? "Разбираем файл..." : "Проверить и показать предпросмотр"}
            </button>
            <button type="button" onClick={clearSelection} disabled={parsing}
              className="border-2 border-black px-4 py-3 text-xs font-bold uppercase tracking-widest hover:bg-black hover:text-white disabled:opacity-50">
              Отмена
            </button>
          </div>
        )}
        {metrics && (
          <div className="border-2 border-[#5866f2]">
            <div className="border-b-2 border-[#5866f2] bg-[#5866f2]/10 px-4 py-3">
              <p className="font-bold uppercase">{metrics.name}</p>
              <p className="mt-1 text-xs text-[#555]">Проверь значения перед сохранением.</p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3">
              {[
                { label: "Старт", value: formatStart(metrics.start_date) },
                { label: "Длительность", value: formatDuration(metrics.moving_time) },
                { label: "Дистанция", value: metrics.distance >= 1000 ? (metrics.distance / 1000).toFixed(2) + " км" : String(Math.round(metrics.distance)) + " м" },
                { label: "Набор", value: String(Math.round(metrics.elevation_gain)) + " м" },
                { label: "Средний пульс", value: metrics.average_heartrate == null ? "Нет данных" : String(Math.round(metrics.average_heartrate)) + " уд/мин" },
                { label: "Макс. пульс", value: metrics.max_heartrate == null ? "Нет данных" : String(Math.round(metrics.max_heartrate)) + " уд/мин" },
                { label: "hrTSS", value: metrics.training_load.toFixed(1) },
                { label: "Время в Z4+", value: formatDuration(metrics.hard_secs) },
                { label: "Вид спорта", value: metrics.sport_type },
              ].map((item) => (
                <div key={item.label} className="min-w-0 border-b border-r border-black/10 p-3">
                  <p className="text-[9px] font-bold uppercase tracking-widest text-[#666]">{item.label}</p>
                  <p className="mt-1 break-words text-sm font-bold">{item.value}</p>
                </div>
              ))}
            </div>
            <div className="px-4 py-3 text-xs text-[#555]">
              Метод расчёта нагрузки: {LOAD_METHODS[metrics.load_method] ?? "оценка"}.
              {metrics.load_method !== "lthr" && " Результат ориентировочный; точность улучшится после настройки пульсовых порогов в профиле."}
            </div>
          </div>
        )}
        {error && <p role="alert" className="border-2 border-[#ff4b26] bg-[#ff4b26]/10 px-4 py-3 text-sm font-semibold">{error}</p>}
        {success && <p role="status" className="border-2 border-[#16803c] bg-[#16803c]/10 px-4 py-3 text-sm font-semibold">{success}</p>}
        {preview && (
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={handleConfirm} disabled={saving}
              className="border-2 border-black bg-[#16803c] px-4 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-black disabled:opacity-50">
              {saving ? "Сохраняем и пересчитываем XP..." : "Подтвердить и сохранить"}
            </button>
            <button type="button" onClick={clearSelection} disabled={saving}
              className="border-2 border-black px-4 py-3 text-xs font-bold uppercase tracking-widest hover:bg-black hover:text-white disabled:opacity-50">
              Выбрать другой файл
            </button>
          </div>
        )}
        <p className="text-[11px] leading-relaxed text-[#666]">
          Тренировка будет сохранена как проверяемая запись из файла (не ручная запись) и попадёт в общий расчёт XP v6.
          Перед сохранением проверяется возможный дубль с Intervals.icu.
        </p>
      </div>
    </section>
  );
}
