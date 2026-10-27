import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { ChevronDown, Menu, X } from "lucide-react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { isStaticMode } from "@/api/mode";
import { SnapshotStamp } from "@/components/SnapshotStamp";

type Dest = { to: string; label: string; note: string; end?: boolean };

/** Reading destinations come first; every dashboard, the calendar and data health stay one click from any page. */
const PRIMARY: Dest[] = [
  { to: "/", label: "Home", note: "Today's findings", end: true },
  { to: "/economic-outlook", label: "Outlook", note: "Indicators beside institutional forecasts" },
  { to: "/stories", label: "Stories", note: "Every finding, one per page" },
];
const EXPLORE: { group: string; links: Dest[] }[] = [
  {
    group: "Dashboards",
    links: [
      { to: "/inflation", label: "Inflation", note: "Consumers price index, quarterly" },
      { to: "/electronic-card-transactions", label: "Card spending", note: "Electronic card transactions, monthly" },
      { to: "/migration", label: "Migration", note: "International migration, monthly" },
    ],
  },
  {
    group: "Releases and data quality",
    links: [
      { to: "/calendar", label: "Release calendar", note: "What Stats NZ publishes next" },
      { to: "/health", label: "Data health", note: "Ingestion and freshness checks" },
    ],
  },
];
const EXPLORE_PATHS = EXPLORE.flatMap((g) => g.links.map((l) => l.to));

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `relative whitespace-nowrap rounded-sm px-2.5 py-2 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-ink ${
    isActive
      ? "font-medium text-foreground after:absolute after:inset-x-2.5 after:-bottom-[13px] after:h-0.5 after:bg-accent-ink"
      : "text-muted-foreground hover:text-foreground"
  }`;

function MenuLink({ d }: { d: Dest }) {
  return (
    <NavLink
      to={d.to}
      end={d.end}
      className={({ isActive }) =>
        `group block rounded-sm px-3 py-2.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-ink ${
          isActive ? "bg-accent-wash" : "hover:bg-muted"
        }`
      }
    >
      {({ isActive }) => (
        <>
          <span className={`block text-sm ${isActive ? "font-semibold text-accent-ink" : "font-medium"}`}>{d.label}</span>
          <span className="block text-xs text-muted-foreground">{d.note}</span>
        </>
      )}
    </NavLink>
  );
}

/**
 * Disclosure navigation (a button that shows a list of links), not an ARIA menu: links keep their native keyboard
 * behaviour. Escape closes and returns focus to the button; so do a click outside and a route change.
 */
function ExploreDisclosure() {
  // Open "at" a path: following a link changes the path, which closes the panel without an extra render.
  const [openAt, setOpenAt] = useState<string | null>(null);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const { pathname } = useLocation();
  const open = openAt === pathname;
  const setOpen = (next: boolean | ((o: boolean) => boolean)) =>
    setOpenAt((typeof next === "function" ? next(open) : next) ? pathname : null);
  const inExplore = EXPLORE_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpenAt(null);
        button.current?.focus();
      }
    };
    const onPointer = (e: PointerEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpenAt(null);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  return (
    <div ref={root} className="sm:relative">
      <button
        ref={button}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className={`relative flex items-center gap-1.5 whitespace-nowrap rounded-sm px-2.5 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-ink ${
          inExplore || open ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground"
        } ${inExplore ? "sm:after:absolute sm:after:inset-x-2.5 sm:after:-bottom-[13px] sm:after:h-0.5 sm:after:bg-accent-ink" : ""}`}
      >
        <span className="sm:hidden" aria-hidden>{open ? <X className="size-4" /> : <Menu className="size-4" />}</span>
        <span>
          <span className="sm:hidden">Menu</span>
          <span className="sr-only sm:not-sr-only">{" "}Explore data</span>
        </span>
        <ChevronDown aria-hidden className={`hidden size-3.5 transition-transform sm:block ${open ? "rotate-180" : ""}`} />
        {inExplore && <span className="sr-only"> (current section)</span>}
      </button>
      <div
        id={id}
        hidden={!open}
        className="absolute inset-x-0 top-full z-40 border-b bg-background shadow-[0_12px_32px_-16px_rgb(15_23_42/0.25)] sm:inset-x-auto sm:right-0 sm:mt-3 sm:w-[30rem] sm:rounded-md sm:border"
      >
        <div className="grid gap-4 p-3 sm:grid-cols-2">
          <ul className="space-y-0.5 sm:hidden" aria-label="Read">
            {PRIMARY.map((d) => <li key={d.to}><MenuLink d={d} /></li>)}
          </ul>
          {EXPLORE.map((g) => (
            <div key={g.group}>
              <p className="px-3 pb-1 text-xs font-medium text-muted-foreground">{g.group}</p>
              <ul className="space-y-0.5" aria-label={g.group}>
                {g.links.map((d) => <li key={d.to}><MenuLink d={d} /></li>)}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header role="banner" className="relative z-30 border-b bg-background print:hidden">
        <div className="mx-auto flex h-16 max-w-[1320px] items-center justify-between gap-4 px-4 lg:px-8">
          <Link to="/" className="flex items-baseline gap-1.5 rounded-sm font-display text-[1.0625rem] tracking-tight focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent-ink">
            <span className="font-bold">NZ Stats</span>
            <span className="font-normal text-muted-foreground">Intelligence</span>
          </Link>
          <nav aria-label="Primary" className="flex items-center gap-1">
            <ul className="hidden items-center gap-1 sm:flex">
              {PRIMARY.map((d) => (
                <li key={d.to}><NavLink to={d.to} end={d.end} className={linkClass}>{d.label}</NavLink></li>
              ))}
            </ul>
            <ExploreDisclosure />
          </nav>
        </div>
      </header>
      {isStaticMode() && <SnapshotStamp />}
      <main id="main" className="mx-auto max-w-[1320px] px-4 py-6 lg:px-8 lg:py-8">
        {children}
      </main>
      <footer className="border-t bg-surface-sunken print:border-0 print:bg-transparent">
        <div className="mx-auto grid max-w-[1320px] gap-6 px-4 py-8 text-xs text-muted-foreground sm:grid-cols-[1fr_auto] lg:px-8">
          <p className="max-w-[70ch] leading-relaxed">
            Source: Stats NZ (stats.govt.nz), licensed under Creative Commons Attribution 4.0
            (CC BY 4.0). This dashboard is independent and not endorsed by Stats NZ. Figures are shown as published;
            each story names its release, reference period and status.
          </p>
          <ul className="flex flex-wrap gap-x-4 gap-y-1 print:hidden" aria-label="All pages">
            {[...PRIMARY, ...EXPLORE.flatMap((g) => g.links)].map((d) => (
              <li key={d.to}><Link className="underline-offset-4 hover:text-foreground hover:underline" to={d.to}>{d.label}</Link></li>
            ))}
          </ul>
        </div>
      </footer>
    </div>
  );
}
