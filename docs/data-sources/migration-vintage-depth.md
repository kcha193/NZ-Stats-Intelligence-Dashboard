# Migration release-file vintage depth

Probed 2026-07 down to 2020-09. 'ok' = file present and header has all expected columns.

| Release | Page | age/sex CSV | citizenship/visa/country CSV |
|---|---|---|---|
| 2026-07 | ok | ok | ok |
| 2026-06 | ok | ok | ok |
| 2026-05 | ok | ok | ok |
| 2026-04 | ok | ok | ok |
| 2026-03 | ok | ok | ok |
| 2026-02 | ok | ok | ok |
| 2026-01 | ok | ok | ok |
| 2025-12 | ok | ok | ok |
| 2025-11 | ok | ok | ok |
| 2025-10 | ok | ok | ok |
| 2025-09 | ok | ok | ok |
| 2025-08 | ok | ok | ok |
| 2025-07 | ok | ok | ok |
| 2025-06 | ok | ok | ok |
| 2025-05 | ok | ok | ok |
| 2025-04 | ok | ok | ok |
| 2025-03 | ok | ok | ok |
| 2025-02 | ok | ok | ok |
| 2025-01 | ok | ok | ok |
| 2024-12 | ok | ok | ok |
| 2024-11 | ok | ok | ok |
| 2024-10 | ok | ok | ok |
| 2024-09 | ok | ok | ok |
| 2024-08 | ok | ok | ok |
| 2024-07 | ok | ok | ok |
| 2024-06 | ok | ok | ok |
| 2024-05 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2024-04 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2024-03 | ok | ok | ok |
| 2024-02 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2024-01 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2023-12 | ok | ok | ok |
| 2023-11 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2023-10 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2023-09 | ok | ok | ok |
| 2023-08 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2023-07 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2023-06 | ok | ok | ok |
| 2023-05 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2023-04 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2023-03 | ok | ok | ok |
| 2023-02 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2023-01 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2022-12 | ok | ok | ok |
| 2022-11 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2022-10 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2022-09 | ok | ok | ok |
| 2022-08 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2022-07 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2022-06 | ok | ok | ok |
| 2022-05 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2022-04 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2022-03 | ok | ok | ok |
| 2022-02 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2022-01 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2021-12 | ok | ok | ok |
| 2021-11 | page 404 | - | - |
| 2021-10 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2021-09 | ok | ok | ok |
| 2021-08 | page 404 | - | - |
| 2021-07 | page 404 | - | - |
| 2021-06 | ok | ok | ok |
| 2021-05 | page 404 | - | - |
| 2021-04 | page 404 | - | - |
| 2021-03 | ok | ok | ok |
| 2021-02 | ok | MISSING/CHANGED (None) | MISSING/CHANGED (None) |
| 2021-01 | page 404 | - | - |
| 2020-12 | ok | ok | ok |
| 2020-11 | page 404 | - | - |
| 2020-10 | page 404 | - | - |
| 2020-09 | ok | ok | ok |

## Findings

Probed 2026-10-11. Both CSV downloads (age/sex and citizenship/visa/country) exist with the
expected column headers for **every release from June 2024 to July 2026 (26 consecutive
months)**. Earlier releases are patchy: only quarter-end months (March, June, September,
December) carry matching CSV links back to September 2020; the intervening monthly pages list
no matching CSV, and some pages from 2020-2021 return 404 under the current slug pattern.

Consequences: continuous vintage history (monthly) is reconstructable from June 2024
(`backfill_since = "2024-06"`). Quarter-end vintages before that exist but are not contiguous,
so revision history before June 2024 is incomplete and is reported as such rather than
reconstructed. The files also carry a `month_of_release` column per observation (when each
value was last published), which identifies when a value changed but not its earlier value.
