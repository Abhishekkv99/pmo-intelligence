import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { DateRangeFilter } from "./DateRangeFilter";

describe("DateRangeFilter", () => {
  const defaultProps = {
    dateFrom: "",
    dateTo: "",
    onDateFromChange: vi.fn(),
    onDateToChange: vi.fn(),
    onClear: vi.fn(),
  };

  it("renders From and To date inputs", () => {
    render(<DateRangeFilter {...defaultProps} />);

    expect(screen.getByLabelText("From")).toBeInTheDocument();
    expect(screen.getByLabelText("To")).toBeInTheDocument();
  });

  it("does not show Clear button when no dates are set", () => {
    render(<DateRangeFilter {...defaultProps} />);

    expect(screen.queryByText("Clear dates")).not.toBeInTheDocument();
  });

  it("shows Clear button when dateFrom is set", () => {
    render(<DateRangeFilter {...defaultProps} dateFrom="2026-01-01" />);

    expect(screen.getByText("Clear dates")).toBeInTheDocument();
  });

  it("shows Clear button when dateTo is set", () => {
    render(<DateRangeFilter {...defaultProps} dateTo="2026-01-31" />);

    expect(screen.getByText("Clear dates")).toBeInTheDocument();
  });

  it("calls onDateFromChange when From input changes", () => {
    const onDateFromChange = vi.fn();
    render(
      <DateRangeFilter {...defaultProps} onDateFromChange={onDateFromChange} />,
    );

    fireEvent.change(screen.getByLabelText("From"), {
      target: { value: "2026-02-01" },
    });

    expect(onDateFromChange).toHaveBeenCalledWith("2026-02-01");
  });

  it("calls onDateToChange when To input changes", () => {
    const onDateToChange = vi.fn();
    render(
      <DateRangeFilter {...defaultProps} onDateToChange={onDateToChange} />,
    );

    fireEvent.change(screen.getByLabelText("To"), {
      target: { value: "2026-02-28" },
    });

    expect(onDateToChange).toHaveBeenCalledWith("2026-02-28");
  });

  it("calls onClear when Clear button is clicked", () => {
    const onClear = vi.fn();
    render(
      <DateRangeFilter
        {...defaultProps}
        dateFrom="2026-01-01"
        dateTo="2026-01-31"
        onClear={onClear}
      />,
    );

    fireEvent.click(screen.getByText("Clear dates"));

    expect(onClear).toHaveBeenCalledOnce();
  });

  it("displays current date values in inputs", () => {
    render(
      <DateRangeFilter
        {...defaultProps}
        dateFrom="2026-03-01"
        dateTo="2026-03-31"
      />,
    );

    expect(screen.getByLabelText("From")).toHaveValue("2026-03-01");
    expect(screen.getByLabelText("To")).toHaveValue("2026-03-31");
  });
});
