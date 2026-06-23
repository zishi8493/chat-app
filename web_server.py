from __future__ import annotations

import argparse
import base64
import hashlib
import mimetypes
import socket
import struct
import threading
from pathlib import Path
from urllib.parse import unquote, urlsplit


HOST = "0.0.0.0"
PORT = 8080
CHAT_HOST = "127.0.0.1"
CHAT_PORT = 9000
BUFFER_SIZE = 4096
ENCODING = "utf-8"
WEB_ROOT = Path(__file__).resolve().parent / "web"
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WebSocketClosed(Exception):
    pass


def status_text(code):
    return {
        200: "OK",
        400: "Bad Request",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        500: "Internal Server Error",
        502: "Bad Gateway",
    }.get(code, "Internal Server Error")


def make_response(code, body, content_type="text/html; charset=utf-8"):
    headers = [
        f"HTTP/1.1 {code} {status_text(code)}",
        "Server: Python-Chat-Web/1.0",
        f"Content-Type: {content_type}",
        f"Content-Length: {len(body)}",
        "Connection: close",
        "Cache-Control: no-store" if content_type.startswith("text/html") else "Cache-Control: public, max-age=3600",
        "",
        "",
    ]
    return "\r\n".join(headers).encode("iso-8859-1") + body


def error_page(code, message):
    body = f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{code} {status_text(code)}</title></head>
