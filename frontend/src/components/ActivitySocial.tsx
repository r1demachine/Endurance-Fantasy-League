"use client";

import { useEffect, useState } from "react";
import { authApi, isAuthenticated } from "@/lib/auth";

type SocialState = {
  likes_count: number;
  liked_by_me: boolean;
};

export default function ActivitySocial({ activityId }: { activityId: number }) {
  const [social, setSocial] = useState<SocialState | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    authApi.get(`/api/activities/${activityId}/social`)
      .then((response) => {
        if (cancelled) return;
        setSocial({
          likes_count: Math.max(0, Number(response.data.likes_count) || 0),
          liked_by_me: Boolean(response.data.liked_by_me),
        });
      })
      .catch(() => {
        if (!cancelled) setError("Не удалось загрузить реакции.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activityId]);

  const toggleLike = async () => {
    if (!social || pending || !isAuthenticated()) return;
    setPending(true);
    setError("");
    try {
      const response = await authApi.put(`/api/activities/${activityId}/reaction`);
      setSocial({
        likes_count: Math.max(0, Number(response.data.likes_count) || 0),
        liked_by_me: Boolean(response.data.liked_by_me ?? response.data.liked),
      });
    } catch {
      setError("Не удалось изменить реакцию. Проверь доступ к тренировке и повтори попытку.");
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => void toggleLike()}
        disabled={loading || pending || !social || !isAuthenticated()}
        aria-pressed={Boolean(social?.liked_by_me)}
        aria-label={social?.liked_by_me ? "Убрать отметку «Нравится»" : "Нравится"}
        className={`inline-flex min-h-9 items-center gap-2 border-2 border-black px-3 py-1.5 text-sm font-bold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2] disabled:cursor-wait disabled:opacity-50 ${
          social?.liked_by_me ? "bg-[#ff4b26] text-white" : "bg-white text-[#111] hover:bg-[#ffd500]"
        }`}
      >
        <span aria-hidden="true" className="text-lg leading-none">♥</span>
        <span>{loading ? "…" : social?.likes_count ?? 0}</span>
      </button>
      {error && <p role="status" className="text-xs font-semibold text-[#b91c1c]">{error}</p>}
    </div>
  );
}
