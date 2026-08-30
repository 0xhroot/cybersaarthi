import { useEffect, useRef, useState } from "react";

export function useDebounce<T>(value: T, delayMs = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

const MOBILE_QUERY = "(max-width: 768px)";

export function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(() =>
    typeof window === "undefined" ? false : window.matchMedia(MOBILE_QUERY).matches,
  );
  useEffect(() => {
    const mql = window.matchMedia(MOBILE_QUERY);
    const onChange = () => setMobile(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  return mobile;
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window === "undefined" ? false : window.matchMedia(query).matches,
  );
  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    mql.addEventListener("change", onChange);
    setMatches(mql.matches);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

export function useDocumentTitle(title: string): void {
  useEffect(() => {
    const base = "CyberSaarthi";
    document.title = title ? `${title} · ${base}` : base;
  }, [title]);
}

/**
 * Global keyboard shortcut handler. Returns whether a handler consumed the key
 * so a palette can prevent further propagation.
 */
export function useHotkey(
  combos: string[],
  handler: (event: KeyboardEvent) => void,
  deps: unknown[] = [],
): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      const alt = event.altKey;
      const plain = event.key.toLowerCase();
      for (const combo of combos) {
        const parts = combo.split("+").map((p) => p.toLowerCase());
        const needsMod = parts.includes("mod");
        const needsAlt = parts.includes("alt");
        const key = parts.find((p) => !["mod", "alt"].includes(p)) ?? "";
        if (needsMod === mod && needsAlt === alt && key === plain) {
          event.preventDefault();
          handlerRef.current(event);
          return;
        }
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [combos.join("|"), ...deps]);
}