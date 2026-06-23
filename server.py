import hashlib
import hmac
import json
import logging
import os
import socket
import sqlite3
import threading
from datetime import datetime
from pathlib import Path


HOST = "0.0.0.0"
PORT = 9000
ENCODING = "utf-8"
PASSWORD_ITERATIONS = 120_000
HISTORY_LIMIT = 100


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
        self.db_lock = threading.Lock()
        self.running = False
        self.server_sock = None
        self.base_dir = Path(__file__).resolve().parent
        self.db_path = self.base_dir / "chat_app.db"

        log_dir = self.base_dir / "chat_logs"
        log_dir.mkdir(exist_ok=True)
        logging.basicConfig(
            filename=log_dir / "server.log",
            level=logging.INFO,
            format="%(asctime)s %(message)s",
            encoding=ENCODING,
        )
        self.init_db()

    def init_db(self):
        with self.get_db() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    target TEXT NOT NULL,
                    message TEXT NOT NULL,
                    sent_at TEXT NOT NULL
                )
                """
            )

    def get_db(self):
        return sqlite3.connect(self.db_path)

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
            auth_data = self.read_message(file)
            if not auth_data:
                self.send_json_raw(client_sock, {"type": "error", "message": "请先发送登录或注册信息。"})
                return

            msg_type = auth_data.get("type")
            if msg_type == "register":
                self.handle_register(client_sock, auth_data)
                return

            if msg_type != "login":
                self.send_json_raw(client_sock, {"type": "error", "message": "请先登录账号。"})
                return

            name = str(auth_data.get("name", "")).strip()
            password = str(auth_data.get("password", ""))
            ok, message = self.authenticate_user(name, password)
            if not ok:
                self.send_json_raw(client_sock, {"type": "login", "success": False, "message": message})
                return

            with self.clients_lock:
                if name in self.clients:
                    self.send_json_raw(client_sock, {"type": "login", "success": False, "message": "昵称已存在，请更换昵称。"})
                    return
                client = Client(name, client_sock, address)
                self.clients[name] = client

            self.send_json(client, {"type": "login", "success": True, "message": "登录成功。"})
            self.send_history(client)
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
        self.save_message(sender, target, message, payload["time"])
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
        self.save_message(sender, target, message, payload["time"])
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

    def handle_register(self, sock, data):
        name = str(data.get("name", "")).strip()
        password = str(data.get("password", ""))
        ok, message = self.register_user(name, password)
        self.send_json_raw(sock, {"type": "register", "success": ok, "message": message})
        return ok

    def register_user(self, name, password):
        if not self.valid_name(name):
            return False, "用户名不能为空，长度不能超过 20，且不能包含空格。"
        if not self.valid_password(password):
            return False, "密码长度至少 6 位，且不能包含空格。"

        salt = os.urandom(16).hex()
        password_hash = self.hash_password(password, salt)
        try:
            with self.db_lock, self.get_db() as conn:
                conn.execute(
                    "INSERT INTO users(username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                    (name, password_hash, salt, self.full_now()),
                )
        except sqlite3.IntegrityError:
            return False, "用户名已存在，请直接登录或更换用户名。"
        logging.info("用户注册: %s", name)
        return True, "注册成功，请登录。"

    def authenticate_user(self, name, password):
        if not self.valid_name(name):
            return False, "用户名不能为空，且不能包含空格。"
        if not password:
            return False, "密码不能为空。"

        with self.db_lock, self.get_db() as conn:
            row = conn.execute(
                "SELECT password_hash, salt FROM users WHERE username = ?",
                (name,),
            ).fetchone()
        if not row:
            return False, "账号不存在，请先注册。"

        expected_hash, salt = row
        actual_hash = self.hash_password(password, salt)
        if not hmac.compare_digest(expected_hash, actual_hash):
            return False, "密码错误。"
        return True, "登录成功。"

    def save_message(self, sender, target, message, sent_at):
        with self.db_lock, self.get_db() as conn:
            conn.execute(
                "INSERT INTO messages(sender, target, message, sent_at) VALUES (?, ?, ?, ?)",
                (sender, target, message, sent_at),
            )

    def send_history(self, client):
        with self.db_lock, self.get_db() as conn:
            rows = conn.execute(
                """
                SELECT sender, target, message, sent_at
                FROM messages
                WHERE target = 'all' OR sender = ? OR target = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (client.name, client.name, HISTORY_LIMIT),
            ).fetchall()

        history = [
            {
                "type": "chat",
                "from": sender,
                "to": target,
                "message": message,
                "time": sent_at,
            }
            for sender, target, message, sent_at in reversed(rows)
        ]
        self.send_json(client, {"type": "history", "messages": history})

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
    def valid_password(password):
        return len(password) >= 6 and not any(ch.isspace() for ch in password)

    @staticmethod
    def hash_password(password, salt):
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(ENCODING),
            bytes.fromhex(salt),
            PASSWORD_ITERATIONS,
        )
        return digest.hex()

    @staticmethod
    def now():
        return datetime.now().strftime("%H:%M:%S")

    @staticmethod
    def full_now():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def close_socket(sock):
        try:
            sock.close()
        except OSError:
            pass


if __name__ == "__main__":
    ChatServer().start()
