import argparse
import os
import selectors
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from httpResolver.fileResponser import FileResponser, HttpResponse
from httpResolver.httpResolver import ErrorReason, HttpRequestData, HttpStreamResolver, HttpVersion


def default_mime_types() -> dict[str, list[str]]:
    return {
        "text/html": [".html", "html", ".htm", "htm"],
        "text/plain": [".txt", "txt"],
        "text/css": [".css", "css"],
        "application/javascript": [".js", "js"],
        "application/json": [".json", "json"],
        "image/png": [".png", "png"],
        "image/webp": [".webp","webp"],
        "image/jpeg": [".jpg", "jpg", ".jpeg", "jpeg"],
        "image/gif": [".gif", "gif"],
        "image/svg+xml": [".svg", "svg"],
    }


@dataclass
class ServerConfig:
    host: str
    port: int
    root: str
    backlog: int = 128
    recv_size: int = 16384


class HttpRequestHandler:
    def __init__(self, root: str):
        self.file_responser = FileResponser(root=root, mime_types=default_mime_types())

    def build_response(self, success: bool, data: Optional[HttpRequestData], error_reason: ErrorReason) -> HttpResponse:
        response = HttpResponse(self.file_responser)
        if success and data is not None:
            response.resolve(data)
        else:
            response.reject(error_reason)
        return response


class ConnectionSession:
    def __init__(self, handler: HttpRequestHandler, on_response: Callable[[bytes, bool], None]):
        self._handler = handler
        self._on_response = on_response
        self._resolver = HttpStreamResolver(self._on_parsed)

    def feed_bytes(self, payload: bytes):
        self._resolver.feed(payload.decode("latin-1", errors="replace"))

    def _on_parsed(self, success: bool, data: Optional[HttpRequestData], error_reason: ErrorReason):
        response = self._handler.build_response(success, data, error_reason)
        should_close = response.headers.get("Connection", "").lower() == "close"
        self._on_response(response.to_http_bytes(), should_close)



class ThreadedHttpServer:
    def __init__(self, config: ServerConfig, handler: HttpRequestHandler):
        self._config = config
        self._handler = handler

    def serve_forever(self):
        listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listen_sock.bind((self._config.host, self._config.port))
        listen_sock.listen(self._config.backlog)
        print(f"{self._config.host}:{self._config.port}, {self._config.root}")

        try:
            while True:
                conn, addr = listen_sock.accept()
                t = threading.Thread(target=self._serve_client, args=(conn, addr), daemon=True)
                t.start()
        finally:
            listen_sock.close()

    def _serve_client(self, conn: socket.socket, addr):
        print(f"accepted {addr}")
        conn.setblocking(True)
        send_lock = threading.Lock()
        close_after_send = {"value": False}

        def on_response(payload: bytes, should_close: bool):
            with send_lock:
                conn.sendall(payload)
                if should_close:
                    close_after_send["value"] = True

        session = ConnectionSession(self._handler, on_response)

        try:
            while True:
                data = conn.recv(self._config.recv_size)
                if not data:
                    break
                session.feed_bytes(data)
                if close_after_send["value"]:
                    break
        except (ConnectionResetError, OSError):
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


def build_server(config: ServerConfig):
    handler = HttpRequestHandler(config.root)
    return ThreadedHttpServer(config, handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=16666)
    parser.add_argument("--root", default=Path(os.path.dirname(__file__),"httpRoot").resolve().__str__())
    return parser.parse_args()


def main():
    args = parse_args()
    config = ServerConfig(host=args.host, port=args.port, root=args.root)
    server = build_server(config)
    server.serve_forever()


if __name__ == "__main__":
    main()

