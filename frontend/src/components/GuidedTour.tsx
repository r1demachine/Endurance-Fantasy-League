"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { usePathname, useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";

type TourStep = {
  href: string;
  target: string;
  title: string;
  description: string;
  nextLabel?: string;
};

type Highlight = {
  left: number;
  top: number;
  width: number;
  height: number;
  viewportWidth: number;
  viewportHeight: number;
};

type PanelPosition = { left: number; top: number };

const TOUR_STEPS: TourStep[] = [
  {
    href: "/",
    target: "home-globe",
    title: "Добро пожаловать в FANTASY",
    description: "Это короткая экскурсия по Endurance Fantasy League. Покажу, где смотреть свой прогресс, достижения, соревнования и как подключить Intervals.icu.",
    nextLabel: "Начать",
  },
  {
    href: "/dashboard",
    target: "dashboard-level",
    title: "Уровень и XP",
    description: "За тренировки и игровые достижения начисляется XP. Накопленный опыт повышает уровень — здесь видно текущий уровень и прогресс до следующего.",
  },
  {
    href: "/dashboard",
    target: "dashboard-streak",
    title: "Стрик — серия активности",
    description: "Здесь отображаются дни и недели подряд с активностью. Регулярность помогает поддерживать серию и получать награды.",
  },
  {
    href: "/dashboard",
    target: "dashboard-week-goal",
    title: "Цель на неделю",
    description: "Этот блок показывает, сколько часов уже набрано относительно недельной цели. Выполняй её в своём темпе и следи за прогрессом.",
  },
  {
    href: "/dashboard",
    target: "dashboard-year-chart",
    title: "Год по неделям",
    description: "График помогает быстро увидеть тренировочную историю за год и выбрать неделю для подробного просмотра. Прокручивай страницу — подсветка будет следовать за блоком.",
  },
  {
    href: "/dashboard",
    target: "dashboard-week-summary",
    title: "Твоя неделя",
    description: "В недельной сводке собраны нагрузка, выполнение цели и разбивка XP: за нагрузку, регулярность, качество, восстановление и достижения. Здесь же доступны пауза и разгрузочная неделя.",
  },
  {
    href: "/dashboard",
    target: "dashboard-achievements",
    title: "Достижения",
    description: "Здесь собраны недельные и долгосрочные достижения. Смотри условия и прогресс при наведении на карточку, а за выполненные задания получай дополнительные награды.",
  },
  {
    href: "/dashboard",
    target: "dashboard-workouts",
    title: "Список тренировок",
    description: "Выбирай неделю и раскрывай тренировку, чтобы посмотреть её вклад в XP и отдельные награды. Здесь же можно перейти к подключению источников или загрузить тренировку.",
  },
  {
    href: "/compete?tab=rating",
    target: "compete-weekly-league",
    title: "Weekly League",
    description: "Недельная лига распределяет участников по дивизионам. Сравнивай свой League Score с другими участниками и следи за позицией в текущей неделе.",
  },
  {
    href: "/compete?tab=rating",
    target: "compete-overall-rating",
    title: "Общий рейтинг",
    description: "В рейтинге можно посмотреть таблицу всех участников или переключиться на рейтинг друзей. В соревнованиях также доступны дуэли и командные разделы.",
  },
  {
    href: "/profile",
    target: "profile-header",
    title: "Профиль атлета",
    description: "В профиле находятся основные данные спортсмена, статистика, настройки аккаунта и управление подключёнными источниками.",
  },
  {
    href: "/profile?settings=sources",
    target: "profile-intervals-source",
    title: "Подключи Intervals.icu",
    description: "Открой строку Intervals.icu и введи ID спортсмена и API-ключ. После подключения синхронизируй историю тренировок — данные появятся на дашборде и будут участвовать в расчёте XP.",
    nextLabel: "Завершить",
  },
];

function getTourStorageKey(): string {
  if (typeof window === "undefined") return "efl_tour_seen_v1:default";
  let identity = "default";
  try {
    const rawUser = localStorage.getItem("fl_user");
    const rawCache = localStorage.getItem("fl_user_cache");
    const parsedUser = rawUser ? JSON.parse(rawUser) : null;
    const parsedCache = rawCache ? JSON.parse(rawCache) : null;
    identity =
      parsedUser?.username ||
      parsedUser?.id ||
      parsedCache?.user?.username ||
      parsedCache?.user?.id ||
      "default";
  } catch {
    identity = "default";
  }
  return `efl_tour_seen_v1:${String(identity)}`;
}

