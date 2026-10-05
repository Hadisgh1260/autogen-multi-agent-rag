const API_BASE = "";


/* =========================================================
   STORAGE
   ========================================================= */

function getToken() {
    return localStorage.getItem("auth_token");
}


function setToken(token) {
    localStorage.setItem("auth_token", token);
}


function clearToken() {
    localStorage.removeItem("auth_token");
}


/* =========================================================
   HELPERS
   ========================================================= */

function authHeaders() {
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${getToken()}`
    };
}


function formatRemaining(seconds) {

    seconds = Math.max(
        0,
        Math.floor(seconds)
    );

    const hours = Math.floor(
        seconds / 3600
    );

    const minutes = Math.floor(
        (seconds % 3600) / 60
    );

    const secs = seconds % 60;

    return [
        String(hours).padStart(2, "0"),
        String(minutes).padStart(2, "0"),
        String(secs).padStart(2, "0")
    ].join(":");
}


/* =========================================================
   LOGIN
   ========================================================= */

const loginForm =
    document.getElementById("loginForm");


if (loginForm) {

    if (getToken()) {
        window.location.href = "/chat";
    }


    loginForm.addEventListener(
        "submit",
        async function (event) {

            event.preventDefault();

            const username =
                document
                    .getElementById("username")
                    .value
                    .trim();

            const password =
                document
                    .getElementById("password")
                    .value;

            const errorBox =
                document.getElementById("loginError");

            const loginButton =
                loginForm.querySelector(
                    "button[type='submit']"
                );


            errorBox.classList.add("hidden");

            loginButton.disabled = true;


            try {

                const response =
                    await fetch(
                        `${API_BASE}/api/login`,
                        {
                            method: "POST",

                            headers: {
                                "Content-Type":
                                    "application/json"
                            },

                            body: JSON.stringify({
                                username,
                                password
                            })
                        }
                    );


                const data =
                    await response.json();


                if (!response.ok) {

                    let message =
                        "Login failed.";

                    if (
                        typeof data.detail ===
                        "string"
                    ) {

                        message =
                            data.detail;

                    } else if (
                        data.detail &&
                        data.detail.message
                    ) {

                        message =
                            data.detail.message;
                    }

                    throw new Error(message);
                }


                setToken(data.token);

                window.location.href = "/chat";

            }


            catch (error) {

                errorBox.textContent =
                    error.message ||
                    "Login failed.";

                errorBox.classList.remove(
                    "hidden"
                );
            }


            finally {

                loginButton.disabled = false;
            }
        }
    );
}


/* =========================================================
   CHAT INITIALIZATION
   ========================================================= */

const chatForm =
    document.getElementById("chatForm");


if (chatForm) {
    initializeChat();
}


async function initializeChat() {

    if (!getToken()) {

        window.location.href = "/";

        return;
    }


    try {

        const response =
            await fetch(
                `${API_BASE}/api/me`,
                {
                    headers:
                        authHeaders()
                }
            );


        if (response.status === 401) {

            clearToken();

            window.location.href = "/";

            return;
        }


        const data =
            await response.json();


        const usernameLabel =
            document.getElementById(
                "usernameLabel"
            );


        if (usernameLabel) {

            usernameLabel.textContent =
                data.username;
        }


        updateCounter(
            data.off_topic_count,
            data.max_off_topic
        );


        /*
         * Personalized welcome message.
         */

        addWelcomeMessage(
            data.username
        );


        if (data.blocked) {

            showBlocked(
                data.remaining_seconds
            );
        }


        const textarea =
            document.getElementById(
                "question"
            );


        if (textarea && !data.blocked) {

            textarea.focus();
        }

    }


    catch (error) {

        console.error(
            "Chat initialization failed:",
            error
        );
    }
}


/* =========================================================
   WELCOME MESSAGE
   ========================================================= */

function addWelcomeMessage(username) {

    const messages =
        document.getElementById(
            "messages"
        );


    if (!messages) {
        return;
    }


    messages.innerHTML = "";


    addMessage(
        "assistant",
        `Hi ${username}! How can I help you today?`
    );
}


/* =========================================================
   CHAT SUBMIT
   ========================================================= */

chatForm?.addEventListener(
    "submit",
    async function (event) {

        event.preventDefault();


        const textarea =
            document.getElementById(
                "question"
            );

        const sendButton =
            document.getElementById(
                "sendButton"
            );


        const question =
            textarea.value.trim();


        if (!question) {
            return;
        }


        addMessage(
            "user",
            question
        );


        textarea.value = "";

        textarea.style.height = "auto";

        sendButton.disabled = true;

        sendButton.innerHTML =
            "<span>Thinking...</span>";


        try {

            const response =
                await fetch(
                    `${API_BASE}/api/chat`,
                    {
                        method: "POST",

                        headers:
                            authHeaders(),

                        body: JSON.stringify({
                            question
                        })
                    }
                );


            const data =
                await response.json();


            /* ---------------------------------------------
               UNAUTHORIZED
               --------------------------------------------- */

            if (
                response.status === 401
            ) {

                clearToken();

                window.location.href = "/";

                return;
            }


            /* ---------------------------------------------
               BLOCKED
               --------------------------------------------- */

            if (
                response.status === 403
            ) {

                const detail =
                    data.detail || {};


                if (
                    detail.blocked_until
                ) {

                    showBlocked(
                        detail.remaining_seconds ||
                        86400
                    );

                } else {

                    addMessage(
                        "assistant",
                        detail.message ||
                        "Your account is currently blocked."
                    );
                }

                return;
            }


            /* ---------------------------------------------
               OTHER ERROR
               --------------------------------------------- */

            if (!response.ok) {

                addMessage(
                    "assistant",
                    typeof data.detail === "string"
                        ? data.detail
                        : "Something went wrong."
                );

                return;
            }


            /* ---------------------------------------------
               NORMAL RESPONSE
               --------------------------------------------- */

            addMessage(
                "assistant",
                data.answer ||
                "I could not generate an answer."
            );


            updateCounter(
                data.off_topic_count,
                data.max_off_topic
            );


            if (data.blocked) {

                showBlocked(
                    data.remaining_seconds
                );
            }

        }


        catch (error) {

            console.error(
                "Chat request failed:",
                error
            );

            addMessage(
                "assistant",
                "Could not connect to the server. Please try again."
            );
        }


        finally {

            sendButton.disabled = false;

            sendButton.innerHTML =
                "<span>Send</span><span class='send-arrow'>→</span>";

            textarea.focus();
        }
    }
);


/* =========================================================
   ENTER TO SEND
   ========================================================= */

const questionInput =
    document.getElementById(
        "question"
    );


questionInput?.addEventListener(
    "keydown",
    function (event) {

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();

            chatForm?.requestSubmit();
        }
    }
);


/* =========================================================
   AUTO-RESIZE TEXTAREA
   ========================================================= */

questionInput?.addEventListener(
    "input",
    function () {

        this.style.height = "auto";

        this.style.height =
            Math.min(
                this.scrollHeight,
                180
            ) + "px";
    }
);


/* =========================================================
   ADD MESSAGE
   ========================================================= */

function addMessage(
    type,
    content
) {

    const messages =
        document.getElementById(
            "messages"
        );


    if (!messages) {
        return;
    }


    const message =
        document.createElement(
            "div"
        );


    message.className =
        `message ${type}`;


    const label =
        document.createElement(
            "div"
        );


    label.className =
        "message-label";


    label.textContent =
        type === "user"
            ? "You"
            : "AI";


    const body =
        document.createElement(
            "div"
        );


    body.className =
        "message-content";


    body.textContent =
        String(content ?? "");


    message.appendChild(label);

    message.appendChild(body);

    messages.appendChild(message);


    messages.scrollTop =
        messages.scrollHeight;
}


/* =========================================================
   COUNTER
   ========================================================= */

function updateCounter(
    count,
    max
) {

    const counter =
        document.getElementById(
            "counter"
        );


    if (!counter) {
        return;
    }


    counter.textContent =
        `Unrelated questions: ${count} / ${max}`;
}


/* =========================================================
   BLOCK SCREEN
   ========================================================= */

let countdownInterval = null;


function showBlocked(
    seconds
) {

    const blockBox =
        document.getElementById(
            "blockBox"
        );

    const chatForm =
        document.getElementById(
            "chatForm"
        );

    const messages =
        document.getElementById(
            "messages"
        );

    const countdown =
        document.getElementById(
            "countdown"
        );


    if (chatForm) {

        chatForm.classList.add(
            "hidden"
        );
    }


    if (messages) {

        messages.classList.add(
            "hidden"
        );
    }


    if (blockBox) {

        blockBox.classList.remove(
            "hidden"
        );
    }


    if (countdownInterval) {

        clearInterval(
            countdownInterval
        );
    }


    let remaining =
        Number(seconds) || 86400;


    if (countdown) {

        countdown.textContent =
            formatRemaining(
                remaining
            );
    }


    countdownInterval =
        setInterval(
            function () {

                remaining--;


                if (remaining <= 0) {

                    clearInterval(
                        countdownInterval
                    );

                    window.location.reload();

                    return;
                }


                if (countdown) {

                    countdown.textContent =
                        formatRemaining(
                            remaining
                        );
                }

            },
            1000
        );
}


/* =========================================================
   LOGOUT
   ========================================================= */

const logoutButton =
    document.getElementById(
        "logoutButton"
    );


logoutButton?.addEventListener(
    "click",
    async function () {

        logoutButton.disabled = true;


        try {

            await fetch(
                `${API_BASE}/api/logout`,
                {
                    method: "POST",

                    headers:
                        authHeaders()
                }
            );

        }

        catch (error) {

            console.error(
                "Logout failed:",
                error
            );
        }


        clearToken();

        window.location.href = "/";
    }
);