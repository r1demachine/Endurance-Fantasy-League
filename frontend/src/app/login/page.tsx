"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authApi, setToken } from "@/lib/auth";
import { Star, Sticker } from "@/components/DreamBits";

type Mode = "login" | "register" | "verify-registration" | "reset-request" | "reset-confirm";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [code, setCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [privacyConsent, setPrivacyConsent] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setStatus(null);
    setLoading(true);

    try {
      if (mode === "login") {
        const response = await authApi.post("/api/auth/login", { username, password });
        setToken(response.data.access_token, response.data.user);
        router.push("/profile");
      } else if (mode === "register") {
        const response = await authApi.post("/api/auth/register", {
          username,
          email,
          password,
          display_name: displayName || username,
          privacy_consent: privacyConsent,
        });
        setEmail(response.data.email || email.trim().toLowerCase());
        setCode("");
        setMode("verify-registration");
        setStatus("Код отправлен на почту. Введите его в течение 10 минут, чтобы завершить регистрацию.");
      } else if (mode === "verify-registration") {
        const response = await authApi.post("/api/auth/registration/verify", { email, code });
        setToken(response.data.access_token, response.data.user);
        router.push("/profile");
      } else if (mode === "reset-request") {
        const response = await authApi.post("/api/auth/password-reset/request", { email });
        setMode("reset-confirm");
        setStatus(response.data.message);
      } else if (mode === "reset-confirm") {
        const response = await authApi.post("/api/auth/password-reset/confirm", {
          email,
          code,
          new_password: newPassword,
        });
        setMode("login");
        setPassword("");
        setNewPassword("");
        setCode("");
        setStatus(response.data.message || "Пароль изменён. Войдите с новым паролем.");
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message || "Ошибка. Проверьте соединение с сервером.";
      setError(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (nextMode: Mode) => {
    setMode(nextMode);
    setError(null);
    setStatus(null);
    setCode("");
  };

  const isRegistration = mode === "register";
  const isLogin = mode === "login";
  const isVerification = mode === "verify-registration";
  const isResetRequest = mode === "reset-request";
  const isResetConfirm = mode === "reset-confirm";
  const fieldClass =
    "w-full border-2 border-black bg-white px-4 py-3 font-bold focus:outline-none focus:bg-[#ffd500]/20";

  const title = isLogin
    ? "Вход в аккаунт"
    : isRegistration
    ? "Создать аккаунт"
    : isVerification
    ? "Подтвердите почту"
    : isResetRequest
    ? "Сброс пароля"
    : "Новый пароль";

  return (
    <main className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] p-2 sm:p-4 md:p-6 text-[#111] relative overflow-hidden flex flex-col">
      <Star className="absolute w-6 h-6 text-white/80 top-[5%] left-[4%] animate-pulse" />
      <Star className="absolute w-4 h-4 text-white/70 top-[14%] right-[7%] animate-pulse" />
      <Star className="absolute w-5 h-5 text-white/80 bottom-[12%] left-[9%] animate-pulse" />
      <Star className="absolute w-7 h-7 text-[#ffd500] bottom-[6%] right-[5%] animate-pulse" />

      <div className="relative max-w-[560px] w-full mx-auto my-auto border-2 border-black bg-[#f4f4f0] flex-1 flex flex-col">
        <div className="grid grid-cols-[auto_1fr_auto] border-b-2 border-black">
          <div className="px-4 py-4 border-r-2 border-black font-display text-2xl">
            FANTASY<span className="text-[#ff4b26]">.</span>
          </div>
          <div className="hidden sm:flex items-center px-4 border-r-2 border-black text-[10px] font-bold tracking-widest uppercase leading-relaxed">
            Endurance Fantasy League
          </div>
          <div className="bg-[#ffd500] px-4 py-4 text-[10px] font-bold tracking-widest uppercase flex items-center">
            Season 001
          </div>
        </div>

        <div className="relative">
          <Sticker className="-top-3 left-6 bg-[#f6b8d0] text-black rotate-[-3deg]">Рады видеть</Sticker>
          <Sticker className="-top-3 right-6 bg-[#5866f2] text-white rotate-[3deg]">Защита аккаунта</Sticker>
        </div>

        <div className="p-5 md:p-8 border-b-2 border-black">
          <p className="text-[10px] font-bold tracking-widest uppercase text-[#666]">Endurance Fantasy League</p>
          <h1 className="font-display uppercase leading-[0.88] text-4xl md:text-5xl mt-2">{title}</h1>
        </div>

        {((isLogin || isRegistration) && (
          <div className="grid grid-cols-2 border-b-2 border-black">
            <button
              type="button"
              onClick={() => switchMode("login")}
              className={isLogin ? "px-4 py-3 text-[10px] font-bold tracking-widest uppercase border-r-2 border-black bg-black text-white" : "px-4 py-3 text-[10px] font-bold tracking-widest uppercase border-r-2 border-black hover:bg-black/5"}
            >
              Вход
            </button>
            <button
              type="button"
              onClick={() => switchMode("register")}
              className={isRegistration ? "px-4 py-3 text-[10px] font-bold tracking-widest uppercase bg-black text-white" : "px-4 py-3 text-[10px] font-bold tracking-widest uppercase hover:bg-black/5"}
            >
              Регистрация
            </button>
          </div>
        )) || null}

        <form onSubmit={handleSubmit} className="p-5 md:p-8 space-y-4">
          {(isLogin || isRegistration) && (
            <label className="block text-[10px] font-bold tracking-widest uppercase text-[#666]">
              Имя пользователя
              <input
                type="text"
                required
                minLength={3}
                maxLength={32}
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
                placeholder="имя_пользователя"
                className={fieldClass + " mt-2"}
              />
            </label>
          )}

          {(isRegistration || isVerification || isResetRequest || isResetConfirm) && (
            <label className="block text-[10px] font-bold tracking-widest uppercase text-[#666]">
              Электронная почта
              <input
                type="email"
                required
                maxLength={320}
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                className={fieldClass + " mt-2"}
              />
            </label>
          )}

          {isRegistration && (
            <label className="block text-[10px] font-bold tracking-widest uppercase text-[#666]">
              Имя для профиля
              <input
                type="text"
                required
                minLength={2}
                maxLength={50}
                autoComplete="name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="Как вас показывать в рейтинге"
                className={fieldClass + " mt-2"}
              />
            </label>
          )}

          {(isLogin || isRegistration) && (
            <label className="block text-[10px] font-bold tracking-widest uppercase text-[#666]">
              Пароль
              <input
                type="password"
                required
                minLength={isLogin ? 1 : 6}
                maxLength={128}
                autoComplete={isLogin ? "current-password" : "new-password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Не менее 6 символов"
                className={fieldClass + " mt-2"}
              />
            </label>
          )}

          {(isVerification || isResetConfirm) && (
            <label className="block text-[10px] font-bold tracking-widest uppercase text-[#666]">
              Код из письма
              <input
                type="text"
                required
                inputMode="numeric"
                autoComplete="one-time-code"
                minLength={6}
                maxLength={6}
                pattern="[0-9]{6}"
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="123456"
                className={fieldClass + " mt-2"}
              />
            </label>
          )}

          {isResetConfirm && (
            <label className="block text-[10px] font-bold tracking-widest uppercase text-[#666]">
              Новый пароль
              <input
                type="password"
                required
                minLength={6}
                maxLength={128}
                autoComplete="new-password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                placeholder="Не менее 6 символов"
                className={fieldClass + " mt-2"}
              />
            </label>
          )}

          {isRegistration && (
            <div className="border-2 border-black bg-white p-4 space-y-3">
              <label className="flex items-start gap-3 text-sm leading-relaxed">
                <input
                  type="checkbox"
                  required
                  checked={privacyConsent}
                  onChange={(event) => setPrivacyConsent(event.target.checked)}
                  className="mt-1 h-4 w-4 shrink-0 accent-[#5866f2]"
                />
                <span>
                  Я согласен с политикой обработки данных: сервис хранит тренировочные данные, пульс, нагрузку, сон и зашифрованный API-ключ Intervals.icu.{" "}
                  <Link href="/data-policy" target="_blank" className="font-bold text-[#5866f2] underline">
                    Подробнее
                  </Link>
                </span>
              </label>
            </div>
          )}

          {error && (
            <div role="alert" className="px-4 py-3 bg-[#ff4b26]/20 border-2 border-[#ff4b26] text-[#ff4b26] text-sm font-bold">
              {error}
            </div>
          )}
          {status && (
            <div role="status" className="px-4 py-3 border-2 border-[#5866f2] bg-[#5866f2]/10 text-sm font-bold">
              {status}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full px-6 py-4 bg-[#ff4b26] text-white font-display uppercase text-xl tracking-wide hover:bg-black transition-colors disabled:opacity-50"
          >
            {loading ? "Обработка..." : isLogin ? "Войти →" : isRegistration ? "Создать аккаунт →" : isVerification ? "Подтвердить и войти →" : isResetRequest ? "Отправить код →" : "Сменить пароль →"}
          </button>

          {isLogin && (
            <button type="button" onClick={() => switchMode("reset-request")} className="block w-full text-center text-xs font-bold text-[#5866f2] underline">
              Забыли пароль?
            </button>
          )}
          {!isLogin && !isRegistration && (
            <button
              type="button"
              onClick={() => switchMode("login")}
              className="block w-full text-center text-xs font-bold text-[#5866f2] underline"
            >
              Вернуться ко входу
            </button>
          )}
          {isRegistration && (
            <p className="text-xs text-[#666] text-center">
              Уже есть аккаунт? Выберите вкладку «Вход».
            </p>
          )}
          {isVerification && (
            <p className="text-xs text-[#666] text-center">
              Проверьте папки «Спам» и «Промоакции». Код действует 10 минут.
            </p>
          )}
          {isResetConfirm && (
            <p className="text-xs text-[#666] text-center">
              Если письмо не пришло, проверьте папку «Спам» или запросите код ещё раз.
            </p>
          )}
        </form>
      </div>
    </main>
  );
}
