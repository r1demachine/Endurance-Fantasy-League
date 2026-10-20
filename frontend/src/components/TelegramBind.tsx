"use client";

import { useCallback, useEffect, useState } from "react";
import { authApi } from "@/lib/auth";

type NotifyPrefKey = "daily_bonus_reminder" | "league_overtaken" | "weekly_results" | "activity_social";

type NotifyPrefs = Record<NotifyPrefKey, boolean>;

const DEFAULT_NOTIFY_PREFS: NotifyPrefs = {
  daily_bonus_reminder: true,
  league_overtaken: true,
  weekly_results: true,
  activity_social: true,
};

const NOTIFY_PREFS: { key: NotifyPrefKey; label: string; detail: string }[] = [
  { key: "daily_bonus_reminder", label: "Напоминание о дневном бонусе", detail: "Вечером, если бонус +20 XP ещё доступен" },
  { key: "league_overtaken", label: "Меня обошли в лиге", detail: "Если место ухудшилось за текущую неделю" },
  { key: "weekly_results", label: "Итоги недели", detail: "XP, тренировочные дни и результат лиги" },
  { key: "activity_social", label: "Лайки и комментарии", detail: "Реакции на твои тренировки" },
];

type Status = {
  bot_configured: boolean;
  bot_username: string | null;
  linked: boolean;
  notify: boolean;
  notify_prefs: NotifyPrefs;
  has_pending_code: boolean;
};

