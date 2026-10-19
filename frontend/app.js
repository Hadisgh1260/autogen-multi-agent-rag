
const API_BASE = "";

let activeChatId = null;
let isLoadingChat = false;
let isSending = false;
let authToken = localStorage.getItem("auth_token") || "";

const $ = (id) => document.getElementById(id);

function authHeaders(extra = {}) {
    return {
        ...extra,
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    };
}

async function apiRequest(url, options = {}) {
    const response = await fetch(`${API_BASE}${url}`, {
        ...options,
        headers: authHeaders({
            ...(options.body ? { "Content-Type": "application/json" } : {}),
            ...(options.headers || {}),
        }),
    });

    let data = {};
    try {
        data = await response.json();
    } catch {
        // The response may have no JSON body.
    }

    if (!response.ok) {
        const error = new Error(
            data.detail || data.message || `Request failed (${response.status})`
        );
        error.status = response.status;
        error.data = data;
        throw error;
    }

    return data;
}

function showElement(element, visible = true) {
    if (element) {
        element.hidden = !visible;
    }
}

function setText(id, value) {
    const element = $(id);
    if (element) element.textContent = value ?? "";
}

function escapeText(value) {
    return String(value ?? "");
}

/* ---------------------------
   LOGIN AND AUTHENTICATION
---------------------------- */

