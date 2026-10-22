import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Overview", end: true },
  { to: "/migration", label: "Migration" },
  { to: "/inflation", label: "Inflation" },
  { to: "/electronic-card-transactions", label: "Card spending" },
  { to: "/calendar", label: "Release calendar" },
  { to: "/health", label: "Data health" },
];

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="border-b print:hidden">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 lg:px-6">
          <span className="text-base font-semibold tracking-tight">NZ Stats Intelligence</span>
          <nav aria-label="Primary" className="-mx-1 flex gap-1 overflow-x-auto">
            {LINKS.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  `rounded px-2 py-1 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 ${
                    isActive ? "bg-muted font-medium" : "text-muted-foreground hover:text-foreground"
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-[1400px] px-4 py-6 lg:px-6">
        {children}
      </main>
      <footer className="border-t print:border-0">
        <p className="mx-auto max-w-[1400px] px-4 py-4 text-xs text-muted-foreground lg:px-6">
          Source: Stats NZ (stats.govt.nz), licensed under Creative Commons Attribution 4.0
          (CC BY 4.0). This dashboard is independent and not endorsed by Stats NZ.
        </p>
      </footer>
    </div>
  );
}
