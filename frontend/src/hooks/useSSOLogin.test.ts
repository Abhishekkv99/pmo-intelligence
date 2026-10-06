import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet } = vi.hoisted(() => ({
  mockGet: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: { get: mockGet },
}));

vi.mock("@/lib/pkce", () => ({
  generateCodeVerifier: () => "verifier",
  generateCodeChallenge: async () => "challenge",
  storeCodeVerifier: () => undefined,
}));

import { useSSOLogin } from "./useSSOLogin";

describe("useSSOLogin", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, "location", {
      value: { ...window.location, href: "" },
      writable: true,
    });
  });

  it("redirects to the authority the server returns, not the tenant id", async () => {
    mockGet.mockResolvedValue({
      client_id: "client-123",
      tenant_id: "tenant-home",
      authority: "organizations",
      redirect_uri: "http://localhost:3000/auth/callback/microsoft",
    });

    const { result } = renderHook(() => useSSOLogin());
    await act(async () => {
      await result.current.initiateSSO();
    });

    const url = new URL(window.location.href);
    expect(url.origin).toBe("https://login.microsoftonline.com");
    expect(url.pathname).toBe("/organizations/oauth2/v2.0/authorize");
    expect(url.searchParams.get("client_id")).toBe("client-123");
    expect(url.searchParams.get("code_challenge")).toBe("challenge");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
  });

  it("uses the tenant id as the authority for a single-tenant deployment", async () => {
    mockGet.mockResolvedValue({
      client_id: "client-123",
      tenant_id: "tenant-home",
      authority: "tenant-home",
      redirect_uri: "http://localhost:3000/auth/callback/microsoft",
    });

    const { result } = renderHook(() => useSSOLogin());
    await act(async () => {
      await result.current.initiateSSO();
    });

    expect(new URL(window.location.href).pathname).toBe(
      "/tenant-home/oauth2/v2.0/authorize",
    );
  });

  it("sets an error and stops loading when the config fetch fails", async () => {
    mockGet.mockRejectedValue(new Error("network"));

    const { result } = renderHook(() => useSSOLogin());
    await act(async () => {
      await result.current.initiateSSO();
    });

    await waitFor(() => {
      expect(result.current.error).toBe(
        "Failed to initiate SSO login. Please try again.",
      );
    });
    expect(result.current.isLoading).toBe(false);
    expect(window.location.href).toBe("");
  });
});
