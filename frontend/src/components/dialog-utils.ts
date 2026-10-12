export function getApiErrorMessage(error: unknown, fallback: string): string {
  const detail = error && typeof error === "object"
    ? (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    : undefined;
  return typeof detail === "string" && detail.trim().length > 0 ? detail : fallback;
}

export function parsePauseWeeks(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isInteger(value) && value >= 0 && value <= 8 ? value : null;
  }
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  if (!/^(0|[1-8])$/.test(normalized)) return null;
  return Number(normalized);
}

export function isConfirmDialogValid(values: {
  confirmation?: string;
  password?: string;
  requireDelete?: boolean;
  requirePassword?: boolean;
}): boolean {
  const { confirmation = "", password = "", requireDelete = false, requirePassword = false } = values;
  return (!requireDelete || confirmation.trim() === "DELETE") &&
    (!requirePassword || password.trim().length > 0);
}

export async function submitConfirmPayload(
  values: { confirmation?: string; password?: string },
  requirements: { requireDelete?: boolean; requirePassword?: boolean },
  onConfirm: (payload: { confirmation: string; password: string }) => void | Promise<void>,
): Promise<boolean> {
  const payload = buildConfirmPayload(values, requirements);
  if (!payload) return false;
  await onConfirm(payload);
  return true;
}

export function buildConfirmPayload(
  values: { confirmation?: string; password?: string },
  requirements: { requireDelete?: boolean; requirePassword?: boolean } = {},
): { confirmation: string; password: string } | null {
  const confirmation = values.confirmation ?? "";
  const password = values.password ?? "";
  if (!isConfirmDialogValid({ confirmation, password, ...requirements })) return null;
  return {
    confirmation: requirements.requireDelete ? confirmation.trim() : "",
    password: requirements.requirePassword ? password : "",
  };
}

export function parsePauseDate(value: string | null): Date | null {
  if (typeof value !== "string" || !value.trim()) return null;
  // API timestamps from SQLAlchemy can be naive UTC strings without "Z".
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value);
  const date = new Date(hasZone ? value : value + "Z");
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatPauseDate(value: string | null, locale = "ru-RU"): string {
  const date = parsePauseDate(value);
  if (!date) return "дата не указана";
  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function shouldCloseFromBackdrop(
  isBackdropTarget: boolean,
  closeOnBackdrop: boolean,
  preventClose: boolean,
): boolean {
  return isBackdropTarget && closeOnBackdrop && !preventClose;
}

type FocusableElement = HTMLElement;
interface DialogLike {
  querySelectorAll: (selector: string) => ArrayLike<FocusableElement>;
  contains: (element: Node | null) => boolean;
  focus: () => void;
}

export function handleDialogKeyDown(
  event: { key: string; shiftKey?: boolean; preventDefault: () => void },
  options: {
    dialog: DialogLike | null | undefined;
    closeOnEscape: boolean;
    preventClose: boolean;
    onClose: () => void;
    activeElement: Node | null;
  },
): "closed" | "focused-dialog" | "focused-last" | "focused-first" | "ignored" {
  const { dialog, closeOnEscape, preventClose, onClose, activeElement } = options;
  if (event.key === "Escape" && closeOnEscape && !preventClose) {
    event.preventDefault();
    onClose();
    return "closed";
  }
  if (event.key !== "Tab" || !dialog) return "ignored";

  const selector = "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex='-1'])";
  const focusable = Array.from(dialog.querySelectorAll(selector));
  if (focusable.length === 0) {
    event.preventDefault();
    dialog.focus();
    return "focused-dialog";
  }

  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && (activeElement === first || !dialog.contains(activeElement))) {
    event.preventDefault();
    last.focus();
    return "focused-last";
  }
  if (!event.shiftKey && (activeElement === last || !dialog.contains(activeElement))) {
    event.preventDefault();
    first.focus();
    return "focused-first";
  }
  return "ignored";
}
