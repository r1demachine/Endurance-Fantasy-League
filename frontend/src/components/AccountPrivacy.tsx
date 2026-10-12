"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { authApi, clearAuth } from "@/lib/auth";
import { refreshUser, clearUserCache } from "@/lib/apiCache";
import TelegramBind from "@/components/TelegramBind";
import { ConfirmDialog, type ConfirmPayload } from "@/components/Modal";
import { getApiErrorMessage } from "@/components/dialog-utils";

type PrivacyState = {
  profile_visibility: "authenticated" | "friends" | "private";
  activity_visibility: "friends" | "private";
  privacy_consent_version: string | null;
  privacy_consent_at: string | null;
  privacy_consent_current: boolean;
  current_consent_version: string;
};

export default function AccountPrivacy() {
  const [settings, setSettings] = useState<PrivacyState | null>(null);
  const [profileVisibility, setProfileVisibility] = useState<PrivacyState["profile_visibility"]>("authenticated");
  const [activityVisibility, setActivityVisibility] = useState<PrivacyState["activity_visibility"]>("friends");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  const load = async () => {
    try {
      const response = await authApi.get("/api/privacy");
      setSettings(response.data);
      setProfileVisibility(response.data.profile_visibility);
      setActivityVisibility(response.data.activity_visibility);
    } catch (error: unknown) {
      setMessage(getApiErrorMessage(error, "Не удалось загрузить настройки приватности."));
    }
  };

  useEffect(() => { void load(); }, []);

  const acceptConsent = async () => {
    setBusy(true);
    setMessage("");
    try {
      await authApi.post("/api/privacy/consent", { consent: true });
      await load();
      await refreshUser(true);
      setMessage("Согласие сохранено.");
    } catch (error: unknown) {
      setMessage(getApiErrorMessage(error, "Не удалось сохранить согласие."));
    } finally {
      setBusy(false);
    }
  };

  const saveVisibility = async () => {
    setBusy(true);
    setMessage("");
    try {
      const response = await authApi.patch("/api/privacy", {
        profile_visibility: profileVisibility,
        activity_visibility: activityVisibility,
      });
      setProfileVisibility(response.data.profile_visibility);
      setActivityVisibility(response.data.activity_visibility);
      await load();
      setMessage("Настройки приватности сохранены.");
    } catch (error: unknown) {
      setMessage(getApiErrorMessage(error, "Не удалось сохранить настройки."));
    } finally {
      setBusy(false);
    }
  };

  const deleteAccount = async ({ password, confirmation }: ConfirmPayload) => {
    setDeleteBusy(true);
    setDeleteError("");
    try {
      await authApi.delete("/api/account", { data: { confirmation, password } });
      clearAuth();
      clearUserCache();
      window.location.assign("/");
    } catch (error: unknown) {
      setDeleteError(getApiErrorMessage(error, "Не удалось удалить аккаунт."));
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <section className="border-2 border-black bg-[#f4f4f0]">
      <div className="border-b-2 border-black bg-[#5866f2] p-4 text-white">
        <h2 className="font-display text-xl uppercase">Privacy & data</h2>
        <p className="mt-1 text-xs text-white/85">Настройки видимости и контроль над персональными данными.</p>
      </div>
      <div className="space-y-6 p-4 md:p-6">
        {settings && !settings.privacy_consent_current && (
          <div className="border-2 border-[#ff4b26] bg-[#ff4b26]/10 p-4">
            <h3 className="font-display text-lg uppercase">Требуется согласие</h3>
            <p className="mt-2 text-sm">
              Для дальнейшей синхронизации и подключения Intervals нужно принять актуальную политику
              обработки данных. Она описывает хранение тренировок, пульса, нагрузки, сна и API-ключа.
            </p>
            <Link href="/data-policy" target="_blank" className="mt-2 inline-block text-sm font-bold text-[#5866f2] underline">
              Что мы храним
            </Link>
            <button
              type="button"
              onClick={acceptConsent}
              disabled={busy}
              className="mt-3 block bg-[#ff4b26] px-4 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-black disabled:opacity-50"
            >
              {busy ? "Сохраняю..." : "Я согласен — продолжить"}
            </button>
          </div>
        )}
        {settings?.privacy_consent_current && (
          <p className="text-xs text-[#666]">
            Согласие на политику {settings.privacy_consent_version} сохранено
            {settings.privacy_consent_at ? ` · ${new Date(settings.privacy_consent_at).toLocaleString()}` : ""}.
          </p>
        )}

        <div>
          <h3 className="font-display text-lg uppercase">Видимость профиля</h3>
          <p className="mt-1 text-sm text-[#666]">Доступ к сводной статистике профиля после входа в систему.</p>
          <select
            value={profileVisibility}
            onChange={(e) => setProfileVisibility(e.target.value as PrivacyState["profile_visibility"])}
            className="mt-2 w-full max-w-xl border-2 border-black bg-white p-3 text-sm"
          >
            <option value="authenticated">Все вошедшие пользователи — сводная статистика</option>
            <option value="friends">Только друзья — сводная статистика</option>
            <option value="private">Только я — профиль скрыт от других</option>
          </select>
        </div>

        <div>
          <h3 className="font-display text-lg uppercase">Детали тренировок</h3>
          <p className="mt-1 text-sm text-[#666]">Тренировки и пульс доступны только тебе и принятым друзьям; можно закрыть их полностью.</p>
          <select
            value={activityVisibility}
            onChange={(e) => setActivityVisibility(e.target.value as PrivacyState["activity_visibility"])}
            className="mt-2 w-full max-w-xl border-2 border-black bg-white p-3 text-sm"
          >
            <option value="friends">Я и принятые друзья</option>
            <option value="private">Только я</option>
          </select>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={saveVisibility}
            disabled={busy}
            className="bg-black px-5 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-[#5866f2] disabled:opacity-50"
          >
            {busy ? "Сохраняю..." : "Сохранить настройки"}
          </button>
        </div>

        {message && <p role="status" className="text-sm font-bold text-[#5866f2]">{message}</p>}

        <TelegramBind />

        <div className="border-t-2 border-black/20 pt-5">
          <h3 className="font-display text-lg uppercase text-[#ff4b26]">Удалить аккаунт</h3>
          <p className="mt-1 max-w-2xl text-sm text-[#666]">
            Будут удалены аккаунт, ключ Intervals, тренировки, wellness, связи друзей, уведомления,
            XP-события, недельные сводки и история участия в лигах. Действие необратимо.
          </p>
          <button
            type="button"
            onClick={() => {
              setDeleteError("");
              setDeleteDialogOpen(true);
            }}
            disabled={busy || deleteBusy}
            className="mt-3 border-2 border-[#ff4b26] px-5 py-3 text-xs font-bold uppercase tracking-widest text-[#ff4b26] hover:bg-[#ff4b26] hover:text-white disabled:opacity-50"
          >
            Удалить аккаунт и все данные
          </button>
        </div>
      </div>
      {deleteDialogOpen && (
        <ConfirmDialog
          title="Удалить аккаунт?"
          text="Будут безвозвратно удалены аккаунт и все связанные данные. Для подтверждения введи DELETE и пароль аккаунта."
          confirmLabel="Удалить аккаунт"
          danger
          busy={deleteBusy}
          error={deleteError}
          requireDelete
          requirePassword
          onClose={() => setDeleteDialogOpen(false)}
          onConfirm={deleteAccount}
        />
      )}
    </section>
  );
}
