"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import FloatingTooltip from "./FloatingTooltip";

type HelpTipProps = {
  label: string;
  children: ReactNode;
  align?: "left" | "right";
};

export default function HelpTip({ label, children, align = "left" }: HelpTipProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tooltipId = useId();
  const pointerActivation = useRef(false);

  const clearCloseTimer = () => {
    if (closeTimer.current !== null) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  const scheduleClose = () => {
    clearCloseTimer();
    if (rootRef.current?.contains(document.activeElement)) return;
    closeTimer.current = setTimeout(() => {
      const tooltip = document.getElementById(tooltipId);
      if (!rootRef.current?.contains(document.activeElement) && !tooltip?.matches(":hover")) {
        setOpen(false);
      }
      closeTimer.current = null;
    }, 120);
  };

  useEffect(() => {
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target as Node;
      const tooltip = document.getElementById(tooltipId);
      if (rootRef.current?.contains(target) || tooltip?.contains(target)) return;
      clearCloseTimer();
      setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        clearCloseTimer();
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      clearCloseTimer();
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [tooltipId]);

  return (
    <div
      ref={rootRef}
      className="relative inline-flex shrink-0 align-middle"
      onMouseEnter={() => {
        clearCloseTimer();
        setOpen(true);
      }}
      onMouseLeave={scheduleClose}
      onBlur={(event) => {
        const relatedTarget = event.relatedTarget as Node | null;
        const tooltip = document.getElementById(tooltipId);
        if (
          !event.currentTarget.contains(relatedTarget) &&
          !tooltip?.contains(relatedTarget)
        ) scheduleClose();
      }}
    >
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={tooltipId}
        aria-describedby={open ? tooltipId : undefined}
        onPointerDown={() => { pointerActivation.current = true; }}
        onFocus={() => {
          if (!pointerActivation.current) setOpen(true);
        }}
        onClick={() => {
          clearCloseTimer();
          setOpen((value) => !value);
          pointerActivation.current = false;
        }}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-current text-[11px] font-bold leading-none opacity-80 transition-opacity hover:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2]"
      >
        ?
      </button>
      <FloatingTooltip
        id={tooltipId}
        open={open}
        anchorRef={rootRef}
        align={align}
        interactive
        onMouseEnter={clearCloseTimer}
        onMouseLeave={scheduleClose}
      >
        {children}
      </FloatingTooltip>
    </div>
  );
}
