import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useScrollRestore } from "./useScrollRestore";

describe("useScrollRestore", () => {
  let mainElement: HTMLElement;

  beforeEach(() => {
    mainElement = document.createElement("main");
    Object.defineProperty(mainElement, "scrollTop", {
      value: 0,
      writable: true,
      configurable: true,
    });
    document.body.appendChild(mainElement);
    sessionStorage.clear();
  });

  afterEach(() => {
    mainElement.remove();
  });

  it("restores scroll position from sessionStorage on mount", () => {
    sessionStorage.setItem("scroll_risk-board", "250");

    renderHook(() => useScrollRestore("risk-board"));

    expect(mainElement.scrollTop).toBe(250);
  });

  it("does not change scroll position when no saved value exists", () => {
    renderHook(() => useScrollRestore("risk-board"));

    expect(mainElement.scrollTop).toBe(0);
  });

  it("saves scroll position to sessionStorage on scroll", async () => {
    vi.useFakeTimers();

    renderHook(() => useScrollRestore("risk-board"));

    // Simulate scroll
    Object.defineProperty(mainElement, "scrollTop", {
      value: 500,
      writable: true,
      configurable: true,
    });
    mainElement.dispatchEvent(new Event("scroll"));

    // Advance past the 150ms debounce
    vi.advanceTimersByTime(200);

    expect(sessionStorage.getItem("scroll_risk-board")).toBe("500");

    vi.useRealTimers();
  });
});
