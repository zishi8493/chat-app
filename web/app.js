const loginView = document.querySelector("#loginView");
const chatView = document.querySelector("#chatView");
const authForm = document.querySelector("#authForm");
const nameInput = document.querySelector("#nameInput");
const passwordInput = document.querySelector("#passwordInput");
const loginButton = document.querySelector("#loginButton");
const registerButton = document.querySelector("#registerButton");
const loginStatus = document.querySelector("#loginStatus");
const connectionStatus = document.querySelector("#connectionStatus");
const logoutButton = document.querySelector("#logoutButton");
const chatTitle = document.querySelector("#chatTitle");
const contacts = document.querySelector("#contacts");
const messages = document.querySelector("#messages");
const messageForm = document.querySelector("#messageForm");
const messageInput = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");

let ws = null;
let myName = "";
let currentTarget = "all";
let onlineUsers = [];
let loggedIn = false;
let manualClose = false;
let pendingMode = "login";

function wsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws`;
}

function setLoginStatus(text, isError = false) {
  loginStatus.textContent = text;
  loginStatus.classList.toggle("error", isError);
}

function setConnectionStatus(text, isError = false) {
  connectionStatus.textContent = text;
  connectionStatus.classList.toggle("error", isError);
}

function setAuthBusy(isBusy) {
  loginButton.disabled = isBusy;
  registerButton.disabled = isBusy;
}

function showLogin() {
  chatView.classList.add("hidden");
  loginView.classList.remove("hidden");
  setAuthBusy(false);
  nameInput.focus();
}

function showChat() {
  loginView.classList.add("hidden");
  chatView.classList.remove("hidden");
  messageInput.focus();
}

function validateAuth() {
  const name = nameInput.value.trim();
  const password = passwordInput.value;
  if (!name || !password) {
    setLoginStatus("账号和密码不能为空。", true);
    return null;
  }
  if (/\s/.test(name)) {
    setLoginStatus("账号不能包含空格。", true);
    return null;
  }
  if (password.length < 6 || /\s/.test(password)) {
    setLoginStatus("密码至少 6 位，且不能包含空格。", true);
    return null;
  }
  return { name, password };
}

function openSocket(mode) {
  const auth = validateAuth();
  if (!auth) {
    return;
  }

  closeSocket(false);
  pendingMode = mode;
  manualClose = false;
  loggedIn = false;
  setAuthBusy(true);
  setLoginStatus(mode === "register" ? "正在注册..." : "正在连接服务器...");

  ws = new WebSocket(wsUrl());

  ws.addEventListener("open", () => {
    sendJson({ type: mode, name: auth.name, password: auth.password });
  });

  ws.addEventListener("message", (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    handleServerMessage(data);
  });

  ws.addEventListener("error", () => {
    if (!loggedIn) {
      setLoginStatus("连接失败，请确认服务器已启动。", true);
      setAuthBusy(false);
    }
  });

  ws.addEventListener("close", () => {
    const wasLoggedIn = loggedIn;
    loggedIn = false;
    ws = null;
    setAuthBusy(false);
    sendButton.disabled = true;
    if (manualClose) {
      return;
    }
    if (wasLoggedIn) {
      appendSystemMessage("连接已断开，请重新登录。");
      setConnectionStatus("连接已断开", true);
    } else if (pendingMode !== "register") {
      setLoginStatus("连接已断开，请稍后重试。", true);
      showLogin();
    }
  });
}

function sendJson(payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return false;
  }
  ws.send(JSON.stringify(payload));
  return true;
}

function handleServerMessage(data) {
  if (data.type === "register") {
    if (data.success) {
      setLoginStatus(data.message || "注册成功，请登录。");
      passwordInput.focus();
    } else {
      setLoginStatus(data.message || "注册失败。", true);
    }
    closeSocket(false);
    setAuthBusy(false);
    return;
  }

  if (data.type === "login") {
    if (data.success) {
      loggedIn = true;
      myName = nameInput.value.trim();
      passwordInput.value = "";
      currentTarget = "all";
      onlineUsers = [];
      messages.innerHTML = "";
      renderContacts();
      showChat();
      setConnectionStatus("已连接");
      sendButton.disabled = false;
      appendSystemMessage(data.message || "登录成功，可以开始聊天。");
    } else {
      setLoginStatus(data.message || "登录失败。", true);
      setAuthBusy(false);
      closeSocket(false);
    }
    return;
  }

  if (data.type === "history") {
    appendHistory(data.messages || []);
    return;
  }

  if (data.type === "users") {
    onlineUsers = Array.isArray(data.users) ? data.users : [];
    if (currentTarget !== "all" && !onlineUsers.includes(currentTarget)) {
      currentTarget = "all";
      chatTitle.textContent = "群聊";
    }
    renderContacts();
    return;
  }

  if (data.type === "chat") {
    appendChatMessage(data);
    return;
  }

  if (data.type === "system") {
    appendSystemMessage(data.message || "");
    return;
  }

  if (data.type === "error") {
    if (loggedIn) {
      appendSystemMessage(data.message || "发生错误。");
    } else {
      setLoginStatus(data.message || "发生错误。", true);
      setAuthBusy(false);
    }
  }
}

function renderContacts() {
  contacts.innerHTML = "";
  contacts.appendChild(createContactButton("群聊", "all"));

  for (const user of onlineUsers) {
    const label = user === myName ? `${user}（我）` : user;
    contacts.appendChild(createContactButton(label, user));
  }
}

function createContactButton(label, target) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "contact";
  button.textContent = label;
  button.title = label;
  button.classList.toggle("active", currentTarget === target);
  button.addEventListener("click", () => {
    currentTarget = target;
    chatTitle.textContent = target === "all" ? "群聊" : target;
    renderContacts();
    messageInput.focus();
  });
  return button;
}

function appendSystemMessage(text) {
  if (!text) {
    return;
  }
  const item = document.createElement("div");
  item.className = "system-message";
  item.textContent = text;
  messages.appendChild(item);
  scrollToBottom();
}

function appendHistory(history) {
  for (const item of history) {
    appendChatMessage(item, false);
  }
  if (history.length) {
    appendSystemMessage(`已加载最近 ${history.length} 条聊天记录`);
  }
}

function appendChatMessage(data, shouldScroll = true) {
  const sender = data.from || "";
  const target = data.to || "all";
  const isSelf = sender === myName;
  const isPrivate = target !== "all";

  const row = document.createElement("article");
  row.className = `message-row${isSelf ? " self" : ""}`;

  const meta = document.createElement("div");
  meta.className = "message-meta";
  const senderText = isSelf ? "我" : sender;
  const privateText = isPrivate ? " 私聊" : "";
  meta.textContent = `${data.time ? `${data.time}  ` : ""}${senderText}${privateText}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = data.message || "";

  row.append(meta, bubble);
  messages.appendChild(row);
  if (shouldScroll) {
    scrollToBottom();
  }
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    messages.scrollTop = messages.scrollHeight;
  });
}

function closeSocket(sendLogout = false) {
  if (!ws) {
    return;
  }
  manualClose = true;
  if (sendLogout && ws.readyState === WebSocket.OPEN) {
    sendJson({ type: "logout" });
  }
  ws.close();
  ws = null;
}

authForm.addEventListener("submit", (event) => {
  event.preventDefault();
  openSocket("login");
});

registerButton.addEventListener("click", () => {
  openSocket("register");
});

messageForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) {
    return;
  }
  if (!sendJson({ type: "chat", to: currentTarget, message })) {
    appendSystemMessage("发送失败，连接已断开。");
    setConnectionStatus("连接已断开", true);
    return;
  }
  messageInput.value = "";
  resizeMessageInput();
});

messageInput.addEventListener("input", resizeMessageInput);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    messageForm.requestSubmit();
  }
});

logoutButton.addEventListener("click", () => {
  closeSocket(true);
  loggedIn = false;
  myName = "";
  currentTarget = "all";
  onlineUsers = [];
  setLoginStatus("已退出，可以重新登录。");
  showLogin();
});

window.addEventListener("beforeunload", () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    sendJson({ type: "logout" });
  }
});

function resizeMessageInput() {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 110)}px`;
}

renderContacts();
