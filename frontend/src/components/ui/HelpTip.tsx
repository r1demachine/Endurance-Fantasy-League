"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

type HelpTipProps = {
  label: string;
  children: ReactNode;
  align?: "left" | "right";
};

export default function HelpTip({ label, children, align = "left" }: HelpTipProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const tooltipId = useId();
  const pointerActivation = useRef(false);

  useEffect(() => {
    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  return (
    <div
      ref={rootRef}
      className="relative inline-flex shrink-0 align-middle"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => {
        if (!rootRef.current?.contains(document.activeElement)) setOpen(false);
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-controls={tooltipId}
        aria-describedby={open ? tooltipId : undefined}
        onPointerDown={() => { pointerActivation.current = true; }}
        onFocus={() => { if (!pointerActivation.current) setOpen(true); }}
        onClick={() => {
          setOpen((value) => !value);
          pointerActivation.current = false;
        }}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-current text-[11px] font-bold leading-none opacity-80 transition-opacity hover:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#5866f2]"
      >
        ?
      </button>
      {open && (
        <div
          id={tooltipId}
          role="tooltip"
          className={`absolute top-full z-50 mt-2 w-72 max-w-[calc(100vw-2rem)] border-2 border-black bg-white p-3 text-left text-xs font-normal leading-relaxed normal-case tracking-normal text-[#171a38] shadow-lg ${align === "left" ? "left-0" : "right-0"}`}
        >
          {children}
        </div>
      )}
    </div>
  );
}
