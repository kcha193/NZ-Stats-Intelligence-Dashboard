type Item = { institution_key: string; reason: string };

/**
 * What an analysis left out and why, by bank. The reasons are fixed server wording, never document text. A figure that
 * is not shown is never silently dropped: this list is how the reader learns that a number is missing on purpose.
 */
export function BankLeftOut({ items, names }: { items: Item[]; names: Record<string, string> }) {
  const unique = items.filter((e, i) => items.findIndex((o) => o.institution_key === e.institution_key && o.reason === e.reason) === i);
  if (unique.length === 0) return null;
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-muted-foreground">Left out ({unique.length})</summary>
      <ul className="mt-2 space-y-1">
        {unique.map((e) => (
          <li key={`${e.institution_key}|${e.reason}`}>{names[e.institution_key] ?? e.institution_key}: {e.reason}</li>
        ))}
      </ul>
    </details>
  );
}
