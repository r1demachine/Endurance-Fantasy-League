"use client";

import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { motion } from "framer-motion";
import {
  buildConfirmPayload,
  formatPauseDate,
  getApiErrorMessage,
  handleDialogKeyDown,
  parsePauseDate,
  parsePauseWeeks,
  submitConfirmPayload,
} from "./dialog-utils";

export interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  closeLabel?: string;
  closeOnBackdrop?: boolean;
  closeOnEscape?: boolean;
  preventClose?: boolean;
}

export function Modal({
  title,
  onClose,
  children,
  closeLabel = "Закрыть",
  closeOnBackdrop = true,
  closeOnEscape = true,
  preventClose = false,
}: ModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousActiveRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  const closeOnEscapeRef = useRef(closeOnEscape);
  const preventCloseRef = useRef(preventClose);

  useEffect(() => {
    onCloseRef.current = onClose;
    closeOnEscapeRef.current = closeOnEscape;
    preventCloseRef.current = preventClose;
  }, [onClose, closeOnEscape, preventClose]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    previousActiveRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    document.body.style.overflow = "hidden";

    const dialog = dialogRef.current;
    const initialFocus = dialog?.querySelector<HTMLElement>("[autofocus]")
      ?? dialog?.querySelector<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex='-1'])",
      );
    const frame = window.requestAnimationFrame(() => {
      (initialFocus ?? dialog)?.focus();
    });

    const onKeyDown = (event: KeyboardEvent) => {
      handleDialogKeyDown(event, {
        dialog,
        closeOnEscape: closeOnEscapeRef.current,
        preventClose: preventCloseRef.current,
        onClose: () => onCloseRef.current(),
        activeElement: document.activeElement,
      });
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previousActiveRef.current?.isConnected) previousActiveRef.current.focus();
    };
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget && closeOnBackdrop && !preventClose) onClose();
      }}
    >
      <motion.div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        initial={{ y: 28, scale: 0.97 }}
        animate={{ y: 0, scale: 1 }}
        exit={{ y: 28, scale: 0.97 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className="flex max-h-[80vh] w-full max-w-md flex-col border-2 border-black bg-[#f4f4f0] shadow-[6px_6px_0_rgba(0,0,0,0.45)]"
      >
        <div className="flex items-center justify-between gap-3 border-b-2 border-black bg-[#5866f2] px-4 py-3 text-white">
          <h2 id={titleId} className="font-display text-xl uppercase leading-none">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={preventClose}
            aria-label={closeLabel}
            className="border-2 border-black bg-white px-3 py-2 text-[10px] font-bold uppercase tracking-widest text-[#111] transition-colors hover:bg-black hover:text-white disabled:opacity-50"
          >
            {closeLabel}
          </button>
        </div>
        <div className="overflow-y-auto p-4">{children}</div>
      </motion.div>
    </motion.div>
  );
}

export interface ConfirmPayload {
  confirmation: string;
  password: string;
}

export interface ConfirmDialogProps {
  title: string;
  text: string;
  confirmLabel: string;
  danger?: boolean;
  busy: boolean;
  error?: string;
  requireDelete?: boolean;
  requirePassword?: boolean;
  passwordLabel?: string;
  onClose: () => void;
  onConfirm: (values: ConfirmPayload) => void | Promise<void>;
}

