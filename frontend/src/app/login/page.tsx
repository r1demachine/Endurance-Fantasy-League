"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { authApi, setToken } from "@/lib/auth";
import { Star, Sticker } from "@/components/DreamBits";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const endpoint = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const payload =
        mode === "login"
          ? { username, password }
          : { username, password, display_name: displayName || username };

      const res = await authApi.post(endpoint, payload);
      setToken(res.data.access_token, res.data.user);
      router.push("/profile");
    } catch (err: any) {
      const msg =
        err.response?.data?.detail ||
        err.message ||
        "Ошибка. Проверь сервер.";
      setError(typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (m: Mode) => {
    setMode(m);
    setError(null);
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] p-2 sm:p-4 md:p-6 text-[#111] relative overflow-hidden flex flex-col">
      {/* ✦ Звёзды */}
      <Star className="absolute w-6 h-6 text-white/80 top-[5%] left-[4%] animate-pulse" />
      <Star className="absolute w-4 h-4 text-white/70 top-[14%] right-[7%] animate-pulse" />
      <Star className="absolute w-5 h-5 text-white/80 bottom-[12%] left-[9%] animate-pulse" />
      <Star className="absolute w-7 h-7 text-[#ffd500] bottom-[6%] right-[5%] animate-pulse" />

      <div className="relative max-w-[560px] w-full mx-auto my-auto border-2 border-black bg-[#f4f4f0] flex-1 flex flex-col">
        {/* Верхняя панель */}
        <div className="grid grid-cols-[auto_1fr_auto] border-b-2 border-black">
          <div className="px-4 py-4 border-r-2 border-black font-display text-2xl">
            FANTASY<span className="text-[#ff4b26]">.</span>
          </div>
          <div className="hidden sm:flex items-center px-4 border-r-2 border-black text-[10px] font-bold tracking-widest uppercase leading-relaxed">
            RideMachine CC<br />Athlete login
          </div>
          <div className="bg-[#ffd500] px-4 py-4 text-[10px] font-bold tracking-widest uppercase flex items-center">
            Season 001
          </div>
        </div>

        {/* Стикеры */}
        <div className="relative">
          <Sticker className="-top-3 left-6 bg-[#f6b8d0] text-black rotate-[-3deg]">welcome back</Sticker>
          <Sticker className="-top-3 right-6 bg-[#5866f2] text-white rotate-[3deg]">no bots 🙅</Sticker>
        </div>

        {/* Заголовок */}
        <div className="p-5 md:p-8 border-b-2 border-black">
          <p className="text-[10px] font-bold tracking-widest uppercase text-[#666]">
            {mode === "login" ? "Sign in" : "Create account"}
          </p>
          <h1 className="font-display uppercase leading-[0.88] text-4xl md:text-5xl mt-2">
            {mode === "login" ? (
              <>Ride<span className="text-[#5866f2]">.</span><br />harder<span className="text-[#ff4b26]">.</span></>
            ) : (
              <>Join the<br />club<span className="text-[#ff4b26]">.</span></>
            )}
          </h1>
        </div>

        {/* Табы */}
        <div className="grid grid-cols-2 border-b-2 border-black">
          <button
            onClick={() => switchMode("login")}
            className={`px-4 py-3 text-[10px] font-bold tracking-widest uppercase border-r-2 border-black transition-colors ${
              mode === "login" ? "bg-black text-white" : "hover:bg-black/5"
            }`}
          >
            Login
          </button>
          <button
            onClick={() => switchMode("register")}
            className={`px-4 py-3 text-[10px] font-bold tracking-widest uppercase transition-colors ${
              mode === "register" ? "bg-black text-white" : "hover:bg-black/5"
            }`}
          >
            Register
          </button>
        </div>

        {/* Форма */}
        <form onSubmit={handleSubmit} className="p-5 md:p-8 space-y-4">
          <div>
            <label className="block text-[9px] font-bold tracking-widest uppercase text-[#666] mb-2">
              Username
            </label>
            <input
              type="text"
              required
              minLength={3}
              maxLength={32}
              value={username}
              onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
              placeholder="ridemachine"
              className="w-full px-4 py-3 bg-white border-2 border-black font-bold focus:outline-none focus:bg-[#ffd500]/20 transition-colors"
            />
          </div>

          {mode === "register" && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
            >
              <label className="block text-[9px] font-bold tracking-widest uppercase text-[#666] mb-2">
                Display name (for leaderboard)
              </label>
              <input
                type="text"
                required
                minLength={2}
                maxLength={50}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="RideMachine CC"
                className="w-full px-4 py-3 bg-white border-2 border-black font-bold focus:outline-none focus:bg-[#ffd500]/20 transition-colors"
              />
            </motion.div>
          )}

          <div>
            <label className="block text-[9px] font-bold tracking-widest uppercase text-[#666] mb-2">
              Password
            </label>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-4 py-3 bg-white border-2 border-black font-bold focus:outline-none focus:bg-[#ffd500]/20 transition-colors"
            />
          </div>

          {error && (
            <div className="px-4 py-3 bg-[#ff4b26]/20 border-2 border-[#ff4b26] text-[#ff4b26] text-sm font-bold">
              ⚠ {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full px-6 py-4 bg-[#ff4b26] text-white font-display uppercase text-xl tracking-wide hover:bg-black transition-colors disabled:opacity-50"
          >
            {loading
              ? "..."
              : mode === "login"
              ? "Enter the club →"
              : "Join RideMachine →"}
          </button>

          <p className="text-[10px] text-[#666] text-center uppercase tracking-widest font-bold pt-2 border-t border-black/10">
            {mode === "login"
              ? "Нет аккаунта? Переключись на Register"
              : "Уже с нами? Переключись на Login"}
          </p>
        </form>
      </div>
    </main>
  );
}