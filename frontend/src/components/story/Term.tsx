import type { ReactNode } from "react";
import { Popover } from "@base-ui/react/popover";
import { GLOSSARY, type TermKey } from "@/stories/glossary";

/**
 * An inline explainer. A click or tap (not hover) opens it, so it works on touch screens and from the keyboard; Escape
 * and a click outside close it, and focus returns to the term.
 */
export function Term({ k, children }: { k: TermKey; children?: ReactNode }) {
  const g = GLOSSARY[k];
  return (
    <Popover.Root>
      <Popover.Trigger
        className="cursor-help rounded-sm text-left underline decoration-dotted decoration-1 underline-offset-[3px] hover:decoration-solid focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-ink"
      >
        {children ?? g.term}
        <span className="sr-only">: what does this mean?</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={8} collisionPadding={16} className="z-50">
          <Popover.Popup className="w-[min(22rem,calc(100vw-2rem))] rounded-md border bg-popover p-4 text-popover-foreground shadow-[0_16px_40px_-20px_rgb(15_23_42/0.35)] outline-none data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 transition-opacity duration-150">
            <Popover.Title className="font-display text-sm font-semibold tracking-tight">{g.term}</Popover.Title>
            <Popover.Description className="mt-1 text-sm leading-relaxed text-muted-foreground">{g.body}</Popover.Description>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** "Key terms" strip: each term opens its explainer. Shown near the finding, not as a glossary wall. */
export function KeyTerms({ keys, className = "" }: { keys: TermKey[]; className?: string }) {
  if (!keys.length) return null;
  return (
    <div className={`flex flex-wrap items-baseline gap-x-3 gap-y-1.5 text-sm ${className}`}>
      <span className="text-xs font-medium text-muted-foreground">Key terms</span>
      {keys.map((k) => <Term key={k} k={k} />)}
    </div>
  );
}
