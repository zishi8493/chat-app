# 网络聊天应用

这是一个基于 TCP Socket 的多用户聊天程序，包含账号注册、账号登录、群聊、私聊和 SQLite 聊天记录保存功能。

## 文件说明

- `client_gui.py`：Tkinter 图形界面聊天客户端
- `server.py`：TCP 多用户聊天服务端，负责账号认证、消息转发和 SQLite 持久化
- `web_server.py`：手机网页版 HTTP 服务和 WebSocket 到 TCP 的桥接服务
- `web/`：手机网页版页面、样式和脚本
- `assets/`：登录页和聊天页背景图、应用图标
- `app.ico`：窗口和打包图标
- `网络聊天应用.spec`：PyInstaller 打包配置
- `release/网络聊天应用.exe`：旧客户端可执行程序

## 运行服务端

```powershell
python server.py
```

服务端默认监听：

```python
HOST = "0.0.0.0"
PORT = 9000
```

服务端首次启动会自动创建 `chat_app.db`，其中包含：

- `users`：账号、密码盐值和密码哈希
- `messages`：聊天记录

## 运行客户端源码

```powershell
python client_gui.py
```

客户端默认连接云端服务器：

```python
DEFAULT_HOST = "124.223.78.29"
DEFAULT_PORT = "9000"
```

首次使用请先在客户端点击“注册账号”，注册成功后再登录。

## 运行手机网页版

先启动新版聊天服务：

```powershell
python server.py
```

再启动手机网页桥接服务：

```powershell
python web_server.py --host 0.0.0.0 --port 8080 --chat-host 127.0.0.1 --chat-port 9000
```

手机浏览器访问：

```text
http://服务器公网IP:8080/
```

网页端和桌面端共用同一个 `server.py`、同一个 `chat_app.db`，账号和聊天记录互通。云端部署时需要放行 TCP `8080`；如果桌面客户端要公网直连，还需要放行 TCP `9000`。

## 直接运行软件

可以直接双击：

```text
release/网络聊天应用.exe
```

## 打包

```powershell
python -m PyInstaller --noconfirm .\网络聊天应用.spec
```

## 通信协议

注册：

```json
{"type":"register","name":"张三","password":"123456"}
```

登录：

```json
{"type":"login","name":"张三","password":"123456"}
```

群聊：

```json
{"type":"chat","to":"all","message":"大家好"}
```

私聊：

```json
{"type":"chat","to":"李四","message":"你好"}
```
