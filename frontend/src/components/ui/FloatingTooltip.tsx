"use client";

import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

type FloatingTooltipProps = {
  id: string;
  open: boolean;
  anchorRef: RefObject<HTMLElement | null>;
  children: ReactNode;
  align?: "left" | "right";
  interactive?: boolean;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
};

export default function FloatingTooltip({
  id,
  open,
  anchorRef,
  children,
  align = "left",
  interactive = false,
  onMouseEnter,
  onMouseLeave,
}: FloatingTooltipProps) {
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: 12, top: 12 });

  useEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      const anchor = anchorRef.current;
      if (!anchor) return;
      const rect = anchor.getBoundingClientRect();
      const width = Math.min(288, Math.max(0, window.innerWidth - 24));
      const panelHeight = tooltipRef.current?.getBoundingClientRect().height ?? 120;
      let left = align === "right" ? rect.right - width : rect.left;
      left = Math.max(12, Math.min(left, window.innerWidth - width - 12));

      let top = rect.bottom + 8;
      if (top + panelHeight > window.innerHeight - 12) {
        top = rect.top - panelHeight - 8;
      }
      top = Math.max(12, Math.min(top, window.innerHeight - panelHeight - 12));
      setPosition({ left, top });
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open, align, anchorRef]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={tooltipRef}
      id={id}
      role="tooltip"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{ left: position.left, top: position.top, pointerEvents: interactive ? "auto" : "none" }}
      className="fixed z-[9999] w-72 max-w-[calc(100vw-1.5rem)] border-2 border-black bg-white p-3 text-left text-sm font-normal leading-relaxed normal-case tracking-normal text-[#171a38] shadow-[3px_3px_0_#000]"
    >
      {children}
    </div>,
    document.body
  );
}
