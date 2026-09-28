import socket
import threading

REMOTE = ("178.209.127.247", 22)
LISTEN = ("127.0.0.1", 2223)
MAX_BANNER = 8192


def recv_line(sock, limit=MAX_BANNER):
    data = bytearray()
    while len(data) < limit:
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("socket closed during SSH identification exchange")
        data += chunk
        if data.endswith(b"\n"):
            return bytes(data)
    raise ValueError("SSH identification line too long")


def copy_loop(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle(client):
    remote = None
    try:
        remote = socket.create_connection(REMOTE, timeout=10)
        remote.settimeout(10)
        client.settimeout(10)

        # This VPS/path requires the server identification to be received
        # before the client's identification is forwarded.
        while True:
            server_line = recv_line(remote)
            client.sendall(server_line)
            if server_line.startswith(b"SSH-"):
                break

        while True:
            client_line = recv_line(client)
            remote.sendall(client_line)
            if client_line.startswith(b"SSH-"):
                break

        remote.settimeout(None)
        client.settimeout(None)

        t1 = threading.Thread(target=copy_loop, args=(client, remote), daemon=True)
        t2 = threading.Thread(target=copy_loop, args=(remote, client), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception as exc:
        print(f"RELAY_CONNECTION_ERROR {type(exc).__name__}: {exc}", flush=True)
    finally:
        try:
            client.close()
        except OSError:
            pass
        if remote is not None:
            try:
                remote.close()
            except OSError:
                pass


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(LISTEN)
        server.listen(20)
        print(f"PORTAL_BANNER_FIRST_RELAY_READY {LISTEN[0]}:{LISTEN[1]} -> {REMOTE[0]}:{REMOTE[1]}", flush=True)
        while True:
            client, _ = server.accept()
            threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
