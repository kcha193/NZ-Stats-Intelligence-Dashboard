"""A child target that dies without reporting (as a segfault or OOM kill would). Synthetic test support only."""

import os


def die(*_args) -> None:
    os._exit(3)
