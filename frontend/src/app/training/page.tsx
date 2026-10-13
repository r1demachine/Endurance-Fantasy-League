"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function TrainingPage() {
  const router = useRouter();

  useEffect(() => {
    const tab = new URLSearchParams(window.location.search).get("tab");
    router.replace(tab === "sources" ? "/profile?settings=sources" : "/dashboard");
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-[#171a38] via-[#2a2f6b] to-[#5866f2] px-4 text-white">
      <p className="font-display text-xl uppercase">Перенаправление…</p>
    </main>
  );
}
