import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ErrorFallback } from "./ErrorFallback";

function makeError(message = "Test error"): Error & { digest?: string } {
  return new Error(message);
}

describe("ErrorFallback", () => {
  it("renders default title and error message", () => {
    render(
      <ErrorFallback error={makeError("Something broke")} reset={() => {}} />,
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Something broke")).toBeInTheDocument();
  });

  it("renders custom title", () => {
    render(
      <ErrorFallback
        error={makeError()}
        reset={() => {}}
        title="Failed to load placements"
      />,
    );
    expect(screen.getByText("Failed to load placements")).toBeInTheDocument();
  });

  it("renders custom description instead of error message", () => {
    render(
      <ErrorFallback
        error={makeError("original error")}
        reset={() => {}}
        description="Please try again later."
      />,
    );
    expect(screen.getByText("Please try again later.")).toBeInTheDocument();
    expect(screen.queryByText("original error")).not.toBeInTheDocument();
  });

  it("renders fallback text when error has no message", () => {
    const error = { message: undefined as unknown as string } as Error & {
      digest?: string;
    };
    render(<ErrorFallback error={error} reset={() => {}} />);
    expect(
      screen.getByText("An unexpected error occurred."),
    ).toBeInTheDocument();
  });

  it("calls reset when Try again button is clicked", async () => {
    const user = userEvent.setup();
    const reset = vi.fn();
    render(<ErrorFallback error={makeError()} reset={reset} />);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledOnce();
  });
});