export function ConfirmDialog({
  title,
  text,
  confirmLabel,
  danger = true,
  busy,
  error,
  requireDelete = false,
  requirePassword = false,
  passwordLabel = "Пароль аккаунта",
  onClose,
  onConfirm,
}: ConfirmDialogProps) {
  const [confirmation, setConfirmation] = useState("");
  const [password, setPassword] = useState("");
  const [internalError, setInternalError] = useState("");

  const payload = buildConfirmPayload(
    { confirmation, password },
    { requireDelete, requirePassword },
  );

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    setInternalError("");
    try {
      await submitConfirmPayload(
        { confirmation, password },
        { requireDelete, requirePassword },
        onConfirm,
      );
    } catch (submitError) {
      setInternalError(getApiErrorMessage(submitError, "Не удалось выполнить действие. Повторите попытку."));
    }
  };

  return (
    <Modal title={title} onClose={onClose} preventClose={busy}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm leading-relaxed text-[#333]">{text}</p>
        {requireDelete && (
          <div>
            <label htmlFor="confirm-delete-word" className="mb-2 block text-[10px] font-bold uppercase tracking-widest text-[#444]">
              Введите DELETE для подтверждения
            </label>
            <input
              id="confirm-delete-word"
              type="text"
              autoComplete="off"
              autoFocus
              required
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder="DELETE"
              aria-invalid={confirmation.length > 0 && confirmation.trim() !== "DELETE"}
              className="w-full border-2 border-black bg-white px-3 py-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#5866f2]"
            />
          </div>
        )}
        {requirePassword && (
          <div>
            <label htmlFor="confirm-account-password" className="mb-2 block text-[10px] font-bold uppercase tracking-widest text-[#444]">
              {passwordLabel}
            </label>
            <input
              id="confirm-account-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full border-2 border-black bg-white px-3 py-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-[#5866f2]"
            />
          </div>
        )}
        {(error || internalError) && (
          <p role="alert" className="border-l-4 border-[#ff4b26] bg-[#ff4b26]/10 px-3 py-2 text-sm font-bold text-[#a62910]">
            {error || internalError}
          </p>
        )}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="border-2 border-black bg-white px-4 py-3 text-[10px] font-bold uppercase tracking-widest transition-colors hover:bg-black hover:text-white disabled:opacity-50"
          >
            Отмена
          </button>
          <button
            type="submit"
            disabled={busy || !payload}
            className={(danger
              ? "border-2 border-[#ff4b26] bg-[#ff4b26] text-white hover:bg-black"
              : "border-2 border-black bg-[#ffd500] text-[#111] hover:bg-black hover:text-white") +
              " px-4 py-3 text-[10px] font-bold uppercase tracking-widest transition-colors disabled:cursor-not-allowed disabled:opacity-50"}
          >
            {busy ? "Выполняется..." : confirmLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export interface PauseDialogProps {
  onClose: () => void;
  onSubmit: (weeks: number) => void | Promise<void>;
  busy: boolean;
  error?: string;
  now: number;
  pauseSetAt?: string | null;
  pausedUntil?: string | null;
}

export function PauseDialog({
  onClose,
  onSubmit,
  busy,
  error,
  now,
  pauseSetAt,
  pausedUntil,
}: PauseDialogProps) {
  const [weeks, setWeeks] = useState(1);
  const endDate = parsePauseDate(pausedUntil ?? null);
  const currentlyPaused = Boolean(endDate && endDate.getTime() > now);

  const changeWeeks = (next: number) => {
    const parsed = parsePauseWeeks(next);
    if (parsed !== null && parsed >= 1) setWeeks(parsed);
  };

  return (
    <Modal title="Пауза: болезнь / отпуск" onClose={onClose} preventClose={busy}>
      <div className="space-y-4">
        {pausedUntil && (
          <div className="border-2 border-black/20 bg-white p-3 text-sm">
            <p className="font-bold">{currentlyPaused ? "Сейчас действует пауза" : "Последняя пауза"}</p>
            {pauseSetAt && <p className="mt-1 text-[#555]">Начало: {formatPauseDate(pauseSetAt)}</p>}
            <p className="mt-1 text-[#555]">
              {currentlyPaused ? "Окончание: " : "Окончилась: "}{formatPauseDate(pausedUntil)}
            </p>
          </div>
        )}
        {!currentlyPaused && (
          <p className="text-sm text-[#444]">Выбери продолжительность от 1 до 8 недель. Поставить паузу можно при болезни или отпуске.</p>
        )}
        <div className="border-2 border-black bg-white p-4">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-[#666]">Продолжительность</p>
          <div className="flex items-center justify-center gap-5">
            <button
              type="button"
              aria-label="Уменьшить срок паузы"
              onClick={() => changeWeeks(weeks - 1)}
              disabled={busy || weeks <= 1}
              className="h-11 w-11 border-2 border-black text-xl font-bold hover:bg-[#ffd500] disabled:opacity-30"
            >
              −
            </button>
            <p aria-live="polite" className="min-w-28 text-center font-display text-3xl">
              {weeks} {weeks === 1 ? "неделя" : weeks >= 2 && weeks <= 4 ? "недели" : "недель"}
            </p>
            <button
              type="button"
              aria-label="Увеличить срок паузы"
              onClick={() => changeWeeks(weeks + 1)}
              disabled={busy || weeks >= 8}
              className="h-11 w-11 border-2 border-black text-xl font-bold hover:bg-[#ffd500] disabled:opacity-30"
            >
              +
            </button>
          </div>
        </div>
        {error && <p role="alert" className="border-l-4 border-[#ff4b26] bg-[#ff4b26]/10 px-3 py-2 text-sm font-bold text-[#a62910]">{error}</p>}
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-between">
          <button
            type="button"
            onClick={() => onSubmit(0)}
            disabled={busy || !currentlyPaused}
            className="border-2 border-[#ff4b26] px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-[#ff4b26] transition-colors hover:bg-[#ff4b26] hover:text-white disabled:opacity-40"
          >
            {busy ? "Сохраняю..." : "Снять паузу"}
          </button>
          <div className="flex flex-col-reverse gap-2 sm:flex-row">
            <button type="button" onClick={onClose} disabled={busy} className="border-2 border-black bg-white px-4 py-3 text-[10px] font-bold uppercase tracking-widest hover:bg-black hover:text-white disabled:opacity-50">
              Отмена
            </button>
            <button type="button" onClick={() => onSubmit(weeks)} disabled={busy} className="border-2 border-black bg-[#ffd500] px-4 py-3 text-[10px] font-bold uppercase tracking-widest hover:bg-black hover:text-white disabled:opacity-50">
              {busy ? "Сохраняю..." : "Поставить паузу"}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
