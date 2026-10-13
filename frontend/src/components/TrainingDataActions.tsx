"use client";

import { useState } from "react";
import { authApi } from "@/lib/auth";
import { refreshUser } from "@/lib/apiCache";
import { ConfirmDialog } from "@/components/Modal";
import { getApiErrorMessage } from "@/components/dialog-utils";

type DataScope = "intervals" | "uploads" | "all";

const ACTIONS: {
  scope: DataScope;
  title: string;
  button: string;
  description: string;
  warning: string;
}[] = [
  {
    scope: "intervals",
    title: "Данные Intervals.icu",
    button: "Удалить тренировки Intervals",
    description: "Удалить только тренировки, полученные из Intervals.icu, и синхронизированные данные сна/восстановления. Загрузки FIT/GPX/TCX останутся.",
    warning: "Ключ Intervals останется подключённым. При следующей синхронизации удалённые тренировки могут импортироваться повторно. Чтобы остановить синхронизацию, сначала отвяжи ключ.",
  },
  {
    scope: "uploads",
    title: "Загруженные файлы",
    button: "Удалить загрузки FIT/GPX/TCX",
    description: "Удалить тренировки, загруженные через сайт или Telegram из FIT, GPX и TCX. Данные Intervals.icu останутся.",
    warning: "Удалятся все сохранённые загрузки из файлов и связанные с ними начисления. После удаления XP и недельные сводки будут пересчитаны на основе оставшихся данных.",
  },
  {
    scope: "all",
    title: "Все тренировочные данные",
    button: "Удалить все тренировочные данные",
    description: "Полностью очистить историю тренировок независимо от источника, wellness, XP-события, недельные сводки и данные лиги.",
    warning: "Это сбросит весь тренировочный опыт и уровень до 1. Аккаунт, настройки и ключ Intervals останутся; если ключ подключён, последующая синхронизация снова загрузит тренировки.",
  },
];

export default function TrainingDataActions() {
  const [scope, setScope] = useState<DataScope | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selected = ACTIONS.find((action) => action.scope === scope);

  const removeData = async () => {
    if (!scope) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      let message = "";
      if (scope === "all") {
        await authApi.delete("/api/reset");
        message = "Все тренировочные данные удалены. XP сброшен до 0, уровень — до 1.";
      } else {
        const response = await authApi.delete("/api/training-data", { data: { scope } });
        const xpChange = Number(response.data.xp_change ?? 0);
        const xpSuffix = xpChange > 0 ? "+" + Math.round(xpChange) : String(Math.round(xpChange));
        message = String(response.data.message ?? "Данные удалены.") +
          " Текущий XP: " + String(Math.round(response.data.total_xp ?? 0)) +
          " (изменение " + xpSuffix + "). Уровень: " + String(response.data.level ?? "—") + ".";
      }
      await refreshUser(true);
      setNotice(message);
      setScope(null);
    } catch (caught: unknown) {
      setError(getApiErrorMessage(caught, "Не удалось удалить данные. Повтори попытку."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="border-2 border-[#ff4b26] bg-white">
      <div className="border-b-2 border-[#ff4b26] bg-[#ff4b26] px-4 py-3 text-white">
        <h3 className="font-display text-xl uppercase">Удаление данных</h3>
        <p className="mt-1 text-xs text-white/90">Отдельные источники можно удалить независимо. Для каждого действия перед подтверждением появится предупреждение и трёхсекундная пауза.</p>
      </div>
      <div className="divide-y-2 divide-black">
        {ACTIONS.map((action) => (
          <div key={action.scope} className="p-4 sm:p-5">
            <h4 className="font-display text-lg uppercase">{action.title}</h4>
            <p className="mt-1 text-sm text-[#666]">{action.description}</p>
            <button
              type="button"
              onClick={() => { setError(""); setNotice(""); setScope(action.scope); }}
              disabled={busy}
              className={"mt-3 border-2 px-4 py-3 text-xs font-bold uppercase tracking-widest transition-colors disabled:opacity-50 " +
                (action.scope === "all"
                  ? "border-[#ff4b26] bg-[#ff4b26] text-white hover:bg-black"
                  : "border-[#ff4b26] text-[#ff4b26] hover:bg-[#ff4b26] hover:text-white")}
            >
              {action.button}
            </button>
          </div>
        ))}
      </div>
      {notice && <p role="status" className="border-t-2 border-black bg-[#16803c]/10 p-4 text-sm font-semibold text-[#14532d]">{notice}</p>}
      {selected && (
        <ConfirmDialog
          title={selected.title + "?"}
          text={selected.warning}
          confirmLabel={selected.button}
          danger
          busy={busy}
          error={error}
          requireDelete={selected.scope === "all"}
          onClose={() => { if (!busy) setScope(null); }}
          onConfirm={removeData}
        />
      )}
    </section>
  );
}
