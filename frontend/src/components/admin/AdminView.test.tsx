import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Role } from "@/lib/roles";

const mockUseAuth = vi.fn();
const replace = vi.fn();
let search = "";

vi.mock("@/components/providers/AuthProvider", () => ({
  useAuth: () => mockUseAuth(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/admin",
  useSearchParams: () => new URLSearchParams(search),
}));
vi.mock("./ProcessingStatusPanel", () => ({
  ProcessingStatusPanel: ({ enabled }: { enabled: boolean }) => (
    <div data-testid="panel">{String(enabled)}</div>
  ),
}));
vi.mock("./register/RegisterTab", () => ({
  RegisterTab: () => <div data-testid="register-tab" />,
}));
vi.mock("./register/ImportTab", () => ({
  ImportTab: () => <div data-testid="import-tab" />,
}));
vi.mock("./users/UsersTab", () => ({
  UsersTab: () => <div data-testid="users-tab" />,
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
    replace.mockReset();
    search = "";
  });

  it.each<Role>(["pmo_manager", "admin"])(
    "opens on the register for %s",
    (role) => {
      signInAs(role);
      render(<AdminView />);

      expect(screen.getByTestId("register-tab")).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Register" })).toHaveAttribute(
        "aria-selected",
        "true",
      );
    },
  );

  it("opens the tab named in the URL, and polls the queue only there", () => {
    signInAs("pmo_manager");
    search = "tab=processing";
    render(<AdminView />);

    expect(screen.getByTestId("panel")).toHaveTextContent("true");
  });

  it("puts the chosen tab in the URL", async () => {
    signInAs("admin");
    render(<AdminView />);

    await userEvent.click(screen.getByRole("tab", { name: "Import" }));

    expect(replace).toHaveBeenCalledWith("/admin?tab=import", {
      scroll: false,
    });
  });

  it("lists the tabs in order", () => {
    signInAs("pmo_manager");
    render(<AdminView />);

    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Register",
      "Import",
      "Users and roles",
      "Processing",
    ]);
  });

  it("falls back to the register for an unknown tab", () => {
    signInAs("pmo_manager");
    search = "tab=nonsense";
    render(<AdminView />);

    expect(screen.getByTestId("register-tab")).toBeInTheDocument();
  });

  it.each<Role | null>(["sme", "tech_lead", "ps", null])(
    "shows the no-access message, and no tabs, to %s",
    (role) => {
      signInAs(role);
      render(<AdminView />);

      expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
      expect(
        screen.getByText("Admin is available to PMO managers and admins"),
      ).toBeInTheDocument();
    },
  );
});
