import json
import queue
import socket
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
from pathlib import Path


DEFAULT_HOST = "124.223.78.29"
DEFAULT_PORT = "9000"
ENCODING = "utf-8"
HEARTBEAT_SECONDS = 20

BG = "#f5f5f5"
SIDEBAR_BG = "#14203d"
SIDEBAR_ACTIVE = "#23345f"
PANEL_BG = "#f7f8fc"
LINE = "#2d3d66"
TEXT = "#222222"
MUTED = "#777777"
GREEN = "#95ec69"
GREEN_DARK = "#07c160"
WHITE = "#ffffff"
SYSTEM_BG = "#e8ebf4"
LOGIN_FALLBACK_BG = "#eef2f5"
LOGIN_BACKGROUND = Path("assets") / "login_background.png"
CHAT_FALLBACK_BG = "#eef1f8"
CHAT_PANEL_BG = "#111a34"
CHAT_INPUT_BG = "#182544"
CHAT_ENTRY_BG = "#edf2ff"
CHAT_TEXT = "#f6f8ff"
CHAT_MUTED = "#b7c2df"
CHAT_ROW_BG = "#172442"
INCOMING_BUBBLE_BG = "#eef2ff"
CHAT_SYSTEM_BG = "#26365f"
CHAT_BACKGROUND = Path("assets") / "chat_background.png"
APP_ICON = Path("app.ico")


def resource_path(relative_path):
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


class ChatClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("网络聊天应用")
        self.set_window_icon()
        self.root.geometry("980x660")
        self.root.minsize(820, 560)
        self.root.configure(bg=BG)

        self.sock = None
        self.file = None
        self.name = ""
        self.connected = False
        self.send_lock = threading.Lock()
        self.inbox = queue.Queue()

        self.host_var = tk.StringVar(value=DEFAULT_HOST)
        self.port_var = tk.StringVar(value=DEFAULT_PORT)
        self.name_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.target_var = tk.StringVar(value="群聊")
        self.status_var = tk.StringVar(value="未连接")
        self.online_users = []
        self.contact_widgets = {}
        self.login_background_image = None
        self.login_canvas = None
        self.login_card_window = None
        self.chat_background_image = None
        self.chat_canvas = None
        self.chat_shell_window = None
        self.message_records = []
        self.message_content_height = 0

        self.build_login_view()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.process_inbox)

    def set_window_icon(self):
        try:
            self.root.iconbitmap(resource_path(APP_ICON))
        except (tk.TclError, OSError):
            pass

    def build_login_view(self):
        self.clear_root()
        self.root.configure(bg=LOGIN_FALLBACK_BG)

        self.login_canvas = tk.Canvas(self.root, bg=LOGIN_FALLBACK_BG, highlightthickness=0)
        self.login_canvas.pack(fill=tk.BOTH, expand=True)
        self.load_login_background()

        card = tk.Frame(self.root, bg=WHITE, padx=42, pady=34, highlightthickness=1, highlightbackground="#e2e6ea")
        self.login_card_window = self.login_canvas.create_window(0, 0, window=card, anchor="center")
        self.login_canvas.bind("<Configure>", self.on_login_canvas_configure)

        logo = tk.Label(card, text="聊", width=3, height=1, bg=GREEN_DARK, fg=WHITE, font=("Microsoft YaHei UI", 22, "bold"))
        logo.grid(row=0, column=0, columnspan=2, pady=(0, 14))

        title = tk.Label(card, text="网络聊天应用", bg=WHITE, fg=TEXT, font=("Microsoft YaHei UI", 22, "bold"))
        title.grid(row=1, column=0, columnspan=2, pady=(0, 28))

        self.add_labeled_entry(card, "服务器地址", self.host_var, 2)
        self.add_labeled_entry(card, "端口", self.port_var, 3)
        name_entry = self.add_labeled_entry(card, "账号", self.name_var, 4)
        name_entry.bind("<Return>", lambda _event: self.login())
        password_entry = self.add_labeled_entry(card, "密码", self.password_var, 5, show="*")
        password_entry.bind("<Return>", lambda _event: self.login())

        login_button = tk.Button(
            card,
            text="登录",
            width=13,
            bg=GREEN_DARK,
            fg=WHITE,
            activebackground="#06ad56",
            activeforeground=WHITE,
            relief=tk.FLAT,
            command=self.login,
            font=("Microsoft YaHei UI", 11),
        )
        login_button.grid(row=6, column=0, pady=(26, 10), ipady=6)

        register_button = tk.Button(
            card,
            text="注册账号",
            width=13,
            bg=WHITE,
            fg=GREEN_DARK,
            activebackground="#eef8f2",
            activeforeground=GREEN_DARK,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=GREEN_DARK,
            command=self.register,
            font=("Microsoft YaHei UI", 11),
        )
        register_button.grid(row=6, column=1, pady=(26, 10), ipady=6)

        hint = tk.Label(card, text="首次使用请先注册账号；密码至少 6 位。", bg=WHITE, fg=MUTED, font=("Microsoft YaHei UI", 9))
        hint.grid(row=7, column=0, columnspan=2)

        for child in card.winfo_children():
            child.grid_configure(padx=7, pady=7)

        name_entry.focus_set()

    def load_login_background(self):
        try:
            self.login_background_image = tk.PhotoImage(file=resource_path(LOGIN_BACKGROUND))
            self.login_canvas.create_image(0, 0, image=self.login_background_image, anchor="center", tags="login_bg")
        except tk.TclError:
            self.login_background_image = None

    def on_login_canvas_configure(self, event):
        center_x = event.width // 2
        center_y = event.height // 2
        if self.login_background_image:
            self.login_canvas.coords("login_bg", center_x, center_y)
        if self.login_card_window:
            self.login_canvas.coords(self.login_card_window, center_x, center_y)

    @staticmethod
    def add_labeled_entry(frame, label, variable, row, show=None):
        tk.Label(frame, text=label, bg=WHITE, fg="#444444", width=10, anchor="e", font=("Microsoft YaHei UI", 10)).grid(row=row, column=0)
        entry = tk.Entry(
            frame,
            textvariable=variable,
            show=show,
            width=30,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#d7dce0",
            highlightcolor=GREEN_DARK,
            font=("Microsoft YaHei UI", 11),
        )
        entry.grid(row=row, column=1, ipady=7)
        return entry

    def build_chat_view(self):
        self.clear_root()
        self.root.configure(bg=CHAT_FALLBACK_BG)

        self.chat_canvas = tk.Canvas(self.root, bg=CHAT_FALLBACK_BG, highlightthickness=0)
        self.chat_canvas.pack(fill=tk.BOTH, expand=True)
        self.load_chat_background()

        shell = tk.Frame(self.chat_canvas, bg=CHAT_PANEL_BG)
        self.chat_shell_window = self.chat_canvas.create_window((0, 0), window=shell, anchor="nw")
        self.chat_canvas.bind("<Configure>", self.on_chat_canvas_configure)

        self.sidebar = tk.Frame(shell, width=270, bg=SIDEBAR_BG)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        self.build_sidebar_header()

        self.contacts_frame = tk.Frame(self.sidebar, bg=SIDEBAR_BG)
        self.contacts_frame.pack(fill=tk.BOTH, expand=True)

        self.chat_panel = tk.Frame(shell, bg=CHAT_PANEL_BG)
        self.chat_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.build_chat_header()
        self.build_message_area()
        self.build_input_area()
        self.update_contacts(self.online_users)

        self.status_var.set("已连接")
        self.message_input.focus_set()

    def load_chat_background(self):
        try:
            self.chat_background_image = tk.PhotoImage(file=resource_path(CHAT_BACKGROUND))
            self.chat_canvas.create_image(0, 0, image=self.chat_background_image, anchor="center", tags="chat_bg")
        except tk.TclError:
            self.chat_background_image = None

    def on_chat_canvas_configure(self, event):
        if self.chat_background_image:
            self.chat_canvas.coords("chat_bg", event.width // 2, event.height // 2)
        if self.chat_shell_window:
            self.chat_canvas.itemconfigure(self.chat_shell_window, width=event.width, height=event.height)

    def build_sidebar_header(self):
        header = tk.Frame(self.sidebar, bg=SIDEBAR_BG, padx=18, pady=16)
        header.pack(fill=tk.X)

        avatar = tk.Label(header, text=self.avatar_text(self.name), width=3, height=1, bg=GREEN_DARK, fg=WHITE, font=("Microsoft YaHei UI", 16, "bold"))
        avatar.pack(side=tk.LEFT)

        info = tk.Frame(header, bg=SIDEBAR_BG)
        info.pack(side=tk.LEFT, padx=(12, 0), fill=tk.X, expand=True)
        tk.Label(info, text=self.name, bg=SIDEBAR_BG, fg=CHAT_TEXT, font=("Microsoft YaHei UI", 12, "bold"), anchor="w").pack(fill=tk.X)
        tk.Label(info, textvariable=self.status_var, bg=SIDEBAR_BG, fg=GREEN_DARK, font=("Microsoft YaHei UI", 9), anchor="w").pack(fill=tk.X)

        search_wrap = tk.Frame(self.sidebar, bg=SIDEBAR_BG, padx=16)
        search_wrap.pack(fill=tk.X, pady=(0, 12))
        tk.Label(
            search_wrap,
            text="搜索联系人",
            bg=CHAT_ENTRY_BG,
            fg="#6d7897",
            anchor="w",
            padx=12,
            pady=7,
            font=("Microsoft YaHei UI", 9),
        ).pack(fill=tk.X)

    def build_chat_header(self):
        self.chat_header = tk.Frame(self.chat_panel, bg=CHAT_PANEL_BG, height=64, highlightthickness=0)
        self.chat_header.pack(fill=tk.X)
        self.chat_header.pack_propagate(False)

        self.chat_title = tk.Label(self.chat_header, text="群聊", bg=CHAT_PANEL_BG, fg=CHAT_TEXT, font=("Microsoft YaHei UI", 14, "bold"))
        self.chat_title.pack(side=tk.LEFT, padx=24)

        tk.Label(self.chat_header, text="在线聊天", bg=CHAT_PANEL_BG, fg=CHAT_MUTED, font=("Microsoft YaHei UI", 9)).pack(side=tk.RIGHT, padx=24)
        tk.Frame(self.chat_panel, height=1, bg=LINE).pack(fill=tk.X)

    def build_message_area(self):
        area = tk.Frame(self.chat_panel, bg=CHAT_PANEL_BG)
        area.pack(fill=tk.BOTH, expand=True)

        self.message_canvas = tk.Canvas(area, bg=CHAT_PANEL_BG, highlightthickness=0)
        self.message_scroll = tk.Scrollbar(area, orient=tk.VERTICAL, command=self.on_message_scroll)
        self.message_canvas.configure(yscrollcommand=self.message_scroll.set)

        self.message_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.message_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        if self.chat_background_image:
            self.message_canvas.create_image(0, 0, image=self.chat_background_image, anchor="center", tags="message_bg")
            self.message_canvas.tag_lower("message_bg")

        self.message_canvas.bind("<Configure>", self.on_canvas_configure)
        self.message_canvas.bind_all("<MouseWheel>", self.on_mousewheel)

    def build_input_area(self):
        tk.Frame(self.chat_panel, height=1, bg=LINE).pack(fill=tk.X)
        input_wrap = tk.Frame(self.chat_panel, bg=CHAT_INPUT_BG, padx=18, pady=12)
        input_wrap.pack(fill=tk.X)

        self.target_label = tk.Label(input_wrap, textvariable=self.target_var, bg=CHAT_INPUT_BG, fg=CHAT_MUTED, anchor="w", font=("Microsoft YaHei UI", 9))
        self.target_label.pack(fill=tk.X, pady=(0, 6))

        row = tk.Frame(input_wrap, bg=CHAT_INPUT_BG)
        row.pack(fill=tk.X)

        self.message_input = tk.Text(row, height=3, wrap=tk.WORD, relief=tk.FLAT, bg=CHAT_ENTRY_BG, fg=TEXT, font=("Microsoft YaHei UI", 11), padx=10, pady=8)
        self.message_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.message_input.bind("<Return>", self.on_enter_send)
        self.message_input.bind("<Shift-Return>", self.on_shift_enter)

        send_button = tk.Button(
            row,
            text="发送",
            width=10,
            bg=GREEN_DARK,
            fg=WHITE,
            activebackground="#06ad56",
            activeforeground=WHITE,
            relief=tk.FLAT,
            command=self.send_message,
            font=("Microsoft YaHei UI", 10),
        )
        send_button.pack(side=tk.LEFT, padx=(12, 0), ipady=7)

    def login(self):
        host = self.host_var.get().strip()
        port_text = self.port_var.get().strip()
        name = self.name_var.get().strip()
        password = self.password_var.get()

        if not host or not port_text or not name or not password:
            messagebox.showwarning("提示", "服务器地址、端口、账号和密码都不能为空。")
            return
        if any(ch.isspace() for ch in name):
            messagebox.showwarning("提示", "账号不能包含空格。")
            return
        if len(password) < 6 or any(ch.isspace() for ch in password):
            messagebox.showwarning("提示", "密码至少 6 位，且不能包含空格。")
            return

        try:
            port = int(port_text)
            self.sock = socket.create_connection((host, port), timeout=5)
            self.file = self.sock.makefile("r", encoding=ENCODING, newline="\n")
            self.send_json({"type": "login", "name": name, "password": password})
            response = self.read_json()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.close_connection()
            messagebox.showerror("连接失败", f"无法连接服务器：{exc}")
            return

        if not response or not response.get("success"):
            self.close_connection()
            messagebox.showerror("登录失败", response.get("message", "服务器拒绝登录。") if response else "服务器无响应。")
            return

        self.name = name
        self.password_var.set("")
        self.sock.settimeout(None)
        self.connected = True
        self.message_records.clear()
        self.build_chat_view()
        self.append_system_message("登录成功，可以开始聊天。")

        receive_thread = threading.Thread(target=self.receive_loop, daemon=True)
        receive_thread.start()
        heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        heartbeat_thread.start()

    def register(self):
        host = self.host_var.get().strip()
        port_text = self.port_var.get().strip()
        name = self.name_var.get().strip()
        password = self.password_var.get()

        if not host or not port_text or not name or not password:
            messagebox.showwarning("提示", "服务器地址、端口、账号和密码都不能为空。")
            return
        if any(ch.isspace() for ch in name):
            messagebox.showwarning("提示", "账号不能包含空格。")
            return
        if len(password) < 6 or any(ch.isspace() for ch in password):
            messagebox.showwarning("提示", "密码至少 6 位，且不能包含空格。")
            return

        sock = None
        file = None
        try:
            port = int(port_text)
            sock = socket.create_connection((host, port), timeout=5)
            file = sock.makefile("r", encoding=ENCODING, newline="\n")
            data = json.dumps({"type": "register", "name": name, "password": password}, ensure_ascii=False) + "\n"
            sock.sendall(data.encode(ENCODING))
            response = self.read_json_from(file)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            messagebox.showerror("注册失败", f"无法连接服务器：{exc}")
            return
        finally:
            if file:
                file.close()
            if sock:
                sock.close()

        if response and response.get("success"):
            messagebox.showinfo("注册成功", response.get("message", "注册成功，请登录。"))
        else:
            messagebox.showerror("注册失败", response.get("message", "服务器拒绝注册。") if response else "服务器无响应。")

    def receive_loop(self):
        try:
            while self.connected:
                data = self.read_json()
                if not data:
                    break
                self.inbox.put(data)
        except (OSError, json.JSONDecodeError):
            pass
        finally:
            if self.connected:
                self.inbox.put({"type": "system", "message": "与服务器的连接已断开。"})
                self.connected = False

    def heartbeat_loop(self):
        while self.connected:
            time.sleep(HEARTBEAT_SECONDS)
            if not self.connected:
                break
            try:
                self.send_json({"type": "ping"})
            except OSError:
                if self.connected:
                    self.inbox.put({"type": "system", "message": "心跳检测失败，连接已断开。"})
                    self.connected = False
                break

    def process_inbox(self):
        while True:
            try:
                data = self.inbox.get_nowait()
            except queue.Empty:
                break
            self.handle_server_message(data)
        self.root.after(100, self.process_inbox)

    def handle_server_message(self, data):
        msg_type = data.get("type")
        if msg_type == "chat":
            sender = data.get("from", "")
            target = data.get("to", "all")
            message = data.get("message", "")
            time_text = data.get("time", "")
            is_self = sender == self.name
            is_private = target != "all"
            self.append_chat_bubble(sender, target, message, time_text, is_self, is_private)
        elif msg_type == "system":
            self.append_system_message(data.get("message", ""))
        elif msg_type == "users":
            self.update_contacts(data.get("users", []))
        elif msg_type == "history":
            self.append_history(data.get("messages", []))
        elif msg_type == "error":
            self.append_system_message(data.get("message", ""))
        elif msg_type == "pong":
            return

    def send_message(self):
        if not self.connected:
            messagebox.showwarning("提示", "当前未连接服务器。")
            return

        message = self.message_input.get("1.0", tk.END).strip()
        if not message:
            return

        target = self.target_var.get()
        protocol_target = "all" if target == "群聊" else target
        try:
            self.send_json({"type": "chat", "to": protocol_target, "message": message})
            self.message_input.delete("1.0", tk.END)
        except OSError:
            self.append_system_message("发送失败，连接可能已经断开。")
            self.connected = False

    def update_contacts(self, users):
        self.online_users = users
        if not hasattr(self, "contacts_frame"):
            return

        for widget in self.contacts_frame.winfo_children():
            widget.destroy()
        self.contact_widgets.clear()

        self.add_contact("群聊", "所有在线用户", is_group=True)
        for user in users:
            subtitle = "我自己" if user == self.name else "在线"
            self.add_contact(user, subtitle, is_group=False)

        if self.target_var.get() != "群聊" and self.target_var.get() not in users:
            self.target_var.set("群聊")
        self.refresh_contact_selection()

    def add_contact(self, name, subtitle, is_group):
        item = tk.Frame(self.contacts_frame, bg=SIDEBAR_BG, padx=14, pady=10)
        item.pack(fill=tk.X)

        avatar_color = GREEN_DARK if is_group else "#c9c9c9"
        avatar = tk.Label(item, text="#" if is_group else self.avatar_text(name), width=3, height=1, bg=avatar_color, fg=WHITE, font=("Microsoft YaHei UI", 13, "bold"))
        avatar.pack(side=tk.LEFT)

        text_wrap = tk.Frame(item, bg=SIDEBAR_BG)
        text_wrap.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))
        tk.Label(text_wrap, text=name, bg=SIDEBAR_BG, fg=CHAT_TEXT, font=("Microsoft YaHei UI", 11), anchor="w").pack(fill=tk.X)
        tk.Label(text_wrap, text=subtitle, bg=SIDEBAR_BG, fg=CHAT_MUTED, font=("Microsoft YaHei UI", 8), anchor="w").pack(fill=tk.X)

        for widget in (item, avatar, text_wrap):
            widget.bind("<Button-1>", lambda _event, contact=name: self.select_contact(contact))
        for child in text_wrap.winfo_children():
            child.bind("<Button-1>", lambda _event, contact=name: self.select_contact(contact))

        self.contact_widgets[name] = item

    def select_contact(self, name):
        self.target_var.set(name)
        self.chat_title.configure(text=name)
        self.refresh_contact_selection()

    def refresh_contact_selection(self):
        for name, widget in self.contact_widgets.items():
            bg = SIDEBAR_ACTIVE if name == self.target_var.get() else SIDEBAR_BG
            self.set_background_recursive(widget, bg)

    def append_system_message(self, message):
        if not hasattr(self, "message_canvas"):
            return
        self.message_records.append({"type": "system", "message": message})
        self.render_messages()
        self.scroll_to_bottom()

    def append_chat_bubble(self, sender, target, message, time_text, is_self, is_private):
        self.message_records.append(
            {
                "type": "chat",
                "sender": sender,
                "target": target,
                "message": message,
                "time": time_text,
                "is_self": is_self,
                "is_private": is_private,
            }
        )
        self.render_messages()
        self.scroll_to_bottom()

    def append_history(self, messages):
        for item in messages:
            sender = item.get("from", "")
            target = item.get("to", "all")
            self.message_records.append(
                {
                    "type": "chat",
                    "sender": sender,
                    "target": target,
                    "message": item.get("message", ""),
                    "time": item.get("time", ""),
                    "is_self": sender == self.name,
                    "is_private": target != "all",
                }
            )
        if messages:
            self.render_messages()
            self.scroll_to_bottom()

    def on_canvas_configure(self, event):
        if getattr(self, "chat_background_image", None):
            self.update_message_background_position()
        self.render_messages()

    def render_messages(self):
        if not hasattr(self, "message_canvas"):
            return

        self.message_canvas.delete("message_item")
        canvas_width = max(self.message_canvas.winfo_width(), 1)
        canvas_height = max(self.message_canvas.winfo_height(), 1)
        y = 14

        for record in self.message_records:
            if record["type"] == "system":
                y = self.draw_system_message(canvas_width, y, record["message"])
            else:
                y = self.draw_chat_message(canvas_width, y, record)

        self.message_content_height = y
        self.message_canvas.configure(scrollregion=(0, 0, canvas_width, max(canvas_height, y)))
        self.update_message_background_position()

    def update_message_background_position(self):
        if not getattr(self, "chat_background_image", None) or not hasattr(self, "message_canvas"):
            return

        visible_left = self.message_canvas.canvasx(0)
        visible_top = self.message_canvas.canvasy(0)
        self.message_canvas.coords(
            "message_bg",
            visible_left + self.message_canvas.winfo_width() // 2,
            visible_top + self.message_canvas.winfo_height() // 2,
        )
        self.message_canvas.tag_lower("message_bg")

    def draw_system_message(self, canvas_width, y, message):
        text_id = self.message_canvas.create_text(
            canvas_width // 2,
            y,
            text=message,
            fill=CHAT_MUTED,
            font=("Microsoft YaHei UI", 9),
            anchor="n",
            tags="message_item",
        )
        bbox = self.message_canvas.bbox(text_id)
        if not bbox:
            return y
        pad_x = 12
        pad_y = 5
        rect_id = self.message_canvas.create_rectangle(
            bbox[0] - pad_x,
            bbox[1] - pad_y,
            bbox[2] + pad_x,
            bbox[3] + pad_y,
            fill=CHAT_SYSTEM_BG,
            outline="",
            tags="message_item",
        )
        self.message_canvas.tag_lower(rect_id, text_id)
        return bbox[3] + pad_y + 14

    def draw_chat_message(self, canvas_width, y, record):
        is_self = record["is_self"]
        name_text = "我" if is_self else record["sender"]
        if record["is_private"]:
            name_text = f"{name_text} 私聊"
        meta = f"{record['time']}  {name_text}" if record["time"] else name_text

        side_margin = 18
        max_bubble_width = max(120, min(430, canvas_width - side_margin * 2 - 80))
        meta_anchor = "ne" if is_self else "nw"
        meta_x = canvas_width - side_margin if is_self else side_margin
        self.message_canvas.create_text(
            meta_x,
            y,
            text=meta,
            fill=CHAT_MUTED,
            font=("Microsoft YaHei UI", 8),
            anchor=meta_anchor,
            tags="message_item",
        )

        y += 18
        text_id = self.message_canvas.create_text(
            0,
            y,
            text=record["message"],
            fill=TEXT,
            font=("Microsoft YaHei UI", 10),
            anchor="nw",
            width=max_bubble_width,
            tags="message_item",
        )
        text_bbox = self.message_canvas.bbox(text_id)
        if not text_bbox:
            return y

        bubble_width = text_bbox[2] - text_bbox[0] + 24
        bubble_height = text_bbox[3] - text_bbox[1] + 16
        bubble_x = canvas_width - side_margin - bubble_width if is_self else side_margin
        bubble_y = y
        bubble_bg = GREEN if is_self else INCOMING_BUBBLE_BG

        self.message_canvas.coords(text_id, bubble_x + 12, bubble_y + 8)
        rect_id = self.message_canvas.create_rectangle(
            bubble_x,
            bubble_y,
            bubble_x + bubble_width,
            bubble_y + bubble_height,
            fill=bubble_bg,
            outline="",
            tags="message_item",
        )
        self.message_canvas.tag_lower(rect_id, text_id)
        return bubble_y + bubble_height + 16

    def on_enter_send(self, _event):
        self.send_message()
        return "break"

    @staticmethod
    def on_shift_enter(_event):
        return None

    def on_mousewheel(self, event):
        if hasattr(self, "message_canvas"):
            self.message_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            self.update_message_background_position()

    def on_message_scroll(self, *args):
        self.message_canvas.yview(*args)
        self.update_message_background_position()

    def scroll_to_bottom(self):
        self.root.update_idletasks()
        self.render_messages()
        self.message_canvas.yview_moveto(1.0)
        self.update_message_background_position()

    @staticmethod
    def avatar_text(name):
        return (name[:1] or "?").upper()

    def send_json(self, payload):
        data = json.dumps(payload, ensure_ascii=False) + "\n"
        with self.send_lock:
            self.sock.sendall(data.encode(ENCODING))

    def read_json(self):
        line = self.file.readline()
        if not line:
            return None
        return json.loads(line)

    @staticmethod
    def read_json_from(file):
        line = file.readline()
        if not line:
            return None
        return json.loads(line)

    def close_connection(self):
        self.connected = False
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass
        self.sock = None
        self.file = None

    def on_close(self):
        if self.connected:
            try:
                self.send_json({"type": "logout"})
            except OSError:
                pass
        self.close_connection()
        self.root.destroy()

    def clear_root(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def set_background_recursive(self, widget, color):
        try:
            widget.configure(bg=color)
        except tk.TclError:
            return
        for child in widget.winfo_children():
            try:
                child.configure(bg=color)
            except tk.TclError:
                pass


if __name__ == "__main__":
    app_root = tk.Tk()
    ChatClientGUI(app_root)
    app_root.mainloop()
