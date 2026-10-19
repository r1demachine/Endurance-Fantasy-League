"use client";

import { useEffect, useState, type FormEvent } from "react";
import { authApi, isAuthenticated } from "@/lib/auth";

type SocialState = {
  likes_count: number;
  liked_by_me: boolean;
  comments_count: number;
};

type ActivityComment = {
  id: number;
  user_id: number;
  author: string;
  username: string | null;
  body: string;
  created_at: string | null;
  can_delete: boolean;
};

function formatCommentDate(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ActivitySocial({ activityId }: { activityId: number }) {
  const [social, setSocial] = useState<SocialState | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [comments, setComments] = useState<ActivityComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [submittingComment, setSubmittingComment] = useState(false);
  const [deletingCommentId, setDeletingCommentId] = useState<number | null>(null);
  const [commentError, setCommentError] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      authApi.get(`/api/activities/${activityId}/social`),
      authApi.get(`/api/activities/${activityId}/comments`, { params: { limit: 30 } }),
    ])
      .then(([socialResponse, commentsResponse]) => {
        if (cancelled) return;
        setSocial({
          likes_count: Math.max(0, Number(socialResponse.data.likes_count) || 0),
          liked_by_me: Boolean(socialResponse.data.liked_by_me),
          comments_count: Math.max(0, Number(socialResponse.data.comments_count) || 0),
        });
        setComments(Array.isArray(commentsResponse.data.comments) ? commentsResponse.data.comments : []);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Не удалось загрузить реакции и комментарии.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setCommentsLoading(false);
        }
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
      setSocial((current) => current ? {
        ...current,
        likes_count: Math.max(0, Number(response.data.likes_count) || 0),
        liked_by_me: Boolean(response.data.liked_by_me ?? response.data.liked),
      } : current);
    } catch {
      setError("Не удалось изменить реакцию. Проверь доступ к тренировке и повтори попытку.");
    } finally {
      setPending(false);
    }
  };

  const submitComment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body = draft.trim();
    if (!body || submittingComment || !isAuthenticated()) return;
    if (body.length > 500) {
      setCommentError("Комментарий не может быть длиннее 500 символов.");
      return;
    }
    if (/[\u0000-\u001F\u007F-\u009F]/.test(body)) {
      setCommentError("Комментарий не должен содержать управляющие символы.");
      return;
    }

    setSubmittingComment(true);
    setCommentError("");
    try {
      const response = await authApi.post(`/api/activities/${activityId}/comments`, { body });
      const created = response.data.comment as ActivityComment;
      setComments((current) => [created, ...current.filter((item) => item.id !== created.id)].slice(0, 30));
      setSocial((current) => current ? {
        ...current,
        comments_count: Math.max(0, Number(response.data.comments_count) || 0),
      } : current);
      setDraft("");
    } catch (requestError: unknown) {
      const detail = (requestError as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setCommentError(typeof detail === "string" ? detail : "Не удалось отправить комментарий.");
    } finally {
      setSubmittingComment(false);
    }
  };

  const deleteComment = async (commentId: number) => {
    if (deletingCommentId !== null) return;
    setDeletingCommentId(commentId);
    setCommentError("");
    try {
      await authApi.delete(`/api/comments/${commentId}`);
      setComments((current) => current.filter((item) => item.id !== commentId));
      setSocial((current) => current ? {
        ...current,
        comments_count: Math.max(0, current.comments_count - 1),
      } : current);
    } catch {
      setCommentError("Не удалось удалить комментарий.");
    } finally {
      setDeletingCommentId(null);
    }
  };

  return (
    <section className="space-y-3 border-t-2 border-black/15 pt-3" aria-label="Реакции и комментарии к тренировке">
      <div className="flex flex-wrap items-center gap-3">
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
        <p className="text-xs font-bold text-[#555]">💬 {loading ? "…" : social?.comments_count ?? 0} комментариев</p>
      </div>

      {error && <p role="status" className="text-xs font-semibold text-[#b91c1c]">{error}</p>}

      <div className="space-y-3">
        <h3 className="font-display text-sm uppercase">Комментарии</h3>
        {isAuthenticated() ? (
          <form onSubmit={(event) => void submitComment(event)} className="flex items-start gap-2">
            <label className="sr-only" htmlFor={`activity-comment-${activityId}`}>Новый комментарий</label>
            <input
              id={`activity-comment-${activityId}`}
              type="text"
              value={draft}
              maxLength={500}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Написать комментарий…"
              className="min-w-0 flex-1 border-2 border-black bg-white px-3 py-2 text-sm outline-none focus:border-[#5866f2]"
              disabled={submittingComment}
            />
            <button
              type="submit"
              disabled={submittingComment || !draft.trim()}
              className="min-h-10 border-2 border-black bg-[#ffd500] px-3 text-xs font-black uppercase hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submittingComment ? "…" : "Отправить"}
            </button>
          </form>
        ) : (
          <p className="text-xs text-[#555]">Войдите, чтобы оставить комментарий.</p>
        )}

        {commentError && <p role="status" className="text-xs font-semibold text-[#b91c1c]">{commentError}</p>}

        {commentsLoading ? (
          <p className="text-xs text-[#666]">Загружаем комментарии…</p>
        ) : comments.length === 0 ? (
          <p className="text-xs text-[#666]">Пока нет комментариев.</p>
        ) : (
          <ul className="space-y-2">
            {comments.map((comment) => (
              <li key={comment.id} className="border-2 border-black/15 bg-white p-3">
                <div className="flex items-start justify-between gap-3">
                  <p className="min-w-0 break-words text-xs font-black">{comment.author}</p>
                  <time className="shrink-0 text-[10px] text-[#666]">{formatCommentDate(comment.created_at)}</time>
                </div>
                <p className="mt-1 whitespace-pre-wrap break-words text-sm">{comment.body}</p>
                {comment.can_delete && (
                  <button
                    type="button"
                    onClick={() => void deleteComment(comment.id)}
                    disabled={deletingCommentId !== null}
                    className="mt-2 text-[10px] font-bold uppercase tracking-wide text-[#b91c1c] underline underline-offset-2 disabled:opacity-50"
                  >
                    {deletingCommentId === comment.id ? "Удаление…" : "Удалить"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {comments.length >= 30 && (
          <p className="text-[10px] text-[#666]">Показаны последние 30 комментариев.</p>
        )}
      </div>
    </section>
  );
}
