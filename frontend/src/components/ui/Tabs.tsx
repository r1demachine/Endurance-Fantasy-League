"use client";

import { useId, useRef } from "react";
import type { KeyboardEvent, ReactNode } from "react";

export type TabItem<T extends string = string> = {
  value: T; label: ReactNode; disabled?: boolean; className?: string; activeClassName?: string;
};
type TabsProps<T extends string> = {
  items: TabItem<T>[]; value: T; onChange: (value: T) => void; ariaLabel: string;
  className?: string; tabClassName?: string; activeClassName?: string; inactiveClassName?: string;
};

export function Tabs<T extends string>({
  items, value, onChange, ariaLabel, className = "flex", tabClassName = "",
  activeClassName = "bg-[#ffd500] text-[#111]", inactiveClassName = "hover:bg-black/5",
}: TabsProps<T>) {
  const id = useId().replace(/:/g, "");
  const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex = index;
    if (event.key === "Home") {
      event.preventDefault();
      nextIndex = items.findIndex((item) => !item.disabled);
    } else if (event.key === "End") {
      event.preventDefault();
      for (let candidate = items.length - 1; candidate >= 0; candidate -= 1) {
        if (!items[candidate].disabled) { nextIndex = candidate; break; }
      }
    } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const direction = event.key === "ArrowRight" ? 1 : -1;
      for (let step = 0; step < items.length; step += 1) {
        nextIndex = (nextIndex + direction + items.length) % items.length;
        if (!items[nextIndex].disabled) break;
      }
    } else return;
    const nextItem = items[nextIndex];
    if (!nextItem || nextItem.disabled) return;
    buttonRefs.current[nextIndex]?.focus();
    onChange(nextItem.value);
  };
  return (
    <div role="tablist" aria-label={ariaLabel} className={className}>
      {items.map((item, index) => {
        const selected = value === item.value;
        const stateClassName = selected ? item.activeClassName ?? activeClassName : inactiveClassName;
        return (
          <button
            key={item.value}
            ref={(node) => { buttonRefs.current[index] = node; }}
            id={`tab-${id}-${item.value}`}
            type="button" role="tab" aria-selected={selected} tabIndex={selected ? 0 : -1}
            disabled={item.disabled} onClick={() => onChange(item.value)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={[`focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] ${tabClassName}`, item.className, stateClassName].filter(Boolean).join(" ")}
          >{item.label}</button>
        );
      })}
    </div>
  );
}
