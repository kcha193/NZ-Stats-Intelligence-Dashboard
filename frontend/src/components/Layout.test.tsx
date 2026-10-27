import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Layout } from "./Layout";

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Layout>
        <p>content</p>
      </Layout>
    </MemoryRouter>,
  );

describe("Layout", () => {
  it("has landmarks, a skip link, reading-first navigation and the licence attribution", () => {
    renderAt("/");
    expect(screen.getByRole("link", { name: /skip to content/i })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("main")).toHaveTextContent("content");
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Stories" })).toHaveAttribute("href", "/stories");
    expect(within(nav).getByRole("button", { name: /explore data/i })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("contentinfo")).toHaveTextContent(/CC BY 4\.0/);
  });

  it("keeps every dashboard, the calendar and data health one disclosure away, and marks the current one", async () => {
    const user = userEvent.setup();
    renderAt("/migration");
    const nav = screen.getByRole("navigation", { name: "Primary" });
    const button = within(nav).getByRole("button", { name: /explore data/i });
    expect(button).toHaveAccessibleName(/current section/);
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    for (const [name, href] of [["Inflation", "/inflation"], ["Card spending", "/electronic-card-transactions"], ["Migration", "/migration"],
      ["Release calendar", "/calendar"], ["Data health", "/health"]]) {
      expect(within(nav).getByRole("link", { name: new RegExp(`^${name}`) })).toHaveAttribute("href", href);
    }
    expect(within(nav).getByRole("link", { name: /^Migration/ })).toHaveAttribute("aria-current", "page");
  });

  it("closes the disclosure with Escape and returns focus to its button", async () => {
    const user = userEvent.setup();
    renderAt("/");
    const button = screen.getByRole("button", { name: /explore data/i });
    await user.click(button);
    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveFocus();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).queryByRole("link", { name: /^Release calendar/ })).toBeNull();
  });

  it("lists every destination in the footer, so no page depends on the disclosure", () => {
    renderAt("/");
    const all = screen.getByRole("list", { name: "All pages" });
    expect(within(all).getAllByRole("link")).toHaveLength(8);
  });
});
