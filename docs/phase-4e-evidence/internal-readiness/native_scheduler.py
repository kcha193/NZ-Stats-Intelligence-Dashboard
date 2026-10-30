"""Run the real `nzstats serve` (scheduler ON) with all non-loopback networking refused in-process.

Native stand-in for the Docker smoke's `--network none`: DNS lookups and connections to anything other than
loopback raise before a packet leaves the host, and every refusal is logged so the run can prove it.
"""

import logging
import socket
import sys

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
log = logging.getLogger("netguard")
_getaddrinfo = socket.getaddrinfo
_connect = socket.socket.connect


def guarded_getaddrinfo(host, *args, **kwargs):
    if host is not None and str(host) not in LOOPBACK:
        log.warning("NETGUARD refused DNS lookup for %s", host)
        raise socket.gaierror(socket.EAI_NONAME, "network disabled by native smoke")
    return _getaddrinfo(host, *args, **kwargs)


def guarded_connect(self, address):
    if isinstance(address, tuple) and str(address[0]) not in LOOPBACK:
        log.warning("NETGUARD refused connection to %s", address[0])
        raise ConnectionRefusedError("network disabled by native smoke")
    return _connect(self, address)


socket.getaddrinfo = guarded_getaddrinfo
socket.socket.connect = guarded_connect

from nzstats.cli import main  # noqa: E402  (import after the guard is installed)

sys.exit(main(["serve", "--host", "127.0.0.1", "--port", sys.argv[1]]))
