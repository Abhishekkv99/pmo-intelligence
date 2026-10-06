"use client";

import { useEffect, useRef } from "react";

const SCROLL_KEY_PREFIX = "scroll_";

/**
 * Saves and restores scroll position for a given key using sessionStorage.
 * Targets the MainLayout `<main>` element as the scroll container.
 *
 * @param key - Unique key for identifying the scroll position (e.g., route path)
 */
export function useScrollRestore(key: string): void {
  const restoredRef = useRef(false);

  useEffect(() => {
    const storageKey = `${SCROLL_KEY_PREFIX}${key}`;
    const scrollContainer = document.querySelector("main");
    if (!scrollContainer) return;

    // Restore scroll position on mount (once)
    if (!restoredRef.current) {
      const saved = sessionStorage.getItem(storageKey);
      if (saved !== null) {
        const scrollTop = parseInt(saved, 10);
        if (!isNaN(scrollTop)) {
          scrollContainer.scrollTop = scrollTop;
        }
      }
      restoredRef.current = true;
    }

    // Save scroll position on scroll (debounced)
    let timeoutId: ReturnType<typeof setTimeout>;
    const handleScroll = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        sessionStorage.setItem(storageKey, String(scrollContainer.scrollTop));
      }, 150);
    };

    scrollContainer.addEventListener("scroll", handleScroll, { passive: true });

    return () => {
      clearTimeout(timeoutId);
      scrollContainer.removeEventListener("scroll", handleScroll);
    };
  }, [key]);
}
