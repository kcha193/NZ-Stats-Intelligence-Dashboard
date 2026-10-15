import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/client";
import { QueryBoundary } from "./QueryBoundary";

const base = { data: undefined, error: null, isLoading: false, isError: false, refetch: vi.fn() };

describe("QueryBoundary", () => {
  it("shows a loading skeleton", () => {
    render(<QueryBoundary query={{ ...base, isLoading: true }}>{() => <p>data</p>}</QueryBoundary>);
    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
  });

  it("shows the error and a working retry", async () => {
    const refetch = vi.fn();
    render(
      <QueryBoundary
        query={{ ...base, isError: true, error: new ApiError(500, "boom"), refetch }}
      >
        {() => <p>data</p>}
      </QueryBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/boom/);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("shows the empty explanation when there is nothing to show", () => {
    render(
      <QueryBoundary
        query={{ ...base, data: [] }}
        isEmpty={(d: unknown[]) => d.length === 0}
        empty={<p>Nothing ingested yet</p>}
      >
        {() => <p>data</p>}
      </QueryBoundary>,
    );
    expect(screen.getByText("Nothing ingested yet")).toBeInTheDocument();
  });

  it("renders children with the data", () => {
    render(
      <QueryBoundary query={{ ...base, data: { n: 3 } }}>{(d: { n: number }) => <p>n={d.n}</p>}</QueryBoundary>,
    );
    expect(screen.getByText("n=3")).toBeInTheDocument();
  });
});
