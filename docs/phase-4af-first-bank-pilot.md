# Phase 4AF: recommended first-bank pilot

**No live ingestion exists for any bank and no permission field was changed.** This is a recommendation for the owner to
accept, adjust or refuse. Nothing here has been started.

## Recommendation: ANZ New Zealand, one hand-saved Quarterly Economic Outlook, table parsing only

Why ANZ: it is the only bank whose landing page, robots and terms were all read directly; robots has no Disallow; the report
URL shape (`ANZ-QEO-YYYYMMDD.pdf`) and cadence are known; and the PDF is a quarterly outlook, which is the only report kind
that feeds consensus and revisions. Why not the others: ASB's PDFs are robots-disallowed and its terms unread; Westpac returned
403 and its terms are unread; BNZ and Kiwibank have no evidence. Why table parsing only and no model: it is deterministic,
needs no model permission, and can be checked cell by cell by a person.

## Exact conditions for the first live pilot

All must hold; none is met today.

1. **Terms.** The owner has read the ANZ site terms in a browser and recorded the clauses and date, and has decided, ideally
   with ANZ's written confirmation, that a hand-saved copy parsed locally for internal analysis is within "reproduce and store
   solely for viewing" and "not displayed or distributed in public". The registry's `access_notes` records the decision.
2. **Registry (a reviewed change, by the owner).** For `anz` only: `manual_import = approved` with approver, date and note, and
   `content_policy = full_text`. `review_status` stays `needs_review` (no crawler), `llm_processing` stays `denied`,
   `hosted` stays denied, `public_display` stays none. The `PRE_APPROVAL_SHA256` pin in
   `tests/research/test_phase_4x_readiness.py` is updated in the same change, with the diff shown key by key.
3. **One report.** The owner saves one current quarterly outlook PDF in a browser and imports it with `research import`
   (a named importer and a note). No script fetches anything.
4. **Dry run.** `research tables extract VERSION --dry-run` shows the counts. Expect rejections on the first real layout; they
   are information. If the tables of interest are all rejected, stop: the interpreter needs a documented change (new
   fixture, failing test first), not a looser rule.
5. **Human check.** Extract, then check **every** stored figure against the PDF by eye (indicator, period, unit, value, and
   that actuals are not forecasts). Record the result. Any wrong figure stops the pilot and becomes a failing test.
6. **Gate.** The loopback dashboard with the owner's `auto_display` on shows the figures under "Bank outlooks"; confirm the
   evidence drawer's page and row and that nothing appears on the public site, a snapshot or another machine.
7. **Revocation rehearsed.** `research purge anz --version N` dry run reviewed; the owner knows it removes the figures.
8. **No model.** No `research summarise` for ANZ, no consent, no policy scope. Local or hosted model reading of ANZ text is a
   separate decision after the table path has been judged.

Out of scope for the pilot: scheduling, the crawler, a second bank, HTML tables, and any hosted processing.

## After the pilot

If the figures match the PDF, run the same checklist for a second quarterly outlook from ANZ to exercise revisions, then decide
the model-reading question separately. If they do not, record what the layout does and add it as a synthetic fixture first.
