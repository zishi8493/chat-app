import json
import logging
import socket
import threading
from datetime import datetime
from pathlib import Path


HOST = "0.0.0.0"
PORT = 9000
ENCODING = "utf-8"


class Client:
    def __init__(self, name, sock, address):
        self.name = name
        self.sock = sock
        self.address = address
        self.send_lock = threading.Lock()


class ChatServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.clients = {}
        self.clients_lock = threading.Lock()
        self.running = False
        self.server_sock = None

        log_dir = Path(__file__).resolve().parent / "chat_logs"
        log_dir.mkdir(exist_ok=True)
        logging.basicConfig(
            filename=log_dir / "server.log",
            level=logging.INFO,
            format="%(asctime)s %(message)s",
            encoding=ENCODING,
        )

    def start(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen()
        self.running = True

        print(f"聊天服务器已启动: {self.host}:{self.port}")
        print("按 Ctrl+C 停止服务器。")
        logging.info("服务器启动 %s:%s", self.host, self.port)

        try:
            while self.running:
                try:
                    client_sock, address = self.server_sock.accept()
                except OSError:
                    if self.running:
                        raise
                    break
                thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_sock, address),
                    daemon=True,
                )
                thread.start()
        except KeyboardInterrupt:
            print("\n服务器正在关闭...")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        with self.clients_lock:
            clients = list(self.clients.values())
            self.clients.clear()

        for client in clients:
            self.close_socket(client.sock)

        if self.server_sock:
            self.close_socket(self.server_sock)
        logging.info("服务器关闭")

    def handle_client(self, client_sock, address):
        client = None
        file = client_sock.makefile("r", encoding=ENCODING, newline="\n")

        try:
            login_data = self.read_message(file)
            if not login_data or login_data.get("type") != "login":
                self.send_json_raw(client_sock, {"type": "error", "message": "请先发送登录信息。"})
                return

            name = str(login_data.get("name", "")).strip()
            if not self.valid_name(name):
                self.send_json_raw(client_sock, {"type": "login", "success": False, "message": "昵称不能为空，且不能包含空格。"})
                return

            with self.clients_lock:
                if name in self.clients:
                    self.send_json_raw(client_sock, {"type": "login", "success": False, "message": "昵称已存在，请更换昵称。"})
                    return
                client = Client(name, client_sock, address)
                self.clients[name] = client

            self.send_json(client, {"type": "login", "success": True, "message": "登录成功。"})
            self.broadcast_system(f"{name} 上线了。")
            self.broadcast_users()
            logging.info("用户上线: %s %s", name, address)

            for data in self.iter_messages(file):
                self.process_message(client, data)
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            if client:
                self.remove_client(client.name)
            self.close_socket(client_sock)

    def process_message(self, client, data):
        msg_type = data.get("type")
        if msg_type == "chat":
            target = str(data.get("to", "all"))
            message = str(data.get("message", "")).strip()
            if not message:
                return
            if target == "all":
                self.broadcast_chat(client.name, "all", message)
            else:
                self.private_chat(client.name, target, message)
        elif msg_type == "logout":
            self.remove_client(client.name)
            self.close_socket(client.sock)
        elif msg_type == "ping":
            self.send_json(client, {"type": "pong", "time": self.now()})

    def broadcast_chat(self, sender, target, message):
        payload = {
            "type": "chat",
            "from": sender,
            "to": target,
            "message": message,
            "time": self.now(),
        }
        logging.info("[群聊] %s: %s", sender, message)
        self.broadcast(payload)

    def private_chat(self, sender, target, message):
        with self.clients_lock:
            sender_client = self.clients.get(sender)
            target_client = self.clients.get(target)

        if not target_client:
            if sender_client:
                self.send_json(sender_client, {"type": "error", "message": f"用户 {target} 不在线。"})
            return

        payload = {
            "type": "chat",
            "from": sender,
            "to": target,
            "message": message,
            "time": self.now(),
        }
        logging.info("[私聊] %s -> %s: %s", sender, target, message)
        self.send_json(target_client, payload)
        if sender_client and sender_client.name != target_client.name:
            self.send_json(sender_client, payload)

    def broadcast_system(self, message):
        logging.info("[系统] %s", message)
        self.broadcast({"type": "system", "message": message, "time": self.now()})

    def broadcast_users(self):
        with self.clients_lock:
            users = sorted(self.clients)
        self.broadcast({"type": "users", "users": users})

    def broadcast(self, payload):
        with self.clients_lock:
            clients = list(self.clients.values())
        broken_names = []
        for client in clients:
            try:
                self.send_json(client, payload)
            except OSError:
                broken_names.append(client.name)

        for name in broken_names:
            self.remove_client(name)

    def remove_client(self, name):
        removed = False
        with self.clients_lock:
            client = self.clients.pop(name, None)
            if client:
                removed = True

        if removed:
            self.close_socket(client.sock)
            self.broadcast_system(f"{name} 下线了。")
            self.broadcast_users()
            logging.info("用户下线: %s", name)

    def send_json(self, client, payload):
        with client.send_lock:
            self.send_json_raw(client.sock, payload)

    @staticmethod
    def send_json_raw(sock, payload):
        data = json.dumps(payload, ensure_ascii=False) + "\n"
        sock.sendall(data.encode(ENCODING))

    @staticmethod
    def read_message(file):
        line = file.readline()
        if not line:
            return None
        return json.loads(line)

    def iter_messages(self, file):
        while True:
            line = file.readline()
            if not line:
                break
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

    @staticmethod
    def valid_name(name):
        return bool(name) and len(name) <= 20 and not any(ch.isspace() for ch in name)

    @staticmethod
    def now():
        return datetime.now().strftime("%H:%M:%S")

    @staticmethod
    def close_socket(sock):
        try:
            sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    ChatServer().start()
