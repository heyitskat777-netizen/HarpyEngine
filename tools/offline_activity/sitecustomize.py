"""Allow only local socket connections in synthetic Activity test processes."""

import ipaddress
import os
import socket

if os.environ.get("HARPY_ACTIVITY_LOOPBACK_ONLY") == "1":

    def require_loopback(host):
        if isinstance(host, bytes):
            host = host.decode()
        if host == "localhost":
            return
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except (TypeError, ValueError):
            pass
        raise AssertionError("Only loopback traffic is allowed in offline Activity tests.")

    def restrict_connect(original):
        def guarded(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                require_loopback(address[0])
            return original(sock, address)

        return guarded

    original_getaddrinfo = socket.getaddrinfo

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host is not None:
            require_loopback(host)
        return original_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = guarded_getaddrinfo
    socket.socket.connect = restrict_connect(socket.socket.connect)
    socket.socket.connect_ex = restrict_connect(socket.socket.connect_ex)
