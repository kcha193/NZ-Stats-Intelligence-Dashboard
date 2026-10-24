/**
 * The public address links and exports should point at. A static build sets VITE_SITE_URL to the canonical origin so a
 * link copied from a deploy preview or the netlify.app alias still names the real site; everywhere else it is the
 * address the page was opened at.
 */
export function siteOrigin(): string {
  const configured = (import.meta.env.VITE_SITE_URL as string | undefined)?.trim().replace(/\/+$/, "");
  return configured || window.location.origin;
}

export const absoluteUrl = (path: string): string => `${siteOrigin()}${path.startsWith("/") ? path : `/${path}`}`;
