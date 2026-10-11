"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authApi, clearAuth } from "@/lib/auth";

type SecurityState = {
  email: string | null;
  email_verified_at: string | null;
};

export default function AccountSecurity() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [verified, setVerified] = useState(false);
  const [code, setCode] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = async () => {
    try {
      const response = await authApi.get("/api/auth/me");
      const data = response.data as SecurityState;
      setEmail(data.email || "");
      setVerified(Boolean(data.email_verified_at));
    } catch {
      setMessage("Не удалось загрузить настройки безопасности.");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const requestVerification = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const response = await authApi.post("/api/auth/email/verification/request", { email });
      setEmail(response.data.email || email.trim().toLowerCase());
      setMessage(response.data.message || "Запрос обработан.");
      if (response.data.message === "Этот адрес уже подтверждён.") {
        setVerified(true);
      } else {
        setVerified(false);
      }
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || "Не удалось отправить код.");
    } finally {
      setBusy(false);
    }
  };

  const confirmVerification = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await authApi.post("/api/auth/email/verification/confirm", { code });
      setCode("");
      await load();
      setMessage("Адрес электронной почты подтверждён.");
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || "Не удалось подтвердить адрес.");
    } finally {
      setBusy(false);
    }
  };

  const changePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      await authApi.post("/api/auth/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      clearAuth();
      router.replace("/login");
    } catch (error: any) {
      setMessage(error?.response?.data?.detail || "Не удалось изменить пароль.");
      setBusy(false);
    }
  };

  const fieldClass =
    "mt-2 w-full border-2 border-black bg-white p-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#5866f2]";

  return (
    <section className="border-2 border-black bg-[#f4f4f0]">
      <div className="border-b-2 border-black bg-[#171a38] p-4 text-white">
        <h2 className="font-display text-xl uppercase">Безопасность аккаунта</h2>
        <p className="mt-1 text-xs text-white/85">Подтверждение почты и смена пароля.</p>
      </div>

      <div className="grid md:grid-cols-2">
        <div className="border-b-2 border-black p-4 md:border-b-0 md:border-r-2 md:p-6">
          <h3 className="font-display text-lg uppercase">Электронная почта</h3>
          <p className="mt-1 text-sm text-[#666]">
            {verified ? "Адрес подтверждён." : "Для сброса пароля нужен подтверждённый адрес."}
          </p>
          <form onSubmit={requestVerification} className="mt-4 space-y-3">
            <label className="block text-xs font-bold">
              Email
              <input
                type="email"
                required
                maxLength={320}
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className={fieldClass}
                placeholder="you@example.com"
              />
            </label>
            <button
              type="submit"
              disabled={busy || !email.trim()}
              className="bg-[#5866f2] px-4 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-black disabled:opacity-50"
            >
              {busy ? "Обработка..." : verified ? "Изменить адрес / отправить код" : "Отправить код"}
            </button>
          </form>
          <form onSubmit={confirmVerification} className="mt-4 space-y-3">
            <label className="block text-xs font-bold">
              Код из письма
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                minLength={6}
                maxLength={6}
                pattern="[0-9]{6}"
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                className={fieldClass}
                placeholder="123456"
              />
            </label>
            <button
              type="submit"
              disabled={busy || code.length !== 6}
              className="border-2 border-black px-4 py-3 text-xs font-bold uppercase tracking-widest hover:bg-black hover:text-white disabled:opacity-50"
            >
              Подтвердить почту
            </button>
          </form>
        </div>

        <div className="p-4 md:p-6">
          <h3 className="font-display text-lg uppercase">Сменить пароль</h3>
          <p className="mt-1 text-sm text-[#666]">
            После смены пароля все действующие сессии будут отозваны.
          </p>
          <form onSubmit={changePassword} className="mt-4 space-y-3">
            <label className="block text-xs font-bold">
              Текущий пароль
              <input
                type="password"
                required
                maxLength={128}
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                className={fieldClass}
              />
            </label>
            <label className="block text-xs font-bold">
              Новый пароль
              <input
                type="password"
                required
                minLength={6}
                maxLength={128}
                autoComplete="new-password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                className={fieldClass}
              />
            </label>
            <button
              type="submit"
              disabled={busy || currentPassword.length === 0 || newPassword.length < 6}
              className="bg-[#ff4b26] px-4 py-3 text-xs font-bold uppercase tracking-widest text-white hover:bg-black disabled:opacity-50"
            >
              {busy ? "Сохраняю..." : "Изменить пароль"}
            </button>
          </form>
        </div>
      </div>
      {message && <p role="status" className="border-t-2 border-black px-4 py-3 text-sm font-bold text-[#5866f2]">{message}</p>}
    </section>
  );
}
