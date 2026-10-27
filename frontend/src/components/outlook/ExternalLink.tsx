import type { ReactNode } from "react";
import { safeHttpsUrl } from "@/lib/research";

export function ExternalLink({ href, children, className = "" }: { href: string | null | undefined; children: ReactNode; className?: string }) {
  const safe = safeHttpsUrl(href);
  if (!safe) return <span className={className}>{children}</span>;
  return (
    <a href={safe} target="_blank" rel="noopener noreferrer" className={`underline underline-offset-4 hover:text-foreground ${className}`}>
      {children}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}
