import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Use vi.hoisted to avoid TDZ issues with vi.mock hoisting
const { mockReplace, mockPost, mockSetToken } = vi.hoisted(() => ({
  mockReplace: vi.fn(),
  mockPost: vi.fn(),
  mockSetToken: vi.fn(),
}));

let mockSearchParams = new URLSearchParams();
let storedVerifier: string | null = "test_code_verifier";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mockReplace }),
  useSearchParams: () => mockSearchParams,
}));

vi.mock("@/lib/api", () => ({
  api: { post: mockPost },
}));

vi.mock("@/lib/auth-token", () => ({
  setToken: (...args: unknown[]) => mockSetToken(...args),
}));

vi.mock("@/lib/pkce", () => ({
  retrieveCodeVerifier: () => {
    const v = storedVerifier;
    storedVerifier = null;
    return v;
  },
}));

// Import after mocks are set up
import MicrosoftCallbackPage from "./page";

describe("MicrosoftCallbackPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storedVerifier = "test_code_verifier";
    mockSearchParams = new URLSearchParams();
  });

  it("shows error when Microsoft returns an error param", () => {
    mockSearchParams = new URLSearchParams({
      error: "access_denied",
      error_description: "User cancelled the sign-in.",
    });
    render(<MicrosoftCallbackPage />);
    expect(screen.getByText("Sign In Failed")).toBeInTheDocument();
    expect(screen.getByText("User cancelled the sign-in.")).toBeInTheDocument();
  });

  it("shows error when no authorization code is present", () => {
    mockSearchParams = new URLSearchParams();
    render(<MicrosoftCallbackPage />);
    expect(
      screen.getByText("No authorization code received from Microsoft."),
    ).toBeInTheDocument();
  });

  it("shows error when PKCE verifier is missing from sessionStorage", () => {
    storedVerifier = null;
    mockSearchParams = new URLSearchParams({ code: "auth_code_123" });
    render(<MicrosoftCallbackPage />);
    expect(screen.getByText(/Missing PKCE verifier/)).toBeInTheDocument();
  });

  it("exchanges the code and sends the browser to the risk board", async () => {
    mockSearchParams = new URLSearchParams({ code: "auth_code_123" });
    mockPost.mockResolvedValueOnce({
      access_token: "jwt_token",
      token_type: "bearer",
    });

    // The page assigns window.location.href (a full navigation, so the refresh
    // cookie is in place before the next request); capture that assignment.
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      value: { origin: "http://localhost:3000", href: "" },
      writable: true,
      configurable: true,
    });

    try {
      render(<MicrosoftCallbackPage />);
      expect(screen.getByText("Signing you in...")).toBeInTheDocument();

      await waitFor(() => {
        expect(window.location.href).toBe("/");
      });
      expect(mockPost).toHaveBeenCalledExactlyOnceWith(
        "/auth/sso/microsoft/callback",
        {
          code: "auth_code_123",
          code_verifier: "test_code_verifier",
          redirect_uri: "http://localhost:3000/auth/callback/microsoft",
        },
      );
      expect(mockSetToken).toHaveBeenCalledWith("jwt_token");
    } finally {
      Object.defineProperty(window, "location", {
        value: originalLocation,
        writable: true,
        configurable: true,
      });
    }
  });

  it("shows error when code exchange fails", async () => {
    mockSearchParams = new URLSearchParams({ code: "auth_code_123" });
    mockPost.mockRejectedValueOnce(new Error("Network error"));

    render(<MicrosoftCallbackPage />);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to complete SSO login. Please try again."),
      ).toBeInTheDocument();
    });
  });

  it("renders Back to Login button on error that navigates to login", async () => {
    const user = userEvent.setup();
    mockSearchParams = new URLSearchParams({ error: "server_error" });
    render(<MicrosoftCallbackPage />);

    const backBtn = screen.getByRole("button", { name: "Back to Login" });
    expect(backBtn).toBeInTheDocument();
    await user.click(backBtn);
    expect(mockReplace).toHaveBeenCalledWith("/login");
  });
});
