"""Institutional economic research commentary (Phase 3A).

A separate domain from the Stats NZ statistical pipeline: nothing in `adapters`, `pipeline`,
`validate`, `stats`, `insights`, `scheduler`, `api` or `publish` imports this package (a test
enforces it), and its tables are never read by the API or the public snapshot.
"""
