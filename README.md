# 网络聊天应用客户端源码

这是从 `dist/网络聊天应用.exe` 对应的旧版客户端还原整理出的源码。

## 文件说明

- `client_gui.py`：Tkinter 图形界面聊天客户端
- `server.py`：TCP 多用户聊天服务端
- `assets/`：登录页和聊天页背景图、应用图标
- `app.ico`：窗口和打包图标
- `网络聊天应用.spec`：PyInstaller 打包配置
- `release/网络聊天应用.exe`：旧客户端可执行程序

## 运行客户端源码

```powershell
python client_gui.py
```

客户端默认连接云端服务器：

```python
DEFAULT_HOST = "124.223.78.29"
DEFAULT_PORT = "9000"
```

## 运行服务端

```powershell
python server.py
```

服务端默认监听：

```python
HOST = "0.0.0.0"
PORT = 9000
```

## 直接运行软件

可以直接双击：

```text
release/网络聊天应用.exe
```

## 打包

```powershell
python -m PyInstaller --noconfirm .\网络聊天应用.spec
```
