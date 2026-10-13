"use client";

import { useState } from "react";
import { authApi } from "@/lib/auth";
import { refreshUser } from "@/lib/apiCache";
import { ConfirmDialog } from "@/components/Modal";
import { getApiErrorMessage } from "@/components/dialog-utils";

export default function IntervalsDisconnectAction({ hasKey }: { hasKey: boolean }) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const disconnect = async () => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await authApi.delete("/api/intervals/disconnect");
      setDialogOpen(false);
      setMessage(typeof response.data.message === "string"
        ? response.data.message
        : "Intervals отвязан. Тренировки, wellness и XP сохранены.");
      await refreshUser(true);
    } catch (caught: unknown) {
      setError(getApiErrorMessage(caught, "Не удалось отвязать Intervals."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="border-2 border-[#ff4b26] bg-white">
      <div className="border-b border-[#ff4b26]/30 px-4 py-3">
        <h3 className="font-display text-lg uppercase text-[#ff4b26]">Отвязать Intervals.icu</h3>
        <p className="mt-1 text-sm text-[#666]">
          Удалится только API-ключ и ID спортсмена. Все тренировки, данные восстановления, XP и недельная история останутся. Чтобы подключиться снова, потребуется ввести ключ заново.
        </p>
      </div>
      <div className="p-4">
        {hasKey ? (
          <button
            type="button"
            onClick={() => { setError(""); setDialogOpen(true); }}
            disabled={busy}
            className="border-2 border-[#ff4b26] px-4 py-3 text-xs font-bold uppercase tracking-widest text-[#ff4b26] hover:bg-[#ff4b26] hover:text-white disabled:opacity-50"
          >
            {busy ? "Отвязываем..." : "Отвязать ключ"}
          </button>
        ) : (
          <p className="text-sm text-[#666]">Intervals сейчас не подключён.</p>
        )}
        {message && <p role="status" className="mt-3 text-sm font-bold text-[#16803c]">{message}</p>}
      </div>
      {dialogOpen && (
        <ConfirmDialog
          title="Отвязать Intervals.icu?"
          text="Будет удалён только ключ и ID спортсмена Intervals.icu. История тренировок, данные сна и восстановления, недельные сводки и опыт останутся. После отвязки автоматическая синхронизация остановится."
          confirmLabel="Отвязать ключ"
          busy={busy}
          error={error}
          onClose={() => setDialogOpen(false)}
          onConfirm={disconnect}
        />
      )}
    </section>
  );
}
