"""All in-process acceptance tests must work without network access."""

import socket
import sys
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    connect = socket.socket.connect
    socketpair = getattr(socket, "_fallback_socketpair", None)

    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("Network access is forbidden in M0 tests")

    def connect_self_pipe(sock: socket.socket, address: tuple[str, int]) -> None:
        # Windows asyncio uses Python's socketpair fallback to wake its own loop.
        if (
            sys.platform == "win32"
            and socketpair is not None
            and isinstance(address, tuple)
            and address[0] in ("127.0.0.1", "::1")
            and sys._getframe(1).f_code is socketpair.__code__
        ):
            connect(sock, address)
            return
        blocked()

    monkeypatch.setattr(socket.socket, "connect", connect_self_pipe)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    yield
