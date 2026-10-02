import socket


def test_connection(host: str, port: int = 9100, timeout: float = 5.0) -> None:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)


def send_zpl(host: str, zpl: str, port: int = 9100, timeout: float = 5.0) -> None:
    if not host:
        raise ValueError("printer host is required")
    payload = zpl.encode("utf-8")
    with socket.create_connection((host, int(port)), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload)
