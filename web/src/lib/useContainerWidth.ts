import { useCallback, useEffect, useState } from "react";

/**
 * Measures the width of the element the returned ref is attached to, so a
 * chart can fill its column instead of forcing a fixed pixel width that
 * overflows a phone (UI-02). Falls back to `fallback` until measured and
 * wherever layout does not exist (jsdom reports 0), which keeps tests
 * rendering at the chart's nominal size.
 */
export function useContainerWidth<T extends HTMLElement = HTMLDivElement>(fallback: number) {
  const [element, setElement] = useState<T | null>(null);
  const [width, setWidth] = useState<number | null>(null);
  const ref = useCallback((node: T | null) => setElement(node), []);

  useEffect(() => {
    if (!element) return;
    const update = () => {
      const measured = Math.floor(element.getBoundingClientRect().width);
      setWidth(measured > 0 ? measured : null);
    };
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);

  return [ref, width ?? fallback] as const;
}
