import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockApi = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: mockApi }));
vi.mock("@/hooks/useSSOLogin", () => ({
  useSSOLogin: () => ({ initiateSSO: vi.fn(), isLoading: false, error: null }),
}));

import LoginPage from "@/app/login/page";
import { formatSaidAt } from "./MiniRiskBoard";

describe("Sign-in showcase", () => {
  const fetchSpy = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    fetchSpy.mockReset();
    Object.values(mockApi).forEach((fn) => fn.mockReset());
  });

  it("states the promise as the page's one top heading", () => {
    render(<LoginPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent(
      "Know which placement is at risk. Before the client does.",
    );
    expect(
      screen.getByRole("button", { name: /sign in with microsoft/i }),
    ).toBeInTheDocument();
  });

  it("draws the sample rows with the app's badges and trends", () => {
    render(<LoginPage />);
    const rows = screen.getAllByTestId("sample-row");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("Aisha Rahman · Fabrikam");
    expect(rows[0]).toHaveTextContent("Last call 3 days ago");
    expect(within(rows[0]).getByTestId("health-badge")).toHaveTextContent(
      "4.1Red",
    );
    expect(within(rows[0]).getByLabelText(/Falling, -1.6/)).toBeInTheDocument();
    expect(within(rows[2]).getByTestId("health-badge")).toHaveTextContent(
      "6.8Amber",
    );
  });

  it("marks the preview as sample data, on the card and in the footer", () => {
    render(<LoginPage />);
    expect(screen.getByText("Sample data")).toBeInTheDocument();
    expect(
      screen.getByText("Internal tool. Sample data shown."),
    ).toBeInTheDocument();
  });

  it("shows the flag by its trigger and severity, with its quote and time", () => {
    render(<LoginPage />);
    expect(screen.getByText("Client dissatisfaction")).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(
      screen.getByText(/losing confidence in the timeline/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Said on a call, 12 Sep · 14:32"),
    ).toBeInTheDocument();
  });

  it("lists the three highlights", () => {
    render(<LoginPage />);
    const titles = screen
      .getAllByRole("heading", { level: 2 })
      .map((h) => h.textContent);
    expect(titles).toEqual([
      "Every call, read",
      "Six dimensions, one score",
      "A flag only with evidence",
    ]);
  });

  it("requests nothing before sign-in", () => {
    render(<LoginPage />);
    expect(fetchSpy).not.toHaveBeenCalled();
    Object.values(mockApi).forEach((fn) => expect(fn).not.toHaveBeenCalled());
  });

  it("stays in the light theme whatever the theme setting", () => {
    const { container } = render(<LoginPage />);
    expect(container.firstElementChild).toHaveClass("theme-light");
  });
});

describe("formatSaidAt", () => {
  it.each([
    ["2026-09-12T13:32:00Z", "12 Sep · 14:32"], // BST
    ["2026-12-01T09:05:00Z", "1 Dec · 09:05"], // GMT
  ])("shows %s on a UK clock as %s", (iso, expected) => {
    expect(formatSaidAt(iso)).toBe(expected);
  });
});