function markTourSeen(): void {
  if (!isAuthenticated() || typeof window === "undefined") return;
  try {
    localStorage.setItem(getTourStorageKey(), "1");
  } catch {
    // The tour remains usable when browser storage is disabled.
  }
}

function hasSeenTour(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return localStorage.getItem(getTourStorageKey()) === "1";
  } catch {
    return false;
  }
}

function isSameDestination(href: string): boolean {
  if (typeof window === "undefined") return false;
  return `${window.location.pathname}${window.location.search}` === href;
}

export default function GuidedTour() {
  const pathname = usePathname();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [active, setActive] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [panelPosition, setPanelPosition] = useState<PanelPosition>({ left: 16, top: 16 });
  const targetRef = useRef<HTMLElement | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const autoRedirectStarted = useRef(false);
  const autoTourHandled = useRef(false);
  const autoStartPending = useRef(false);
  const lastTargetPathname = useRef<string | null>(null);
  const step = TOUR_STEPS[stepIndex];
  const hasHighlight = highlight !== null;

  const startTour = useCallback(() => {
    if (isAuthenticated()) {
      markTourSeen();
      autoTourHandled.current = true;
      autoStartPending.current = false;
    }
    setStepIndex(0);
    setHighlight(null);
    setActive(true);
    if (typeof window !== "undefined" && window.location.pathname !== "/") {
      router.push("/", { scroll: false });
    }
  }, [router]);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const onStartTour = () => startTour();
    window.addEventListener("efl:start-guided-tour", onStartTour);
    return () => window.removeEventListener("efl:start-guided-tour", onStartTour);
  }, [startTour]);

  // Start onboarding once per account. New users are taken to the home page first.
  useEffect(() => {
    if (!mounted || active || !isAuthenticated()) return;

    if (hasSeenTour()) {
      autoTourHandled.current = true;
      autoStartPending.current = false;
      return;
    }

    if (autoTourHandled.current) {
      if (autoStartPending.current && pathname === "/") {
        autoStartPending.current = false;
        markTourSeen();
        setStepIndex(0);
        setHighlight(null);
        setActive(true);
      }
      return;
    }

    if (pathname === "/") {
      autoTourHandled.current = true;
      markTourSeen();
      setStepIndex(0);
      setHighlight(null);
      setActive(true);
      autoRedirectStarted.current = false;
      return;
    }

    if (pathname !== "/login" && !autoRedirectStarted.current) {
      autoRedirectStarted.current = true;
      autoTourHandled.current = true;
      autoStartPending.current = true;
      router.replace("/", { scroll: false });
    }
  }, [active, mounted, pathname, router]);

  useEffect(() => {
    if (!active || !hasHighlight) return;

    const focusTimer = window.setTimeout(() => {
      panelRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    }, 0);
    const handleKeyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        markTourSeen();
        setActive(false);
        setHighlight(null);
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = panelRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)");
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const currentIndex = Array.from(focusable).indexOf(document.activeElement as HTMLButtonElement);
      if (currentIndex < 0) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && currentIndex === 0) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && currentIndex === focusable.length - 1) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyboard);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", handleKeyboard);
    };
  }, [active, hasHighlight]);

  useEffect(() => {
    if (!active || !step) {
      setHighlight(null);
      targetRef.current = null;
      return;
    }

    const expectedPathname = step.href.split("?")[0];
    if (pathname !== expectedPathname) {
      setHighlight(null);
      return;
    }

    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let transitionFallbackTimer: number | null = null;
    let animationFrame = 0;
    let target: HTMLElement | null = null;

    const positionOverlay = () => {
      if (!target || !target.isConnected) return;
      const rect = target.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const padding = 8;
      const left = Math.max(0, rect.left - padding);
      const top = Math.max(0, rect.top - padding);
      const right = Math.min(viewportWidth, rect.right + padding);
      const bottom = Math.min(viewportHeight, rect.bottom + padding);
      setHighlight({
        left,
        top,
        width: Math.max(0, right - left),
        height: Math.max(0, bottom - top),
        viewportWidth,
        viewportHeight,
      });

      const panelWidth = Math.min(360, viewportWidth - 24);
      const panelHeight = panelRef.current?.getBoundingClientRect().height ?? 220;
      const gap = 16;
      let panelLeft: number;
      let panelTop: number;

      if (rect.right + gap + panelWidth <= viewportWidth - 12) {
        panelLeft = rect.right + gap;
      } else if (rect.left - gap - panelWidth >= 12) {
        panelLeft = rect.left - gap - panelWidth;
      } else {
        panelLeft = Math.max(12, (viewportWidth - panelWidth) / 2);
      }

      const roomBelow = viewportHeight - (rect.bottom + gap);
      const roomAbove = rect.top - gap;
      if (roomBelow >= panelHeight || roomBelow >= roomAbove) {
        panelTop = Math.min(viewportHeight - panelHeight - 12, rect.bottom + gap);
      } else {
        panelTop = Math.max(12, rect.top - panelHeight - gap);
      }
      panelTop = Math.max(12, Math.min(panelTop, viewportHeight - panelHeight - 12));
      panelLeft = Math.max(12, Math.min(panelLeft, viewportWidth - panelWidth - 12));
      setPanelPosition({ left: panelLeft, top: panelTop });
    };

    const schedulePosition = () => {
      if (animationFrame) return;
      animationFrame = window.requestAnimationFrame(() => {
        animationFrame = 0;
        positionOverlay();
      });
    };

    const findTarget = (attempt: number) => {
      if (cancelled) return;
      const found = document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`);
      if (!found) {
        if (attempt < 50) retryTimer = setTimeout(() => findTarget(attempt + 1), 100);
        return;
      }

      target = found;
      targetRef.current = found;
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      found.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center", inline: "nearest" });
      positionOverlay();

      window.addEventListener("scroll", schedulePosition, true);
      window.addEventListener("resize", schedulePosition);
      window.visualViewport?.addEventListener("resize", schedulePosition);
      window.visualViewport?.addEventListener("scroll", schedulePosition);
    };

    const previousTargetPathname = lastTargetPathname.current;
    const waitForTransition = previousTargetPathname !== null && previousTargetPathname !== pathname;
    lastTargetPathname.current = pathname;

    let targetSearchStarted = false;
    const startTargetSearch = () => {
      if (cancelled || targetSearchStarted) return;
      targetSearchStarted = true;
      if (transitionFallbackTimer) window.clearTimeout(transitionFallbackTimer);
      window.removeEventListener("efl:page-transition-complete", onPageTransitionComplete);
      findTarget(0);
    };
    const onPageTransitionComplete = (event: Event) => {
      const transitionPathname = (event as CustomEvent<{ pathname?: string }>).detail?.pathname;
      // Ignore the outgoing page's exit animation; the new page must finish entering first.
      if (transitionPathname && transitionPathname !== pathname) return;
      startTargetSearch();
    };

    if (waitForTransition) {
      window.addEventListener("efl:page-transition-complete", onPageTransitionComplete);
      // Safety fallback in case a transition callback is skipped by reduced motion or an interrupted route change.
      transitionFallbackTimer = window.setTimeout(startTargetSearch, 1800);
    } else {
      startTargetSearch();
    }

    return () => {
      cancelled = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      if (transitionFallbackTimer) window.clearTimeout(transitionFallbackTimer);
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      window.removeEventListener("efl:page-transition-complete", onPageTransitionComplete);
      window.removeEventListener("scroll", schedulePosition, true);
      window.removeEventListener("resize", schedulePosition);
      window.visualViewport?.removeEventListener("resize", schedulePosition);
      window.visualViewport?.removeEventListener("scroll", schedulePosition);
    };
  }, [active, pathname, step]);

  const closeTour = () => {
    markTourSeen();
    setActive(false);
    setHighlight(null);
  };

  const goNext = () => {
    if (!isAuthenticated() && stepIndex === 0) {
      setActive(false);
      router.push("/login");
      return;
    }

    const nextIndex = stepIndex + 1;
    if (nextIndex >= TOUR_STEPS.length) {
      closeTour();
      return;
    }

    const nextStep = TOUR_STEPS[nextIndex];
    setStepIndex(nextIndex);
    setHighlight(null);
    if (!isSameDestination(nextStep.href)) {
      router.push(nextStep.href, { scroll: false });
    }
  };

  if (!mounted || !active || !highlight || typeof document === "undefined") return null;

  const right = highlight.left + highlight.width;
  const bottom = highlight.top + highlight.height;
  const finalStep = stepIndex === TOUR_STEPS.length - 1;

  return createPortal(
    <div className="fixed inset-0 z-[10000]">
      <svg
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 h-full w-full"
        width={highlight.viewportWidth}
        height={highlight.viewportHeight}
        viewBox={`0 0 ${highlight.viewportWidth} ${highlight.viewportHeight}`}
        preserveAspectRatio="none"
      >
        <path
          d={`M0 0H${highlight.viewportWidth}V${highlight.viewportHeight}H0Z M${highlight.left} ${highlight.top}H${right}V${bottom}H${highlight.left}Z`}
          fill="rgba(5, 7, 20, 0.80)"
          fillRule="evenodd"
        />
        <rect
          x={highlight.left}
          y={highlight.top}
          width={highlight.width}
          height={highlight.height}
          rx="4"
          fill="none"
          stroke="#ffd500"
          strokeWidth="3"
        />
      </svg>

      {/* The four blockers stop clicks outside the spotlight but leave its target clickable. */}
      <div
        aria-hidden="true"
        className="fixed left-0 top-0 bg-transparent"
        style={{ width: highlight.viewportWidth, height: highlight.top, pointerEvents: "auto" }}
      />
      <div
        aria-hidden="true"
        className="fixed left-0 bg-transparent"
        style={{ top: bottom, width: highlight.viewportWidth, height: Math.max(0, highlight.viewportHeight - bottom), pointerEvents: "auto" }}
      />
      <div
        aria-hidden="true"
        className="fixed left-0 bg-transparent"
        style={{ top: highlight.top, width: highlight.left, height: highlight.height, pointerEvents: "auto" }}
      />
      <div
        aria-hidden="true"
        className="fixed bg-transparent"
        style={{ left: right, top: highlight.top, width: Math.max(0, highlight.viewportWidth - right), height: highlight.height, pointerEvents: "auto" }}
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="guided-tour-title"
        aria-describedby="guided-tour-description"
        className="fixed z-[10002] max-h-[calc(100vh-24px)] w-[min(360px,calc(100vw-24px))] overflow-y-auto border-2 border-black bg-[#f4f4f0] p-4 text-[#171a38] shadow-[5px_5px_0_#000] sm:p-5"
        style={{ left: panelPosition.left, top: panelPosition.top }}
      >
        <div className="flex items-start justify-between gap-3">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#5866f2]">
            Обучение · шаг {stepIndex + 1} из {TOUR_STEPS.length}
          </p>
          <button
            type="button"
            onClick={closeTour}
            aria-label="Отменить обучение"
            className="flex h-8 w-8 shrink-0 items-center justify-center border-2 border-black bg-white text-lg font-bold leading-none hover:bg-[#ffd500]"
          >
            ×
          </button>
        </div>
        <h2 id="guided-tour-title" className="mt-2 font-display text-xl uppercase leading-tight">
          {step.title}
        </h2>
        <p id="guided-tour-description" className="mt-3 text-sm leading-relaxed">
          {step.description}
        </p>
        <div className="mt-5 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={closeTour}
            className="border-2 border-black bg-white px-3 py-2 text-[10px] font-bold uppercase tracking-wide hover:bg-black hover:text-white"
          >
            Отменить
          </button>
          <button
            type="button"
            onClick={goNext}
            className="border-2 border-black bg-[#ffd500] px-4 py-2 text-[10px] font-bold uppercase tracking-wide hover:bg-black hover:text-white"
          >
            {stepIndex === 0 && !isAuthenticated() ? "Войти →" : finalStep ? "Завершить ✓" : step.nextLabel || "Дальше →"}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
