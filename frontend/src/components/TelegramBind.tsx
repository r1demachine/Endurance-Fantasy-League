"use client";

import { useCallback, useEffect, useState } from "react";
import { authApi } from "@/lib/auth";

type Status = {
  bot_configured: boolean;
  bot_username: string | null;
  linked: boolean;
  notify: boolean;
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
      setStatus(r.data);
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
