import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Layout } from "./Layout";

describe("Layout", () => {
  it("has landmarks, a skip link, navigation and the licence attribution", () => {
    render(
      <MemoryRouter initialEntries={["/migration"]}>
        <Layout>
          <p>content</p>
        </Layout>
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: /skip to content/i })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("main")).toHaveTextContent("content");
    const nav = screen.getByRole("navigation", { name: /primary/i });
    expect(nav).toHaveTextContent(/overview/i);
    expect(screen.getByRole("link", { name: /migration/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("contentinfo")).toHaveTextContent(/CC BY 4\.0/);
  });
});
