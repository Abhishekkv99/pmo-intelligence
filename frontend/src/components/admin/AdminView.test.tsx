import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Role } from "@/lib/roles";

const mockUseAuth = vi.fn();

vi.mock("@/components/providers/AuthProvider", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("./ProcessingStatusPanel", () => ({
  ProcessingStatusPanel: ({ enabled }: { enabled: boolean }) => (
    <div data-testid="panel">{String(enabled)}</div>
  ),
}));

import { AdminView } from "./AdminView";

function signInAs(role: Role | null) {
  mockUseAuth.mockReturnValue({
    user: { role },
    isLoading: false,
    logout: vi.fn(),
  });
}

describe("AdminView", () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
  });

  it.each<Role>(["pmo_manager", "admin"])(
    "shows the queue panel to %s",
    (role) => {
      signInAs(role);
      render(<AdminView />);
      expect(screen.getByTestId("panel")).toHaveTextContent("true");
      expect(
        screen.queryByText(/available to PMO managers/),
      ).not.toBeInTheDocument();
    },
  );

  it.each<Role | null>(["sme", "tech_lead", "ps", null])(
    "shows the no-access message, not the panel, to %s",
    (role) => {
      signInAs(role);
      render(<AdminView />);
      expect(screen.queryByTestId("panel")).not.toBeInTheDocument();
      expect(
        screen.getByText("Admin is available to PMO managers and admins"),
      ).toBeInTheDocument();
    },
  );
});
