import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginForm } from "./LoginForm";

const mockInitiateSSO = vi.fn();
let mockSSOLoading = false;
let mockSSOError: string | null = null;

vi.mock("@/hooks/useSSOLogin", () => ({
  useSSOLogin: () => ({
    initiateSSO: mockInitiateSSO,
    isLoading: mockSSOLoading,
    error: mockSSOError,
  }),
}));

describe("LoginForm", () => {
  beforeEach(() => {
    mockInitiateSSO.mockClear();
    mockSSOLoading = false;
    mockSSOError = null;
  });

  it("renders the Microsoft sign-in button", () => {
    render(<LoginForm />);
    expect(
      screen.getByRole("button", { name: /sign in with microsoft/i }),
    ).toBeInTheDocument();
  });

  it("calls initiateSSO when the button is clicked", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);
    await user.click(
      screen.getByRole("button", { name: /sign in with microsoft/i }),
    );
    expect(mockInitiateSSO).toHaveBeenCalledOnce();
  });

  it("displays an SSO error when one is set", () => {
    mockSSOError = "SSO is not configured";
    render(<LoginForm />);
    expect(screen.getByText("SSO is not configured")).toBeInTheDocument();
  });

  it("disables the button and shows progress while redirecting", () => {
    mockSSOLoading = true;
    render(<LoginForm />);
    const button = screen.getByRole("button", { name: /redirecting/i });
    expect(button).toBeDisabled();
  });

  // Microsoft is the only way in, so the password path must not reappear
  // through a stray import or a partially reverted change.
  it("offers no email or password field", () => {
    render(<LoginForm />);
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
  });

  it("offers no sign-up link", () => {
    render(<LoginForm />);
    expect(
      screen.queryByRole("link", { name: /sign up/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/don't have an account/i),
    ).not.toBeInTheDocument();
  });

  it("tells the user where accounts come from", () => {
    render(<LoginForm />);
    expect(screen.getByText(/microsoft entra id/i)).toBeInTheDocument();
  });
});
