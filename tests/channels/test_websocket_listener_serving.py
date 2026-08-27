"""Regression tests for the WebSocket listener serving-state predicate.

macOS cannot read SO_ACCEPTCONN via getsockopt (raises ENOPROTOOPT), so the
predicate must fall back to ``Server.is_serving()`` instead of treating the
platform limitation as a dead listener.
"""

import errno

from nanobot.channels.websocket.runtime import WebSocketChannel


class _MacSocket:
    """Mimics asyncio.TransportSocket.getsockopt behaviour on macOS."""

    def fileno(self) -> int:
        return 7

    def getsockopt(self, level: int, optname: int) -> int:
        raise OSError(errno.ENOPROTOOPT, "Protocol not available")


class _Server:
    def __init__(self, sockets: list[_MacSocket]) -> None:
        self.sockets = tuple(sockets)

    def is_serving(self) -> bool:
        return True


def test_listener_is_serving_treats_enoprotoopt_as_serving() -> None:
    assert WebSocketChannel._listener_is_serving(_Server([_MacSocket()])) is True


def test_listener_is_serving_rejects_closed_sockets() -> None:
    class _ClosedSocket(_MacSocket):
        def fileno(self) -> int:
            return -1

    assert WebSocketChannel._listener_is_serving(_Server([_ClosedSocket()])) is False


def test_listener_is_serving_rejects_other_socket_errors() -> None:
    class _BrokenSocket(_MacSocket):
        def getsockopt(self, level: int, optname: int) -> int:
            raise OSError(errno.EBADF, "Bad file descriptor")

    assert WebSocketChannel._listener_is_serving(_Server([_BrokenSocket()])) is False
