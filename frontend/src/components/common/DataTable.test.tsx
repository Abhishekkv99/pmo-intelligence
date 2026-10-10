import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "./DataTable";

interface Row {
  name: string;
  city: string;
}

const columns: ColumnDef<Row>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "city", header: "City" },
];

const data: Row[] = [
  { name: "Asha", city: "Leeds" },
  { name: "Ben", city: "Bristol" },
];

function cellTexts(): string[] {
  return screen
    .getAllByRole("row")
    .slice(1)
    .map((row) => row.textContent ?? "");
}

describe("DataTable", () => {
  it("filters rows on any column's text", async () => {
    render(
      <DataTable
        columns={columns}
        data={data}
        searchPlaceholder="Search people"
        emptyMessage="Nobody"
      />,
    );

    await userEvent.type(screen.getByLabelText("Search people"), "brist");

    expect(cellTexts()).toEqual(["BenBristol"]);
  });

  it("sorts by a column when its header is clicked", async () => {
    render(
      <DataTable
        columns={columns}
        data={data}
        searchPlaceholder="Search"
        emptyMessage="Nobody"
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "City" }));

    expect(cellTexts()).toEqual(["BenBristol", "AshaLeeds"]);
  });

  it("keeps the given order with plain headers when not sortable", () => {
    render(
      <DataTable
        columns={columns}
        data={data}
        searchPlaceholder="Search"
        emptyMessage="Nobody"
        sortable={false}
      />,
    );

    expect(screen.queryByRole("button", { name: "City" })).toBeNull();
    expect(screen.getByRole("columnheader", { name: "City" })).toBeVisible();
    expect(cellTexts()).toEqual(["AshaLeeds", "BenBristol"]);
  });

  it("shows the empty message, or loading while loading", () => {
    const { rerender } = render(
      <DataTable
        columns={columns}
        data={[]}
        searchPlaceholder="Search"
        emptyMessage="Nobody yet"
      />,
    );
    expect(screen.getByText("Nobody yet")).toBeInTheDocument();

    rerender(
      <DataTable
        columns={columns}
        data={[]}
        searchPlaceholder="Search"
        emptyMessage="Nobody yet"
        isLoading
      />,
    );
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });
});
