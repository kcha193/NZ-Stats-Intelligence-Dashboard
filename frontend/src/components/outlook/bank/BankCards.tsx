import { useId } from "react";
import type { BankCard } from "@/api/bank";
import { formatCivilDate } from "@/lib/format";
import { CLAIM_LABELS, STATE_LABELS, STATE_SENTENCES } from "./labels";

function Card({ card }: { card: BankCard }) {
  const id = useId();
  return (
    <article aria-labelledby={id} className="flex flex-col gap-2 border-t pt-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={id} className="type-card">{card.name}</h3>
        <span className="rounded border px-1.5 py-0.5 text-xs text-muted-foreground">
          {STATE_LABELS[card.state]}{card.worst_series ? ` · ${card.worst_series}` : ""}
        </span>
      </header>
      {card.report_name && (
        <p className="text-sm text-muted-foreground">
          {card.report_name} <span aria-hidden>·</span> {formatCivilDate(card.published_on)}
        </p>
      )}
      {card.stance ? (
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{card.stance.label}</p>
          <p className="max-w-[60ch] text-sm leading-relaxed">{card.stance.text}</p>
          <p className="text-xs text-muted-foreground">{CLAIM_LABELS[card.stance.claim_status]}</p>
        </div>
      ) : (
        STATE_SENTENCES[card.state] && <p className="text-sm text-muted-foreground">{STATE_SENTENCES[card.state]}</p>
      )}
    </article>
  );
}

/** One card per bank: the newest report, the source's state, and the AI's reading of it, labelled as such. */
export function BankCards({ cards }: { cards: BankCard[] }) {
  return (
    <div className="grid gap-x-8 gap-y-6 md:grid-cols-2 xl:grid-cols-3">
      {cards.map((c) => <Card key={c.key} card={c} />)}
    </div>
  );
}
