import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LogoMark, Wordmark } from "./Logo";

describe("LogoMark", () => {
  it("is an image named after the product", () => {
    render(<LogoMark />);

    expect(
      screen.getByRole("img", { name: "PMO Intelligence" }),
    ).toBeInTheDocument();
  });

  it("is hidden from assistive technology when decorative", () => {
    const { container } = render(<LogoMark decorative />);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(container.querySelector("svg")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });

  it("gives each mark its own gradient", () => {
    const { container } = render(
      <>
        <LogoMark />
        <LogoMark />
      </>,
    );

    const ids = Array.from(container.querySelectorAll("linearGradient")).map(
      (gradient) => gradient.id,
    );
    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(2);
    container.querySelectorAll("svg").forEach((svg, index) => {
      expect(svg.querySelectorAll("rect")[1]).toHaveAttribute(
        "fill",
        `url(#${ids[index]})`,
      );
    });
  });
});

describe("Wordmark", () => {
  it("shows the product name once, with a decorative mark, and no heading", () => {
    render(<Wordmark />);

    expect(screen.getByText("PMO Intelligence")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });
});