export default function TelegramBind() {
  const [status, setStatus] = useState<Status | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [expires, setExpires] = useState<string | null>(null);
  const [deepLink, setDeepLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      const r = await authApi.get("/api/telegram/status");
      setStatus({
        ...r.data,
        notify_prefs: { ...DEFAULT_NOTIFY_PREFS, ...(r.data.notify_prefs || {}) },
      });
      if (r.data.linked) {
        setCode(null);
        setDeepLink(null);
        setExpires(null);
      }
    } catch {
      setStatus({
        bot_configured: false,
        bot_username: null,
        linked: false,
        notify: false,
        notify_prefs: DEFAULT_NOTIFY_PREFS,
        has_pending_code: false,
      });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const genCode = async () => {
    setBusy(true);
    setMsg("");
    try {
      const r = await authApi.post("/api/telegram/link-code");
      setCode(r.data.code);
      setExpires(r.data.expires_at);
      setDeepLink(typeof r.data.deep_link === "string" ? r.data.deep_link : null);
      setMsg(r.data.instructions || "Открой ссылку, чтобы привязать аккаунт.");
      await load();
    } catch (e: any) {
      setMsg(e.response?.data?.detail || "Не удалось создать код");
    } finally {
      setBusy(false);
    }
  };

  const toggleNotify = async (enabled: boolean) => {
    setBusy(true);
    try {
      await authApi.post("/api/telegram/notify", { enabled });
      await load();
    } catch (e: any) {
      setMsg(e.response?.data?.detail || "Ошибка");
    } finally {
      setBusy(false);
    }
  };

  const togglePreference = async (key: NotifyPrefKey, enabled: boolean) => {
    setBusy(true);
    setMsg("");
    try {
      const response = await authApi.patch("/api/telegram/preferences", { [key]: enabled });
      setStatus((current) => current ? {
        ...current,
        notify_prefs: { ...DEFAULT_NOTIFY_PREFS, ...(response.data.notify_prefs || {}), [key]: enabled },
      } : current);
    } catch (e: any) {
      setMsg(e.response?.data?.detail || "Не удалось сохранить настройки уведомлений");
    } finally {
      setBusy(false);
    }
  };

  const unlink = async () => {
    setBusy(true);
    try {
      await authApi.post("/api/telegram/unlink");
      setCode(null);
      setDeepLink(null);
      await load();
      setMsg("Telegram отвязан");
    } catch (e: any) {
      setMsg(e.response?.data?.detail || "Ошибка");
    } finally {
      setBusy(false);
    }
  };

  if (!status) return null;

  return (
    <div data-tour="profile-telegram-bind" className="border-t-2 border-black/20 pt-5">
      <h3 className="font-display text-lg uppercase">Telegram</h3>
      <p className="mt-1 max-w-2xl text-sm text-[#666]">
        Привяжи бота для уведомлений (итоги недели, дуэли) и загрузки .fit / .gpx / .tcx.
      </p>

      {!status.bot_configured ? (
        <p className="mt-3 text-sm font-bold text-[#666]">Бот на сервере пока не настроен.</p>
      ) : (
        <div className="mt-3 space-y-3">
          <p className="text-[10px] font-bold tracking-widest uppercase text-[#666]">
            {status.linked ? "Привязан" : "Не привязан"}
            {status.bot_username ? ` · @${status.bot_username}` : ""}
            {status.linked ? ` · уведомления ${status.notify ? "вкл" : "выкл"}` : ""}
          </p>

          {!status.linked && (
            <button
              type="button"
              disabled={busy}
              onClick={genCode}
              className="border-2 border-black bg-[#ffd500] px-5 py-3 text-xs font-bold uppercase tracking-widest hover:bg-black hover:text-white disabled:opacity-50"
            >
              {busy ? "…" : "Получить код привязки"}
            </button>
          )}

          {code && (
            <div className="border-2 border-black bg-white p-3">
              <p className="text-[10px] font-bold tracking-widest uppercase text-[#666]">Код (15 мин)</p>
              <p className="font-display text-3xl tracking-widest">{code}</p>
              {deepLink ? (
                <a
                  href={deepLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-flex border-2 border-black bg-[#229ED9] px-4 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-black"
                >
                  Открыть Telegram и привязать
                </a>
              ) : (
                <p className="mt-1 text-sm text-[#666]">
                  В боте отправь: <span className="font-bold">/link {code}</span>
                </p>
              )}
              <p className="mt-2 text-xs text-[#666]">
                Ссылка одноразовая и действует 15 минут. Уведомления включаются отдельно после привязки.
              </p>
              <button
                type="button"
                disabled={busy}
                onClick={load}
                className="mt-3 border border-black/40 px-3 py-2 text-[10px] font-bold uppercase tracking-wide hover:bg-[#ffd500] disabled:opacity-50"
              >
                Я привязал — проверить статус
              </button>
              {expires && <p className="mt-1 text-[10px] text-[#666]">до {expires}</p>}
            </div>
          )}

          {status.linked && (
            <fieldset className="border-2 border-black bg-white p-3">
              <legend className="px-2 font-display text-sm uppercase">Какие уведомления присылать</legend>
              <div className="space-y-1">
                {NOTIFY_PREFS.map((item) => (
                  <label key={item.key} className="flex cursor-pointer items-start gap-3 border-b border-black/10 py-2 last:border-0">
                    <input
                      type="checkbox"
                      checked={Boolean(status.notify_prefs[item.key])}
                      disabled={busy}
                      onChange={(event) => void togglePreference(item.key, event.target.checked)}
                      className="mt-1 h-4 w-4 accent-[#5866f2] disabled:opacity-50"
                    />
                    <span className="min-w-0">
                      <span className="block text-sm font-bold">{item.label}</span>
                      <span className="block text-xs text-[#666]">{item.detail}</span>
                    </span>
                  </label>
                ))}
              </div>
              <p className="mt-2 text-[10px] text-[#666]">
                Не больше одного проактивного сообщения в сутки и четырёх в неделю. Глобальный переключатель выше отключает все сообщения.
              </p>
            </fieldset>
          )}

          {status.linked && (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => toggleNotify(!status.notify)}
                className="border-2 border-black bg-white px-4 py-2 text-[10px] font-bold uppercase tracking-widest hover:bg-[#ffd500]"
              >
                {status.notify ? "Выключить уведомления" : "Включить уведомления"}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={unlink}
                className="border-2 border-[#ff4b26] px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-[#ff4b26] hover:bg-[#ff4b26] hover:text-white"
              >
                Отвязать
              </button>
            </div>
          )}
        </div>
      )}
      {msg && <p className="mt-2 text-sm font-bold text-[#5866f2]">{msg}</p>}
    </div>
  );
}
