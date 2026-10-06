import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renders title", () => {
    render(<EmptyState title="No placements found" />);
    expect(screen.getByText("No placements found")).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    render(
      <EmptyState
        title="No data"
        description="Add a placement to get started."
      />,
    );
    expect(
      screen.getByText("Add a placement to get started."),
    ).toBeInTheDocument();
  });

  it("does not render description when omitted", () => {
    const { container } = render(<EmptyState title="Empty" />);
    expect(container.querySelectorAll("p")).toHaveLength(0);
  });

  it("renders link action when href is provided", () => {
    render(
      <EmptyState
        title="No placements"
        action={{ label: "Add placement", href: "/admin" }}
      />,
    );
    const link = screen.getByRole("link", { name: "Add placement" });
    expect(link).toHaveAttribute("href", "/admin");
  });

  it("renders button action when onClick is provided", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <EmptyState
        title="No results"
        action={{ label: "Try again", onClick }}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("does not render action when omitted", () => {
    render(<EmptyState title="Nothing here" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
