import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { act, render, screen } from "@testing-library/react";
import { toast } from "sonner";

vi.mock("next/font/google", () => ({
  Geist: () => ({ variable: "font-geist-sans" }),
  Geist_Mono: () => ({ variable: "font-geist-mono" }),
}));

vi.mock("@/components/providers/AuthProvider", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("@/components/providers/SWRProvider", () => ({
  SWRProvider: ({ children }: { children: React.ReactNode }) => children,
}));

import RootLayout, { metadata } from "./layout";
import { Toaster } from "@/components/ui/sonner";

const originalMatchMedia = window.matchMedia;

beforeEach(() => {
  // jsdom has no matchMedia; next-themes and sonner read it to follow the
  // system theme.
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
});

afterEach(() => {
  window.matchMedia = originalMatchMedia;
});

describe("RootLayout", () => {
  it("carries the PMO Intelligence name and tagline in the page metadata", () => {
    expect(metadata.title).toBe("PMO Intelligence");
    expect(metadata.description).toBe(
      "Live health for every consultant placement",
    );
  });

  it("mounts the toast notification region alongside the page", () => {
    const html = renderToStaticMarkup(
      <RootLayout>
        <p>Page content</p>
      </RootLayout>,
    );

    expect(html).toContain("Page content");
    expect(html).toMatch(/<section[^>]*aria-label="Notifications/);
  });
});

describe("Toaster", () => {
  it("shows a toast raised anywhere in the app", async () => {
    render(<Toaster />);

    act(() => {
      toast.success("API key revoked");
    });

    expect(await screen.findByText("API key revoked")).toBeInTheDocument();
  });
});
