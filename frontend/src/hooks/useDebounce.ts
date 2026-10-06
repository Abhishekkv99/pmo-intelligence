"use client";

import { useState, useEffect } from "react";

/**
 * Debounce a value by the specified delay in milliseconds.
 * Returns the debounced value that only updates after the caller
 * stops changing the input for `delay` ms.
 */
export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}
