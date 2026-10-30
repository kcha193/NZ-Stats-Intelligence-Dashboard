"""Operational monitoring (Phase 4F): is the dashboard running, collecting and backed up?

`recorder` is the only writer of heartbeat state (the serve process). `health` is read-only and is shared by the
`status` command, the `/api/ops/status` endpoint and `alerts`. Nothing here contacts a network.
"""
