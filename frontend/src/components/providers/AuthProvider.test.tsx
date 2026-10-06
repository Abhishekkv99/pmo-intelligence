import { render, screen, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockNav = vi.hoisted(() => ({ replace: vi.fn(), pathname: "/" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockNav.replace }),
  usePathname: () => mockNav.pathname,
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

const PMO_MANAGER = { email: "manager@example.com", role: "pmo_manager" };

function WhoAmI() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <p>loading</p>;
  return (
    <p>
      {user
        ? `signed in as ${user.email} (${user.role ?? "no role"})`
        : "signed out"}
    </p>
  );
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
    mockNav.replace.mockReset();
    mockNav.pathname = "/";
    mockApi.refresh.mockReset();
    mockApi.get.mockReset();
    mockApi.handler = null;
  });

  it("sends the browser to login when the session cannot be restored", async () => {
    mockApi.refresh.mockResolvedValue(false);
    renderProvider();

    await waitFor(() => expect(mockNav.replace).toHaveBeenCalledWith("/login"));
    expect(screen.getByText("signed out")).toBeTruthy();
    expect(mockApi.get).not.toHaveBeenCalled();
  });

  it("restores the user, with their role, through the shared refresh", async () => {
    mockApi.refresh.mockResolvedValue(true);
    mockApi.get.mockResolvedValue(PMO_MANAGER);
    renderProvider();

    expect(
      await screen.findByText("signed in as manager@example.com (pmo_manager)"),
    ).toBeTruthy();
    expect(mockApi.get).toHaveBeenCalledWith("/auth/me");
    expect(mockNav.replace).not.toHaveBeenCalled();
  });

  it("keeps a signed-in user with no role yet on the page", async () => {
    mockApi.refresh.mockResolvedValue(true);
    mockApi.get.mockResolvedValue({ email: "new@example.com", role: null });
    renderProvider();

    expect(
      await screen.findByText("signed in as new@example.com (no role)"),
    ).toBeTruthy();
    expect(mockNav.replace).not.toHaveBeenCalled();
  });

  it("sends a signed-in user away from the login page to the risk board", async () => {
    mockNav.pathname = "/login";
    mockApi.refresh.mockResolvedValue(true);
    mockApi.get.mockResolvedValue(PMO_MANAGER);
    renderProvider();

    await waitFor(() => expect(mockNav.replace).toHaveBeenCalledWith("/"));
  });

  it("leaves a signed-out visitor on the login page", async () => {
    mockNav.pathname = "/login";
    mockApi.refresh.mockResolvedValue(false);
    renderProvider();

    await screen.findByText("signed out");
    expect(mockNav.replace).not.toHaveBeenCalled();
  });

  it("sends the browser to login when the session expires mid-use", async () => {
    mockApi.refresh.mockResolvedValue(true);
    mockApi.get.mockResolvedValue(PMO_MANAGER);
    renderProvider();
    await screen.findByText("signed in as manager@example.com (pmo_manager)");

    expect(mockApi.handler).not.toBeNull();
    act(() => mockApi.handler?.());

    await waitFor(() => expect(mockNav.replace).toHaveBeenCalledWith("/login"));
    expect(screen.getByText("signed out")).toBeTruthy();
  });
});
