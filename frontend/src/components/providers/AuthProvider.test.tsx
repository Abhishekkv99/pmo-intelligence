import { render, screen, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockReplace = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  usePathname: () => "/dashboard",
}));

const mockApi = vi.hoisted(() => ({
  refresh: vi.fn<() => Promise<boolean>>(),
  get: vi.fn(),
  handler: null as (() => void) | null,
}));
vi.mock("@/lib/api", () => ({
  api: { get: mockApi.get, post: vi.fn() },
  ApiError: class ApiError extends Error {},
  refreshAccessToken: mockApi.refresh,
  setSessionExpiredHandler: (h: (() => void) | null) => {
    mockApi.handler = h;
  },
}));

import { AuthProvider, useAuth } from "./AuthProvider";

function WhoAmI() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <p>loading</p>;
  return <p>{user ? `signed in as ${user.email}` : "signed out"}</p>;
}

function renderProvider() {
  return render(
    <AuthProvider>
      <WhoAmI />
    </AuthProvider>,
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockApi.refresh.mockReset();
    mockApi.get.mockReset();
    mockApi.handler = null;
  });

  it("sends the browser to login when the session cannot be restored", async () => {
    mockApi.refresh.mockResolvedValue(false);
    renderProvider();

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
    expect(screen.getByText("signed out")).toBeTruthy();
    expect(mockApi.get).not.toHaveBeenCalled();
  });

  it("restores the user through the shared refresh", async () => {
    mockApi.refresh.mockResolvedValue(true);
    mockApi.get.mockResolvedValue({ email: "admin@example.com" });
    renderProvider();

    expect(
      await screen.findByText("signed in as admin@example.com"),
    ).toBeTruthy();
    expect(mockApi.get).toHaveBeenCalledWith("/auth/me");
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("sends the browser to login when the session expires mid-use", async () => {
    mockApi.refresh.mockResolvedValue(true);
    mockApi.get.mockResolvedValue({ email: "admin@example.com" });
    renderProvider();
    await screen.findByText("signed in as admin@example.com");

    expect(mockApi.handler).not.toBeNull();
    act(() => mockApi.handler?.());

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login"));
    expect(screen.getByText("signed out")).toBeTruthy();
  });
});
