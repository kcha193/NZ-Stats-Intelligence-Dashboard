"""What research fetching may request: URL/host rules (SSRF) and robots.txt.

Both are pure and offline-testable. `HostPolicy.check` is the single gate every URL passes before a
request, including each redirect hop. Robots rules follow the usual (Google) semantics: the most
specific user-agent group, the longest matching pattern wins, Allow wins a tie, `*` and `$` work.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable, Sequence
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

Resolver = Callable[[str], Sequence[str]]

_TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|mc_cid|mc_eid|_hsenc|_hsmi|hsa_.*)$", re.IGNORECASE)
_LOCAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home.arpa")
_BAD_CHARS = re.compile(r"[\x00-\x20\x7f\\]")
ROBOTS_MAX_CHARS = 512 * 1024


class UnsafeUrl(ValueError):
    """A URL research fetching must not request. The message is fixed wording, safe to store."""


def system_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return sorted({info[4][0].split("%", 1)[0] for info in infos})


def _is_public(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global


def _split(url: str):
    if not isinstance(url, str) or not url or _BAD_CHARS.search(url):
        raise UnsafeUrl("malformed url")
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018  (raises ValueError for an invalid port)
    except ValueError:
        raise UnsafeUrl("malformed url") from None
    return parts


_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")


def canonical_path(path: str) -> str:
    """The path as a server will most likely read it, for prefix and robots matching.

    Escaped unreserved characters are decoded (`%70` is `p`), the other escapes are upper-cased, and runs
    of slashes collapse, so `/%70rivate/` and `//private/` cannot slip past a rule written for `/private/`.
    """

    def fix(m: re.Match[str]) -> str:
        char = chr(int(m.group(1), 16))
        return char if char in _UNRESERVED else f"%{m.group(1).upper()}"

    return re.sub(r"/{2,}", "/", _ESCAPE.sub(fix, path))


def normalise_url(url: str) -> str:
    """Stable identity for a document: scheme/host lowercased, default port, fragment, trailing slash
    and tracking parameters removed, remaining query sorted."""
    parts = _split(url)
    host = (parts.hostname or "").rstrip(".")
    if not host or not parts.scheme:
        raise UnsafeUrl("malformed url")
    port = f":{parts.port}" if parts.port not in (None, 443) else ""
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k)
    )
    return urlunsplit((parts.scheme.lower(), f"{host}{port}", path, urlencode(query), ""))


class HostPolicy:
    def __init__(
        self,
        allowed_hosts: Sequence[str],
        *,
        allowed_path_prefixes: Sequence[str] = (),
        blocked_path_prefixes: Sequence[str] = (),
        resolver: Resolver | None = system_resolver,
    ) -> None:
        self._hosts = frozenset(h.lower() for h in allowed_hosts)
        self._allowed = tuple(allowed_path_prefixes)
        self._blocked = tuple(blocked_path_prefixes)
        self._resolver = resolver

    def check(self, url: str) -> str:
        """The normalised URL if it may be requested; otherwise raises `UnsafeUrl`."""
        parts = _split(url)
        if parts.scheme.lower() != "https":
            raise UnsafeUrl("not https")
        if parts.username is not None or parts.password is not None:
            raise UnsafeUrl("url has credentials")
        if parts.port not in (None, 443):
            raise UnsafeUrl("non-standard port")
        host = (parts.hostname or "").rstrip(".").lower()
        if host not in self._hosts:
            raise UnsafeUrl("host is not on the allowlist")
        if "." not in host or host.endswith(_LOCAL_SUFFIXES):
            raise UnsafeUrl("local host name")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise UnsafeUrl("ip address literal")
        self._check_path(canonical_path(parts.path))
        self._check_addresses(host)
        return normalise_url(url)

    def _check_path(self, path: str) -> None:
        decoded = unquote(path)
        if "\\" in decoded or any(seg in ("..", ".") for seg in decoded.split("/")):
            raise UnsafeUrl("path traversal")
        if self._allowed and not any(path.startswith(p) for p in self._allowed):
            raise UnsafeUrl("path is outside the allowed prefixes")
        folded = path.lower()
        if any(folded.startswith(p.lower()) for p in self._blocked):
            raise UnsafeUrl("path is blocked")

    def _check_addresses(self, host: str) -> None:
        if self._resolver is None:
            return
        try:
            addresses = list(self._resolver(host))
        except OSError:
            raise UnsafeUrl("host does not resolve") from None
        if not addresses or not all(_is_public(a) for a in addresses):
            raise UnsafeUrl("host resolves to a non-public address")


class RobotsRules:
    """Parsed rules for one user agent."""

    def __init__(self, rules: dict[str, bool], crawl_delay: float | None = None) -> None:
        self._rules = rules  # pattern -> allow
        self.crawl_delay = crawl_delay
        self._compiled: dict[str, re.Pattern[str]] = {}

    @classmethod
    def parse(cls, text: str, agent: str) -> RobotsRules:
        groups: list[dict] = []
        current: dict | None = None
        last_was_rule = True
        for raw in text[:ROBOTS_MAX_CHARS].lstrip("﻿").splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field, value = (p.strip() for p in line.split(":", 1))
            field = field.lower()
            if field == "user-agent":
                if current is None or last_was_rule:
                    current = {"agents": set(), "rules": {}, "delay": None}
                    groups.append(current)
                current["agents"].add(value.lower())
                last_was_rule = False
            elif field in ("allow", "disallow") and current is not None:
                last_was_rule = True
                if value:  # an empty Disallow means "allow everything"
                    allow = field == "allow"
                    rules = current["rules"]
                    rules[value] = rules.get(value, False) or allow
            elif field == "crawl-delay" and current is not None:
                last_was_rule = True
                try:
                    current["delay"] = float(value)
                except ValueError:
                    pass
        return cls._select(groups, agent.lower())

    @classmethod
    def _select(cls, groups: list[dict], agent: str) -> RobotsRules:
        best, chosen = 0, []
        for group in groups:
            score = max((len(a) for a in group["agents"] if a != "*" and a in agent), default=0)
            if score > best:
                best, chosen = score, [group]
            elif score == best and score > 0:
                chosen.append(group)
        if not chosen:
            chosen = [g for g in groups if "*" in g["agents"]]
        rules: dict[str, bool] = {}
        delay = None
        for group in chosen:
            for pattern, allow in group["rules"].items():
                rules[pattern] = rules.get(pattern, False) or allow
            delay = group["delay"] if group["delay"] is not None else delay
        return cls(rules, delay)

    def allowed(self, path_and_query: str) -> bool:
        best_len, verdict = -1, True
        for pattern, allow in self._rules.items():
            if self._matches(pattern, path_and_query) and (
                len(pattern) > best_len or (len(pattern) == best_len and allow)
            ):
                best_len, verdict = len(pattern), allow
        return verdict

    def _matches(self, pattern: str, target: str) -> bool:
        if "*" not in pattern and not pattern.endswith("$"):
            return target.startswith(pattern)
        regex = self._compiled.get(pattern)
        if regex is None:
            anchored = pattern.endswith("$")
            body = ".*".join(re.escape(p) for p in pattern.removesuffix("$").split("*"))
            regex = self._compiled[pattern] = re.compile(body + ("$" if anchored else ""))
        return regex.match(target) is not None


ALLOW_ALL = RobotsRules({})
DENY_ALL = RobotsRules({"/": False})
