"use client";

import { useEffect, useState, type FormEvent } from "react";
import { AnimatePresence } from "framer-motion";
import { authApi } from "@/lib/auth";
import { refreshUser } from "@/lib/apiCache";
import ConnectSources, { type ConnectMessage } from "@/components/ConnectSources";
import TelegramBind from "@/components/TelegramBind";
import HeartRateSettings from "@/components/HeartRateSettings";
import ActivityUpload from "@/components/ActivityUpload";
import AccountPrivacy from "@/components/AccountPrivacy";
import IntervalsDisconnectAction from "@/components/IntervalsDisconnectAction";
import { Modal, PauseDialog } from "@/components/Modal";
import TrainingDataActions from "@/components/TrainingDataActions";
import { getApiErrorMessage } from "@/components/dialog-utils";
import { useTheme } from "@/lib/theme";

export type SettingsTab = "account" | "appearance" | "sources" | "training" | "privacy" | "danger";

const TABS: { id: SettingsTab; label: string; emoji: string }[] = [
  { id: "account", label: "Аккаунт", emoji: "👤" },
  { id: "appearance", label: "Оформление", emoji: "🎨" },
  { id: "sources", label: "Источники данных", emoji: "🔌" },
  { id: "training", label: "Тренировки и пульс", emoji: "🚴" },
  { id: "privacy", label: "Приватность", emoji: "🔒" },
  { id: "danger", label: "Опасная зона", emoji: "⚠️" },
];

type UserData = {
  user?: {
    name?: string;
    username?: string;
    has_intervals_key?: boolean;
    intervals_id?: string | null;
    pause_set_at?: string | null;
    paused_until?: string | null;
  };
};

