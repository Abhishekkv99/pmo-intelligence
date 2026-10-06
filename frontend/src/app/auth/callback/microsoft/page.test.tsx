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

  it("exchanges code and redirects on success", async () => {
    mockSearchParams = new URLSearchParams({ code: "auth_code_123" });
    mockPost.mockResolvedValueOnce({
      access_token: "jwt_token",
      token_type: "bearer",
    });

    // Mock window.location.href assignment (used instead of router.replace for cookie propagation)
    const locationHrefSpy = vi
      .spyOn(window, "location", "get")
      .mockReturnValue({
        ...window.location,
        origin: "http://localhost:3000",
        href: "http://localhost:3000/auth/callback/microsoft",
      } as Location);
    const hrefSetter = vi.fn();
    vi.spyOn(window, "location", "set").mockImplementation((val) =>
      hrefSetter(val),
    );
    // Use defineProperty to capture href assignment
    Object.defineProperty(window, "location", {
      value: { ...window.location, origin: "http://localhost:3000", href: "" },
      writable: true,
      configurable: true,
    });

    render(<MicrosoftCallbackPage />);
    expect(screen.getByText("Signing you in...")).toBeInTheDocument();

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledOnce();
      expect(mockSetToken).toHaveBeenCalledWith("jwt_token");
      expect(window.location.href).toBe("/");
    });
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
