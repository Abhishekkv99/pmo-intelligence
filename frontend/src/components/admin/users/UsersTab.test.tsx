import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { UserListItem } from "@/types/register";

const grantRole = vi.fn();
const changeRole = vi.fn();
const mutate = vi.fn();
const success = vi.fn();
let users: UserListItem[] = [];

vi.mock("@/hooks/useUsers", () => ({
  useUsers: () => ({ users, isLoading: false, error: null, mutate }),
  grantRole: (...args: unknown[]) => grantRole(...args),
  changeRole: (...args: unknown[]) => changeRole(...args),
}));
vi.mock("@/components/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "u1" } }),
}));
vi.mock("sonner", () => ({ toast: { success: (m: string) => success(m) } }));

import { ApiError } from "@/lib/api";
import { UsersTab } from "./UsersTab";

const manager: UserListItem = {
  id: "u1",
  email: "boss@example.com",
  full_name: "Boss",
  role: "pmo_manager",
  is_active: true,
  signed_in_with_microsoft: true,
};

const newcomer: UserListItem = {
  id: "u2",
  email: "new@example.com",
  full_name: "new",
  role: null,
  is_active: true,
  signed_in_with_microsoft: false,
};

describe("UsersTab", () => {
  beforeEach(() => {
    users = [manager, newcomer];
    grantRole.mockReset();
    changeRole.mockReset();
    mutate.mockReset();
    success.mockReset();
  });

  it("lists users with their role, marks you, and shows who has signed in", () => {
    render(<UsersTab />);

    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("PMO manager")).toBeInTheDocument();
    expect(within(rows[0]).getByText("(you)")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Signed in")).toBeInTheDocument();
    expect(within(rows[1]).getByText("No role")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Not yet")).toBeInTheDocument();
  });

  it("shows why the last PMO manager cannot lose the role", async () => {
    changeRole.mockRejectedValueOnce(
      new ApiError(
        "boss@example.com is the last active PMO manager; make someone else a PMO manager first",
        409,
      ),
    );
    render(<UsersTab />);

    await userEvent.click(
      screen.getByRole("button", { name: "Change the role of Boss" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(changeRole).toHaveBeenCalledWith("u1", "pmo_manager");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "last active PMO manager",
    );
    expect(mutate).not.toHaveBeenCalled();
  });

  it("requires an email and a role to give access", async () => {
    render(<UsersTab />);

    await userEvent.click(screen.getByRole("button", { name: /Give access/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Not an email address")).toBeInTheDocument();
    expect(screen.getByText("Choose a role")).toBeInTheDocument();
    expect(grantRole).not.toHaveBeenCalled();
  });

  it("reports what a change did and refreshes the list", async () => {
    changeRole.mockResolvedValueOnce({
      user: { ...newcomer, role: null },
      message: "new@example.com: already without a role, nothing changed",
    });
    render(<UsersTab />);

    await userEvent.click(
      screen.getByRole("button", { name: "Change the role of new" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(mutate).toHaveBeenCalled());
    expect(changeRole).toHaveBeenCalledWith("u2", null);
    expect(success).toHaveBeenCalledWith(
      "new@example.com: already without a role, nothing changed",
    );
  });
});