export default function ProfileSettingsModal({
  tab,
  userData,
  onClose,
  onTabChange,
  onLogout,
  onDataUpdated,
}: {
  tab: SettingsTab;
  userData: UserData | null;
  onClose: () => void;
  onTabChange: (tab: SettingsTab) => void;
  onLogout: () => void | Promise<void>;
  onDataUpdated?: () => void | Promise<void>;
}) {
  const [displayName, setDisplayName] = useState(userData?.user?.name ?? "");
  const [nameSaving, setNameSaving] = useState(false);
  const [notice, setNotice] = useState<ConnectMessage | null>(null);
  const [pauseDialogOpen, setPauseDialogOpen] = useState(false);
  const [pauseBusy, setPauseBusy] = useState(false);
  const [pauseError, setPauseError] = useState("");
  const [pauseNow, setPauseNow] = useState(Date.now());
  const { theme, toggle } = useTheme();

  useEffect(() => {
    setDisplayName(userData?.user?.name ?? "");
  }, [userData?.user?.name]);

  const saveName = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalized = displayName.trim();
    if (normalized.length < 2 || normalized.length > 50) {
      setNotice({ type: "error", text: "Имя должно содержать от 2 до 50 символов." });
      return;
    }

    setNameSaving(true);
    setNotice(null);
    try {
      const response = await authApi.patch("/api/auth/me", { display_name: normalized });
      setDisplayName(response.data.display_name ?? normalized);
      await refreshUser(true);
      setNotice({ type: "success", text: "Имя сохранено." });
    } catch (error: unknown) {
      setNotice({ type: "error", text: getApiErrorMessage(error, "Не удалось сохранить имя.") });
    } finally {
      setNameSaving(false);
    }
  };

  const savePause = async (weeks: number) => {
    setPauseBusy(true);
    setPauseError("");
    try {
      await authApi.post("/api/pause", { weeks });
      await refreshUser(true);
      setPauseDialogOpen(false);
      setNotice({
        type: "success",
        text: weeks === 0 ? "Пауза снята." : "Пауза установлена на " + String(weeks) + (weeks === 1 ? " неделю." : " недели."),
      });
    } catch (error: unknown) {
      setPauseError(getApiErrorMessage(error, "Не удалось изменить паузу."));
    } finally {
      setPauseBusy(false);
    }
  };

  const selected = TABS.find((item) => item.id === tab) ?? TABS[0];

  return (
    <>
      <Modal title="Настройки" closeLabel="Закрыть" onClose={onClose} variant="settings">
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <nav aria-label="Разделы настроек" className="shrink-0 border-b-2 border-black bg-white p-2 md:w-60 md:overflow-y-auto md:border-b-0 md:border-r-2 md:p-3">
            <div className="flex gap-2 overflow-x-auto md:flex-col">
              {TABS.map((item) => {
                const active = item.id === tab;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => { setNotice(null); onTabChange(item.id); }}
                    aria-current={active ? "page" : undefined}
                    aria-label={item.label}
                    title={item.label}
                    className={"flex min-h-11 shrink-0 items-center justify-center gap-3 border-2 px-3 py-2 text-left text-xs font-bold uppercase tracking-wide transition-colors md:w-full md:justify-start " +
                      (active
                        ? (item.id === "danger" ? "border-[#ff4b26] bg-[#ff4b26] text-white" : "border-black bg-[#5866f2] text-white")
                        : "border-transparent bg-[#f4f4f0] text-[#111] hover:border-black")}
                  >
                    <span aria-hidden="true" className="text-lg leading-none">{item.emoji}</span>
                    <span className="hidden md:inline">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </nav>

          <section role="tabpanel" aria-label={selected.label} className="min-h-0 min-w-0 flex-1 overflow-y-auto p-3 sm:p-5 md:p-6">
            <div className="mb-5 border-b-2 border-black pb-4">
              <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#5866f2]">Profile settings</p>
              <h3 className="mt-1 font-display text-2xl uppercase md:text-3xl">{selected.label}</h3>
            </div>

            {notice && (
              <p role={notice.type === "error" ? "alert" : "status"}
                className={"mb-4 border-2 px-4 py-3 text-sm font-semibold " +
                  (notice.type === "error"
                    ? "border-[#ff4b26] bg-[#ff4b26]/10 text-[#a62910]"
                    : notice.type === "success"
                      ? "border-[#16803c] bg-[#16803c]/10 text-[#14532d]"
                      : "border-[#5866f2] bg-[#5866f2]/10 text-[#272e82]")}>
                {notice.text}
              </p>
            )}

            {tab === "account" && (
              <div className="max-w-2xl space-y-6">
                <form onSubmit={saveName} className="space-y-4 border-2 border-black bg-white p-4 sm:p-5">
                  <div>
                    <label htmlFor="profile-display-name" className="block text-[10px] font-bold uppercase tracking-widest text-[#555]">Имя</label>
                    <input
                      id="profile-display-name"
                      value={displayName}
                      onChange={(event) => setDisplayName(event.target.value)}
                      minLength={2}
                      maxLength={50}
                      required
                      autoComplete="name"
                      className="mt-2 w-full border-2 border-black bg-white px-3 py-3 text-base"
                    />
                  </div>
                  <div>
                    <label htmlFor="profile-username" className="block text-[10px] font-bold uppercase tracking-widest text-[#555]">Username · только чтение</label>
                    <input
                      id="profile-username"
                      value={userData?.user?.username ?? ""}
                      readOnly
                      aria-readonly="true"
                      className="mt-2 w-full cursor-not-allowed border-2 border-black/20 bg-[#f4f4f0] px-3 py-3 text-base text-[#666]"
                    />
                  </div>
                  <button type="submit" disabled={nameSaving}
                    className="border-2 border-black bg-[#5866f2] px-5 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-black disabled:opacity-50">
                    {nameSaving ? "Сохраняю..." : "Сохранить имя"}
                  </button>
                </form>

                <div className="border-2 border-black bg-white p-4 sm:p-5">
                  <h4 className="font-display text-lg uppercase">Сессия</h4>
                  <p className="mt-1 text-sm text-[#666]">Выйти из аккаунта на этом устройстве и отозвать активную сессию.</p>
                  <button type="button" onClick={() => void onLogout()}
                    className="mt-4 border-2 border-black px-5 py-3 text-xs font-bold uppercase tracking-widest hover:bg-black hover:text-white">
                    Выйти из аккаунта
                  </button>
                </div>

                <div className="border border-black/20 bg-white/60 p-4">
                  <h4 className="font-display text-lg uppercase">Смена пароля</h4>
                  <p className="mt-1 text-sm text-[#666]">В текущем API нет endpoint для смены пароля, поэтому здесь эта операция пока недоступна.</p>
                </div>
              </div>
            )}

            {tab === "sources" && (
              <div className="space-y-5">
                <ConnectSources
                  hasKey={Boolean(userData?.user?.has_intervals_key)}
                  athleteId={userData?.user?.intervals_id ?? null}
                  onMessage={setNotice}
                  onDataUpdated={onDataUpdated}
                  allowDisconnectAction={false}
                />
                <TelegramBind />
              </div>
            )}

            {tab === "training" && (
              <div className="space-y-5">
                <HeartRateSettings />
                <ActivityUpload onUploaded={onDataUpdated} />
                <div className="border-2 border-black bg-white">
                  <div className="border-b-2 border-black bg-[#171a38] px-4 py-3 text-white">
                    <h4 className="font-display text-lg uppercase">Пауза тренировок</h4>
                    <p className="mt-1 text-xs text-white/80">Болезнь или отпуск: пауза на срок до 8 недель.</p>
                  </div>
                  <div className="p-4">
                    {userData?.user?.paused_until && (
                      <p className="mb-3 text-sm text-[#555]">
                        Текущая дата окончания: {new Date(userData.user.paused_until).toLocaleDateString("ru-RU")}
                      </p>
                    )}
                    <button type="button" onClick={() => { setPauseNow(Date.now()); setPauseError(""); setPauseDialogOpen(true); }}
                      className="border-2 border-black bg-[#ffd500] px-5 py-3 text-xs font-bold uppercase tracking-widest hover:bg-black hover:text-white">
                      Настроить паузу
                    </button>
                  </div>
                </div>
              </div>
            )}

            {tab === "appearance" && (
              <div className="max-w-2xl border-2 border-black bg-white p-4 sm:p-5">
                <h4 className="font-display text-lg uppercase">Тема оформления</h4>
                <p className="mt-2 text-sm text-[#666]">
                  Выбери, как будет выглядеть приложение. Настройка сохраняется на этом устройстве.
                </p>
                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => { if (theme !== "light") toggle(); }}
                    aria-pressed={theme === "light"}
                    className={"flex items-center justify-between gap-3 border-2 px-4 py-4 text-left text-sm font-bold uppercase tracking-wide transition-colors " +
                      (theme === "light" ? "border-black bg-[#ffd500] text-[#111]" : "border-black/20 bg-[#f4f4f0] hover:border-black")}
                  >
                    <span>☀ Светлая</span>
                    {theme === "light" && <span aria-hidden="true">✓</span>}
                  </button>
                  <button
                    type="button"
                    onClick={() => { if (theme !== "dark") toggle(); }}
                    aria-pressed={theme === "dark"}
                    className={"flex items-center justify-between gap-3 border-2 px-4 py-4 text-left text-sm font-bold uppercase tracking-wide transition-colors " +
                      (theme === "dark" ? "border-black bg-[#5866f2] text-white" : "border-black/20 bg-[#f4f4f0] hover:border-black")}
                  >
                    <span>☾ Тёмная</span>
                    {theme === "dark" && <span aria-hidden="true">✓</span>}
                  </button>
                </div>
              </div>
            )}

            {tab === "privacy" && <AccountPrivacy section="privacy" />}

            {tab === "danger" && (
              <div className="space-y-5">
                <IntervalsDisconnectAction hasKey={Boolean(userData?.user?.has_intervals_key)} />
                <TrainingDataActions />
                <AccountPrivacy section="danger" />
              </div>
            )}
          </section>
        </div>
      </Modal>

      <AnimatePresence>
        {pauseDialogOpen && (
          <PauseDialog
            onClose={() => setPauseDialogOpen(false)}
            onSubmit={savePause}
            busy={pauseBusy}
            error={pauseError}
            now={pauseNow}
            pauseSetAt={userData?.user?.pause_set_at ?? null}
            pausedUntil={userData?.user?.paused_until ?? null}
          />
        )}
      </AnimatePresence>
    </>
  );
}