async function handleLogin(event) {
    event.preventDefault();

    const form = $("loginForm");
    const username = $("username")?.value.trim();
    const password = $("password")?.value;
    const errorElement = $("loginError");
    const submitButton = form?.querySelector('[type="submit"]');

    if (errorElement) {
        errorElement.textContent = "";
        errorElement.hidden = true;
    }

    if (!username || !password) {
        showLoginError("Please enter your username and password.");
        return;
    }

    const turnstileResponse =
        document.querySelector('[name="cf-turnstile-response"]')?.value || "";

    const turnstileWidget = document.querySelector(".cf-turnstile");

    if (turnstileWidget && !turnstileResponse) {
        showLoginError("Please complete the security verification.");
        return;
    }

    if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = "Signing in...";
    }

    try {
        const response = await fetch(`${API_BASE}/api/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username,
                password,
                turnstile_token: turnstileResponse,
            }),
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(
                data.detail || data.message || "Login failed. Please try again."
            );
        }

        authToken = data.access_token || data.token || "";
        if (authToken) {
            localStorage.setItem("auth_token", authToken);
        }

        window.location.href = "/chat";
    } catch (error) {
        showLoginError(error.message || "Unable to sign in.");
        if (window.turnstile) {
            window.turnstile.reset();
        }
    } finally {
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.textContent = "Login";
        }
    }
}

function showLoginError(message) {
    const errorElement = $("loginError");
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.hidden = false;
    } else {
        alert(message);
    }
}

/* ---------------------------
   CHAT INITIALIZATION
---------------------------- */

async function initializeChat() {
    try {
        const me = await apiRequest("/api/me");

        const username =
            me.username ||
            me.user?.username ||
            "User";

        setText("usernameDisplay", username);
        setText("welcomeUsername", username);

        await loadChatHistory();
    } catch (error) {
        if (error.status === 401 || error.status === 403) {
            localStorage.removeItem("auth_token");
            window.location.href = "/";
            return;
        }

        console.error("Chat initialization failed:", error);
        showChatError("Unable to load your chats. Please refresh the page.");
    }
}

/* ---------------------------
   CHAT HISTORY
---------------------------- */

async function loadChatHistory() {
    try {
        const data = await apiRequest("/api/chats");
        const chats = Array.isArray(data.chats) ? data.chats : [];

        renderChatHistory(chats);

        const selectedId =
            data.active_chat_id ??
            chats[0]?.id ??
            null;

        if (selectedId !== null) {
            await openChat(selectedId, false);
            renderChatHistory(chats);
        } else {
            activeChatId = null;
            clearMessages();
            showWelcomeMessage();
        }
    } catch (error) {
        console.error("Could not load chat history:", error);
        showChatError("Could not load chat history.");
    }
}

function renderChatHistory(chats) {
    const history = $("chatHistory");
    if (!history) return;

    history.replaceChildren();

    if (!chats.length) {
        const empty = document.createElement("p");
        empty.className = "chat-history-empty";
        empty.textContent = "No chats yet";
        history.appendChild(empty);
        return;
    }

    chats.forEach((chat) => {
        history.appendChild(createChatHistoryItem(chat));
    });

    updateActiveHistoryItem();
}

function createChatHistoryItem(chat) {
    const item = document.createElement("div");
    item.className = "chat-history-item";
    item.dataset.chatId = String(chat.id);

    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "chat-history-open";
    openButton.textContent = chat.title || "New Chat";
    openButton.title = chat.title || "New Chat";
    openButton.addEventListener("click", () => {
        openChat(chat.id);
        closeMobileSidebar();
    });

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "chat-history-delete";
    deleteButton.textContent = "×";
    deleteButton.title = "Delete chat";
    deleteButton.setAttribute("aria-label", "Delete chat");
    deleteButton.addEventListener("click", (event) => {
        event.stopPropagation();
        deleteChat(chat.id);
    });

    item.append(openButton, deleteButton);
    return item;
}

function updateActiveHistoryItem() {
    document.querySelectorAll(".chat-history-item").forEach((item) => {
        item.classList.toggle(
            "active",
            Number(item.dataset.chatId) === Number(activeChatId)
        );
    });
}

async function refreshChatHistory(selectedChatId = activeChatId) {
    try {
        const data = await apiRequest("/api/chats");
        const chats = Array.isArray(data.chats) ? data.chats : [];

        renderChatHistory(chats);

        if (selectedChatId !== null && selectedChatId !== undefined) {
            activeChatId = selectedChatId;
        }

        updateActiveHistoryItem();
    } catch (error) {
        console.error("Could not refresh chat history:", error);
    }
}

/* ---------------------------
   OPEN AND CREATE CHATS
---------------------------- */

async function openChat(chatId, refreshHistory = true) {
    if (isLoadingChat || chatId === null || chatId === undefined) {
        return;
    }

    isLoadingChat = true;

    try {
        const data = await apiRequest(`/api/chats/${encodeURIComponent(chatId)}`);

        activeChatId = data.chat?.id ?? chatId;

        clearMessages();

        const messages = Array.isArray(data.messages) ? data.messages : [];

        if (!messages.length) {
            showWelcomeMessage();
        } else {
            messages.forEach((message) => {
                const type =
                    message.role === "user" || message.sender === "user"
                        ? "user"
                        : "assistant";

                addMessage(type, message.content ?? message.message ?? "");
            });
        }

        updateActiveHistoryItem();

        if (refreshHistory) {
            await refreshChatHistory(activeChatId);
        }
    } catch (error) {
        console.error("Could not open chat:", error);
        showChatError("Unable to open this chat.");
    } finally {
        isLoadingChat = false;
    }
}

async function createNewChat() {
    try {
        const data = await apiRequest("/api/chats", {
            method: "POST",
            body: JSON.stringify({}),
        });

        const chat = data.chat || data;

        if (chat.id === undefined || chat.id === null) {
            throw new Error("The server did not return a chat ID.");
        }

        activeChatId = chat.id;
        clearMessages();
        showWelcomeMessage();

        await refreshChatHistory(activeChatId);
        closeMobileSidebar();
        $("question")?.focus();
    } catch (error) {
        console.error("Could not create a chat:", error);
        showChatError("Unable to create a new chat.");
    }
}

/* ---------------------------
   DELETE CHAT
---------------------------- */

async function deleteChat(chatId) {
    const confirmed = confirm(
        "Are you sure you want to delete this chat?"
    );

    if (!confirmed) return;

    try {
        const data = await apiRequest(
            `/api/chats/${encodeURIComponent(chatId)}`,
            { method: "DELETE" }
        );

        const chats = Array.isArray(data.chats) ? data.chats : [];
        const wasActive = Number(chatId) === Number(activeChatId);

        if (wasActive) {
            const nextId =
                data.active_chat_id ??
                chats[0]?.id ??
                null;

            if (nextId !== null) {
                activeChatId = nextId;
                await openChat(nextId, false);
            } else {
                activeChatId = null;
                clearMessages();
                showWelcomeMessage();
            }
        }

        renderChatHistory(chats);
        updateActiveHistoryItem();
    } catch (error) {
        console.error("Could not delete chat:", error);
        showChatError(error.message || "Unable to delete this chat.");
    }
}

/* ---------------------------
   MESSAGES
---------------------------- */

function clearMessages() {
    const messages = $("messages");
    if (messages) messages.replaceChildren();
}

function showWelcomeMessage() {
    const messages = $("messages");
    if (!messages) return;

    const welcome = document.createElement("div");
    welcome.className = "welcome-message";

    const title = document.createElement("h2");
    title.textContent = "How can I help you today?";

    const subtitle = document.createElement("p");
    subtitle.textContent =
        "Ask me a backend, frontend, or software-engineering question.";

    welcome.append(title, subtitle);
    messages.appendChild(welcome);
}

function addMessage(type, content) {
    const messages = $("messages");
    if (!messages) return;

    messages.querySelector(".welcome-message")?.remove();

    const message = document.createElement("div");
    message.className = `message ${type}-message`;

    const label = document.createElement("div");
    label.className = "message-label";
    label.textContent = type === "user" ? "You" : "AI";

    const body = document.createElement("div");
    body.className = "message-content";
    body.textContent = escapeText(content);

    message.append(label, body);
    messages.appendChild(message);
    messages.scrollTop = messages.scrollHeight;
}

function showChatError(message) {
    console.error(message);

    const errorElement = $("chatError");
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.hidden = false;

        window.setTimeout(() => {
            errorElement.hidden = true;
        }, 5000);
    }
}

/* ---------------------------
   SEND MESSAGE
---------------------------- */

async function sendMessage(event) {
    event.preventDefault();

    if (isSending) return;

    const questionInput = $("question");
    const sendButton = $("sendButton");
    const question = questionInput?.value.trim();

    if (!question) return;

    isSending = true;

    if (sendButton) sendButton.disabled = true;
    if (questionInput) questionInput.disabled = true;

    questionInput.value = "";
    addMessage("user", question);

    try {
        if (activeChatId === null) {
            const created = await apiRequest("/api/chats", {
                method: "POST",
                body: JSON.stringify({}),
            });

            const chat = created.chat || created;
            activeChatId = chat.id;
        }

        const data = await apiRequest("/api/chat", {
            method: "POST",
            body: JSON.stringify({
                question,
                chat_id: activeChatId,
            }),
        });

        if (data.chat_id !== undefined && data.chat_id !== null) {
            activeChatId = data.chat_id;
        }

        if (data.answer) {
            addMessage("assistant", data.answer);
        } else {
            addMessage(
                "assistant",
                "I couldn't generate an answer. Please try again."
            );
        }

        updateOffTopicCounter(data);
        await refreshChatHistory(activeChatId);

        if (data.blocked || data.blocked_until) {
            showBlockMessage(data);
        }
    } catch (error) {
        console.error("Message request failed:", error);

        if (error.status === 403) {
            const data = error.data || {};

            if (data.blocked || data.blocked_until) {
                showBlockMessage(data);
            } else {
                addMessage(
                    "assistant",
                    data.detail || "Your request was denied."
                );
            }
        } else {
            addMessage(
                "assistant",
                error.message || "Something went wrong. Please try again."
            );
        }
    } finally {
        isSending = false;

        if (sendButton) sendButton.disabled = false;
        if (questionInput) {
            questionInput.disabled = false;
            questionInput.focus();
        }
    }
}

function updateOffTopicCounter(data) {
    const count =
        data.off_topic_count ??
        data.off_topic ??
        data.off_topic_attempts;

    const max = data.max_off_topic ?? 3;

    if (count !== undefined) {
        setText("offTopicCounter", `${count}/${max}`);
        setText("counter", `${count}/${max}`);
    }
}

function showBlockMessage(data) {
    const blockBox = $("blockBox");
    if (!blockBox) {
        addMessage(
            "assistant",
            data.detail || "Your account is temporarily blocked."
        );
        return;
    }

    blockBox.hidden = false;
    blockBox.textContent =
        data.detail ||
        "Your account is temporarily blocked. Please try again later.";

    const form = $("chatForm");
    if (form) {
        form.querySelectorAll("input, textarea, button").forEach((element) => {
            element.disabled = true;
        });
    }
}

/* ---------------------------
   LOGOUT
---------------------------- */

async function logout() {
    try {
        await apiRequest("/api/logout", { method: "POST" });
    } catch (error) {
        console.warn("Logout request failed:", error);
    } finally {
        authToken = "";
        localStorage.removeItem("auth_token");
        window.location.href = "/";
    }
}

/* ---------------------------
   MOBILE SIDEBAR
---------------------------- */

function openMobileSidebar() {
    $("chatSidebar")?.classList.add("open");
    $("sidebarOverlay")?.classList.add("visible");
}

function closeMobileSidebar() {
    $("chatSidebar")?.classList.remove("open");
    $("sidebarOverlay")?.classList.remove("visible");
}

/* ---------------------------
   EVENT LISTENERS
---------------------------- */

document.addEventListener("DOMContentLoaded", () => {
    $("loginForm")?.addEventListener("submit", handleLogin);

    $("chatForm")?.addEventListener("submit", sendMessage);

    $("newChatButton")?.addEventListener("click", createNewChat);

    $("logoutButton")?.addEventListener("click", logout);
    $("logoutBtn")?.addEventListener("click", logout);

    $("question")?.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            $("chatForm")?.requestSubmit();
        }
    });

    $("sidebarToggle")?.addEventListener("click", openMobileSidebar);
    $("closeSidebarButton")?.addEventListener("click", closeMobileSidebar);
    $("sidebarOverlay")?.addEventListener("click", closeMobileSidebar);

    if ($("chatForm") || $("chatHistory")) {
        initializeChat();
    }
});