<body><h1>{code} {status_text(code)}</h1><p>{message}</p></body>
</html>
"""
    return make_response(code, body.encode(ENCODING))


def recv_http_request(client_sock):
    data = bytearray()
    while b"\r\n\r\n" not in data and len(data) <= 65536:
        chunk = client_sock.recv(BUFFER_SIZE)
        if not chunk:
            break
        data.extend(chunk)

    header_bytes, _, rest = bytes(data).partition(b"\r\n\r\n")
    header_text = header_bytes.decode("iso-8859-1", errors="replace")
    lines = header_text.split("\r\n")
    request_line = lines[0] if lines else ""
    headers = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return request_line, headers, rest


def resolve_path(target):
    url_path = unquote(urlsplit(target).path)
    if url_path == "/":
        url_path = "/index.html"
    candidate = (WEB_ROOT / url_path.lstrip("/")).resolve()
    try:
        candidate.relative_to(WEB_ROOT.resolve())
    except ValueError:
        return None
    return candidate


def serve_static(client_sock, target):
    file_path = resolve_path(target)
    if file_path is None:
        client_sock.sendall(error_page(403, "禁止访问 Web 根目录之外的文件。"))
        return
    if not file_path.is_file():
        client_sock.sendall(error_page(404, "请求的文件不存在。"))
        return

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    if content_type.startswith("text/") or file_path.suffix == ".js":
        content_type += "; charset=utf-8"
    client_sock.sendall(make_response(200, file_path.read_bytes(), content_type))


def is_websocket_request(target, headers):
    return (
        urlsplit(target).path == "/ws"
        and headers.get("upgrade", "").lower() == "websocket"
        and "upgrade" in headers.get("connection", "").lower()
    )


def accept_websocket(client_sock, headers):
    key = headers.get("sec-websocket-key")
    if not key:
        client_sock.sendall(error_page(400, "缺少 WebSocket Key。"))
        return False

    accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    )
    client_sock.sendall(response.encode("ascii"))
    return True


def recv_exact(sock, size):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise WebSocketClosed()
        chunks.extend(chunk)
    return bytes(chunks)


def recv_ws_text(sock):
    header = recv_exact(sock, 2)
    first, second = header
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F

    if length == 126:
        length = struct.unpack("!H", recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", recv_exact(sock, 8))[0]

    mask = recv_exact(sock, 4) if masked else b""
    payload = bytearray(recv_exact(sock, length))
    if masked:
        for index, value in enumerate(payload):
            payload[index] = value ^ mask[index % 4]

    if opcode == 0x8:
        raise WebSocketClosed()
    if opcode == 0x9:
        send_ws_frame(sock, bytes(payload), opcode=0xA)
        return None
    if opcode == 0xA:
        return None
    if opcode != 0x1:
        return None

    return payload.decode(ENCODING)


def send_ws_text(sock, text):
    send_ws_frame(sock, text.encode(ENCODING), opcode=0x1)


def send_ws_close(sock):
    try:
        send_ws_frame(sock, b"", opcode=0x8)
    except OSError:
        pass


def send_ws_frame(sock, payload, opcode=0x1):
    first = 0x80 | opcode
    length = len(payload)
    if length < 126:
        header = struct.pack("!BB", first, length)
    elif length < 65536:
        header = struct.pack("!BBH", first, 126, length)
    else:
        header = struct.pack("!BBQ", first, 127, length)
    sock.sendall(header + payload)


def send_chat_line(chat_sock, text):
    chat_sock.sendall((text.rstrip("\n") + "\n").encode(ENCODING))


def pipe_chat_to_web(chat_file, web_sock, stop_event):
    try:
        while not stop_event.is_set():
            line = chat_file.readline()
            if not line:
                break
            send_ws_text(web_sock, line.rstrip("\n"))
    except (OSError, WebSocketClosed):
        pass
    finally:
        stop_event.set()


def bridge_websocket(web_sock, chat_host, chat_port):
    stop_event = threading.Event()
    chat_sock = None
    chat_file = None
    try:
        chat_sock = socket.create_connection((chat_host, chat_port), timeout=8)
        chat_sock.settimeout(None)
        chat_file = chat_sock.makefile("r", encoding=ENCODING, newline="\n")

        reader = threading.Thread(target=pipe_chat_to_web, args=(chat_file, web_sock, stop_event), daemon=True)
        reader.start()

        while not stop_event.is_set():
            text = recv_ws_text(web_sock)
            if text is None:
                continue
            send_chat_line(chat_sock, text)
    except (OSError, WebSocketClosed):
        if not stop_event.is_set():
            try:
                send_ws_text(web_sock, '{"type":"error","message":"无法连接聊天服务器或连接已断开。"}')
            except OSError:
                pass
    finally:
        stop_event.set()
        if chat_file:
            try:
                chat_file.close()
            except OSError:
                pass
        if chat_sock:
            close_socket(chat_sock)
        send_ws_close(web_sock)


def handle_client(client_sock, address, chat_host, chat_port):
    with client_sock:
        try:
            request_line, headers, _rest = recv_http_request(client_sock)
            parts = request_line.split()
            if len(parts) != 3:
                client_sock.sendall(error_page(400, "无法解析 HTTP 请求行。"))
                return

            method, target, _version = parts
            print(f"[{address[0]}:{address[1]}] {method} {target}")
            if method.upper() != "GET":
                client_sock.sendall(error_page(405, "本服务器仅支持 GET 请求。"))
                return

            if is_websocket_request(target, headers):
                if accept_websocket(client_sock, headers):
                    bridge_websocket(client_sock, chat_host, chat_port)
                return

            serve_static(client_sock, target)
        except OSError:
            return


def serve(host, port, chat_host, chat_port):
    if not WEB_ROOT.is_dir():
        raise SystemExit(f"Web 目录不存在: {WEB_ROOT}")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((host, port))
    server_sock.listen(32)
    print(f"手机网页版已启动: http://127.0.0.1:{port}/")
    print(f"WebSocket 桥接到聊天服务器: {chat_host}:{chat_port}")
    print("按 Ctrl+C 停止服务。")

    try:
        while True:
            client_sock, address = server_sock.accept()
            thread = threading.Thread(target=handle_client, args=(client_sock, address, chat_host, chat_port), daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("\n网页服务正在关闭...")
    finally:
        close_socket(server_sock)


def close_socket(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Mobile web client and WebSocket bridge for the TCP chat server.")
    parser.add_argument("--host", default=HOST, help="HTTP server listen host.")
    parser.add_argument("--port", type=int, default=PORT, help="HTTP server listen port.")
    parser.add_argument("--chat-host", default=CHAT_HOST, help="TCP chat server host.")
    parser.add_argument("--chat-port", type=int, default=CHAT_PORT, help="TCP chat server port.")
    args = parser.parse_args()
    serve(args.host, args.port, args.chat_host, args.chat_port)


if __name__ == "__main__":
    main()
