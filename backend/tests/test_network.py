import socket
import threading

from app.services.printing import send_zpl


def test_real_tcp_receives_complete_zpl():
    received = bytearray()
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(5)

        def receiver():
            with server.accept()[0] as connection:
                connection.settimeout(5)
                while chunk := connection.recv(4096):
                    received.extend(chunk)

        thread = threading.Thread(target=receiver)
        thread.start()
        zpl = "^XA^CI28^FDtest^FS^PQ40,0,1,Y^XZ"
        send_zpl("127.0.0.1", zpl, server.getsockname()[1], timeout=2)
        thread.join(5)
        assert not thread.is_alive() and received == zpl.encode("utf-8")
