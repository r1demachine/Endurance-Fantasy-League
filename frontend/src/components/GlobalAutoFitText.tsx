"use client";

import { useEffect } from "react";

const MIN_FONT_SIZE_PX = 8;
const FIT_SELECTOR = [
  "h1", "h2", "h3", "h4", "h5", "h6",
  "button", "a", "label",
  "[data-autofit-text]",
  "[class~=\"truncate\"]",
  "[class~=\"whitespace-nowrap\"]",
  "p", "span", "small", "strong", "em",
].join(",");

type OriginalStyles = {
  fontSize: string;
  whiteSpace: string;
  overflowWrap: string;
};

function isEligible(element: HTMLElement): boolean {
  const tag = element.tagName.toLowerCase();
  const text = (element.innerText || element.textContent || "").trim();
  if (!text || text.length < 2) return false;
  if (tag === "p" && text.length > 96 &&
      !element.matches("[data-autofit-text], [class~=\"truncate\"], [class~=\"whitespace-nowrap\"]")) {
    return false;
  }
  if (element.closest("svg,script,style,textarea,select,[contenteditable=\"true\"]")) return false;
  if (element.getAttribute("aria-hidden") === "true") return false;

  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.display === "contents") return false;
  // Inline fragments have no independent available width; their block/flex parent
  // or the nearest button/link is fitted instead.
  if (style.display === "inline" &&
      !element.matches("[data-autofit-text], [class~=\"truncate\"], [class~=\"whitespace-nowrap\"]")) {
    return false;
  }
  return true;
}

function fitElement(
  element: HTMLElement,
  originals: WeakMap<HTMLElement, OriginalStyles>,
): void {
  let original = originals.get(element);
  if (!original) {
    original = {
      fontSize: element.style.fontSize,
      whiteSpace: element.style.whiteSpace,
      overflowWrap: element.style.overflowWrap,
    };
    originals.set(element, original);
  }

  // Restore React-authored inline styles before calculating this element's
  // intended size. The fitted value is always derived from the current CSS.
  element.style.fontSize = original.fontSize;
  element.style.whiteSpace = original.whiteSpace;
  element.style.overflowWrap = original.overflowWrap;

  if (!isEligible(element)) return;
  const availableWidth = element.clientWidth;
  if (availableWidth <= 0) return;

  const baseFont = Number.parseFloat(window.getComputedStyle(element).fontSize);
  if (!Number.isFinite(baseFont) || baseFont <= MIN_FONT_SIZE_PX) return;

  const oldWhiteSpace = element.style.whiteSpace;
  const oldOverflowWrap = element.style.overflowWrap;
  element.style.whiteSpace = "nowrap";
  element.style.overflowWrap = "normal";

  if (element.scrollWidth <= element.clientWidth + 1) {
    element.style.whiteSpace = oldWhiteSpace;
    element.style.overflowWrap = oldOverflowWrap;
    return;
  }

  const minSize = Math.min(MIN_FONT_SIZE_PX, baseFont);
  let low = minSize;
  let high = baseFont;
  let fittingSize = minSize;

  // Binary search is cheaper and steadier than shrinking one pixel at a time.
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const candidate = (low + high) / 2;
    element.style.fontSize = `${candidate}px`;
    if (element.scrollWidth <= element.clientWidth + 1) {
      fittingSize = candidate;
      high = candidate;
    } else {
      low = candidate;
    }
  }

  element.style.fontSize = `${fittingSize}px`;
  element.style.whiteSpace = "nowrap";
  element.style.overflowWrap = "normal";
}

export default function GlobalAutoFitText() {
  useEffect(() => {
    const originals = new WeakMap<HTMLElement, OriginalStyles>();
    let frame = 0;
    let stopped = false;

    const fitPage = () => {
      frame = 0;
      if (stopped || !document.body) return;

      const elements = Array.from(
        document.body.querySelectorAll<HTMLElement>(FIT_SELECTOR),
      );
      // Fit leaf labels before their containers so nested text can use its own
      // available width; ancestor buttons/headings are measured afterwards.
      const depth = (element: HTMLElement) => {
        let value = 0;
        let node: HTMLElement | null = element;
        while (node) {
          value += 1;
          node = node.parentElement;
        }
        return value;
      };
      elements.sort((left, right) => depth(right) - depth(left));

      for (const element of elements) {
        fitElement(element, originals);
      }
    };

    const scheduleFit = () => {
      if (stopped || frame !== 0) return;
      frame = window.requestAnimationFrame(fitPage);
    };

    const observer = new MutationObserver(scheduleFit);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class"],
    });
    window.addEventListener("resize", scheduleFit, { passive: true });
    document.fonts?.addEventListener("loadingdone", scheduleFit);
    scheduleFit();
    void document.fonts?.ready.then(scheduleFit);

    return () => {
      stopped = true;
      observer.disconnect();
      window.removeEventListener("resize", scheduleFit);
      document.fonts?.removeEventListener("loadingdone", scheduleFit);
      if (frame !== 0) window.cancelAnimationFrame(frame);

      // The global behaviour is a presentation enhancement, not permanent DOM
      // state; put original inline styles back when the app root unmounts.
      for (const element of Array.from(document.body.querySelectorAll<HTMLElement>(FIT_SELECTOR))) {
        const original = originals.get(element);
        if (!original) continue;
        element.style.fontSize = original.fontSize;
        element.style.whiteSpace = original.whiteSpace;
        element.style.overflowWrap = original.overflowWrap;
      }
    };
  }, []);

  return null;
}
