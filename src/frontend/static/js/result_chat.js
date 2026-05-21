(function () {
    var dashboardRoot = document.getElementById("dashboard-root");
    if (!dashboardRoot) return;
    var taskId = dashboardRoot.getAttribute("data-task-id");
    if (!taskId) return;

    var SIDEBAR_KEY = "vibe.llm.sidebar.collapsed";
    var CHAT_HISTORY_KEY = "vibe.llm.chat.history." + taskId;

    var llmShell = document.getElementById("llm-shell");
    var llmOpen = document.getElementById("llm-open");
    var llmClose = document.getElementById("llm-close");
    var llmTestBtn = document.getElementById("llm-test-btn");
    var llmTestStatus = document.getElementById("llm-test-status");
    var chatHistory = document.getElementById("llm-chat-history");
    var chatForm = document.getElementById("llm-chat-form");
    var chatInput = document.getElementById("llm-chat-input");
    var chatSend = document.getElementById("llm-chat-send");
    var chatClear = document.getElementById("llm-chat-clear");
    var chatError = document.getElementById("llm-chat-error");

    var history = loadHistory();
    // 流式传输上下文，发送按钮变为停止按钮，中断时清除失败的对话轮次
    var stream = null;

    function setSidebarCollapsed(collapsed) {
        llmShell.classList.toggle("sidebar-collapsed", collapsed);
        try {
            localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
        } catch (e) { /* ignore */ }
    }

    function setTestStatus(text, kind) {
        if (!llmTestStatus) return;
        llmTestStatus.textContent = text || "";
        llmTestStatus.className = "llm-test-status small " + (
            kind === "ok" ? "text-success" :
            kind === "err" ? "text-danger" :
            "text-muted"
        );
    }

    function runLlmTest() {
        var baseUrl = document.getElementById("llm_base_url").value.trim();
        var apiKey = document.getElementById("llm_api_key").value.trim();
        var model = document.getElementById("llm_model").value.trim();
        if (!baseUrl || !model) {
            setTestStatus("请先填写 Base URL 和模型名", "err");
            return;
        }
        llmTestBtn.disabled = true;
        setTestStatus("正在测试...", "muted");
        AppCommon.fetchJson("/api/llm/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, model: model })
        }).then(function (response) {
            if (response.code === 0) {
                setTestStatus(response.data.message || "连接成功", "ok");
            } else {
                setTestStatus(response.msg || "测试失败", "err");
            }
        }).catch(function (error) {
            setTestStatus("测试失败：" + error.message, "err");
        }).finally(function () {
            llmTestBtn.disabled = false;
        });
    }

    function loadHistory() {
        try {
            var raw = sessionStorage.getItem(CHAT_HISTORY_KEY);
            if (!raw) return [];
            var parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            return [];
        }
    }

    function saveHistory() {
        try {
            sessionStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(history));
        } catch (e) { /* ignore */ }
    }

    function makeBubble(entry, isStreaming) {
        var wrapper = document.createElement("div");
        wrapper.className = "chat-message chat-message-" + entry.role
            + (isStreaming ? " chat-message-streaming" : "");

        var avatar = document.createElement("span");
        avatar.className = "chat-avatar";
        avatar.innerHTML = entry.role === "user"
            ? '<i class="bi bi-person-circle"></i>'
            : '<i class="bi bi-stars"></i>';

        var bubble = document.createElement("div");
        bubble.className = "chat-bubble chat-bubble-" + entry.role;
        if (entry.role === "assistant") {
            if (!entry.content) {
                bubble.innerHTML = '<span class="chat-typing"><span></span><span></span><span></span></span>';
            } else {
                bubble.innerHTML = AppCommon.renderMarkdown(entry.content);
            }
        } else {
            bubble.textContent = entry.content || "";
        }
        wrapper.appendChild(avatar);
        wrapper.appendChild(bubble);
        return wrapper;
    }

    function renderHistory() {
        chatHistory.innerHTML = "";
        if (!history.length) {
            var empty = document.createElement("div");
            empty.className = "text-muted small llm-chat-empty";
            empty.textContent = "分析完成后，在下方输入你想问的问题，我会基于当前任务的数据作答。";
            chatHistory.appendChild(empty);
            return;
        }
        history.forEach(function (entry, idx) {
            var isStreaming = stream && idx === stream.assistantIdx;
            chatHistory.appendChild(makeBubble(entry, isStreaming));
        });
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function setError(message) {
        chatError.textContent = message || "";
        chatError.classList.toggle("d-none", !message);
    }

    function setSendButtonState(mode) {
        // mode: "send" | "stop"
        if (mode === "stop") {
            chatSend.classList.remove("btn-primary");
            chatSend.classList.add("btn-danger");
            chatSend.innerHTML = '<i class="bi bi-stop-circle me-1"></i>停止';
            chatSend.type = "button";
        } else {
            chatSend.classList.remove("btn-danger");
            chatSend.classList.add("btn-primary");
            chatSend.innerHTML = '<i class="bi bi-send me-1"></i>发送';
            chatSend.type = "submit";
        }
    }

    // 就地更新助手气泡内容，避免整体重渲染
    function updateStreamingBubble() {
        if (!stream) return;
        var bubbles = chatHistory.querySelectorAll(".chat-bubble-assistant");
        var bubble = bubbles[bubbles.length - 1];
        if (!bubble) return;
        var text = stream.accumulated;
        bubble.innerHTML = text
            ? AppCommon.renderMarkdown(text)
            : '<span class="chat-typing"><span></span><span></span><span></span></span>';
        // 模型输出时自动滚动到底部
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // 丢弃正在进行的对话轮次，中断的对话不留痕迹
    function discardCurrentStream() {
        if (!stream) return;
        // history layout: [..., user(userIdx), assistant(assistantIdx)]
        history.splice(stream.userIdx, 2);
        stream = null;
        saveHistory();
        renderHistory();
    }

    function finishStreamSuccessfully() {
        if (!stream) return;
        var idx = stream.assistantIdx;
        if (!history[idx] || !history[idx].content) {
            // 模型返回空回复，视为失败轮次
            discardCurrentStream();
            setError("模型返回了空回复");
            return;
        }
        stream = null;
        saveHistory();
        renderHistory();
    }

    // 将缓冲区解析为完整的 SSE 事件
    function parseSseBuffer(buf) {
        var events = [];
        while (true) {
            var sep = buf.indexOf("\n\n");
            if (sep === -1) break;
            var rawEvent = buf.slice(0, sep);
            buf = buf.slice(sep + 2);
            var lines = rawEvent.split("\n");
            var dataLines = [];
            for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (line.indexOf("data:") === 0) {
                    dataLines.push(line.slice(5).trim());
                }
            }
            if (!dataLines.length) continue;
            try {
                events.push(JSON.parse(dataLines.join("\n")));
            } catch (e) { /* skip malformed frame */ }
        }
        return { events: events, rest: buf };
    }

    async function streamSse(payload) {
        var controller = new AbortController();
        stream = {
            controller: controller,
            userIdx: history.length - 2,
            assistantIdx: history.length - 1,
            accumulated: "",
        };
        setSendButtonState("stop");
        chatInput.disabled = true;

        var response;
        try {
            response = await fetch("/api/result/" + taskId + "/llm-chat-stream", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream"
                },
                body: JSON.stringify(payload),
                signal: controller.signal,
            });
        } catch (err) {
            if (err.name !== "AbortError") {
                setError("连接失败：" + err.message);
            }
            discardCurrentStream();
            setSendButtonState("send");
            chatInput.disabled = false;
            chatInput.focus();
            return;
        }

        if (!response.ok || !response.body) {
            setError("HTTP " + response.status);
            discardCurrentStream();
            setSendButtonState("send");
            chatInput.disabled = false;
            chatInput.focus();
            return;
        }

        var reader = response.body.getReader();
        var decoder = new TextDecoder("utf-8");
        var buf = "";
        var encounteredError = null;
        var doneFlag = false;

        try {
            while (true) {
                var chunk = await reader.read();
                if (chunk.done) break;
                buf += decoder.decode(chunk.value, { stream: true });
                var parsed = parseSseBuffer(buf);
                buf = parsed.rest;
                for (var i = 0; i < parsed.events.length; i++) {
                    var ev = parsed.events[i];
                    if (ev.error) {
                        encounteredError = ev.error;
                        break;
                    }
                    if (ev.done) {
                        doneFlag = true;
                        break;
                    }
                    if (typeof ev.delta === "string" && stream) {
                        stream.accumulated += ev.delta;
                        history[stream.assistantIdx].content = stream.accumulated;
                        updateStreamingBubble();
                    }
                }
                if (encounteredError || doneFlag) break;
            }
        } catch (err) {
            if (err.name !== "AbortError") {
                encounteredError = err.message || String(err);
            }
            // AbortError 静默处理，由 discardCurrentStream 清理
        }

        if (encounteredError) {
            setError(encounteredError);
            discardCurrentStream();
        } else if (!stream) {
            // Already discarded by an explicit stop click.
        } else if (!doneFlag) {
            // 连接未正常结束，丢弃半成品回复
            discardCurrentStream();
        } else {
            finishStreamSuccessfully();
        }

        setSendButtonState("send");
        chatInput.disabled = false;
        chatInput.focus();
    }

    function sendQuestion(question) {
        var baseUrl = document.getElementById("llm_base_url").value.trim();
        var apiKey = document.getElementById("llm_api_key").value.trim();
        var model = document.getElementById("llm_model").value.trim();
        var contextFormat = document.getElementById("llm_context_format").value || "xml";

        if (!baseUrl || !model) {
            setError("请先在上方填写 Base URL 和模型名");
            return;
        }

        setError("");

        // 快照已完成的对话历史用于上游发送
        var historyForUpstream = history.slice();

        history.push({ role: "user", content: question });
        history.push({ role: "assistant", content: "" });
        renderHistory();
        // 故意不立即保存，仅在成功后持久化

        streamSse({
            base_url: baseUrl,
            api_key: apiKey,
            model: model,
            question: question,
            context_format: contextFormat,
            history: historyForUpstream
        });
    }

    function stopActiveStream() {
        if (!stream) return;
        try { stream.controller.abort(); } catch (e) { /* ignore */ }
        // streamSse will see AbortError and call discardCurrentStream() in finally.
    }

    chatForm.addEventListener("submit", function (event) {
        event.preventDefault();
        if (stream) {
            // 按钮当前为停止模式，中止而非提交
            stopActiveStream();
            return;
        }
        var question = chatInput.value.trim();
        if (!question) return;
        chatInput.value = "";
        sendQuestion(question);
    });

    chatSend.addEventListener("click", function (event) {
        if (stream) {
            event.preventDefault();
            stopActiveStream();
        }
    });

    // Enter 发送，Shift+Enter 换行
    chatInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
        }
    });

    chatClear.addEventListener("click", function () {
        if (stream) stopActiveStream();
        history = [];
        try { sessionStorage.removeItem(CHAT_HISTORY_KEY); } catch (e) { /* ignore */ }
        renderHistory();
        setError("");
    });

    // 页面关闭时中断流式传输并清理进行中的对话
    window.addEventListener("beforeunload", function () {
        if (stream) {
            try { stream.controller.abort(); } catch (e) { /* ignore */ }
            history.splice(stream.userIdx, 2);
            try { sessionStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(history)); } catch (e) { /* ignore */ }
        }
    });

    if (llmClose) llmClose.addEventListener("click", function () { setSidebarCollapsed(true); });
    if (llmOpen) llmOpen.addEventListener("click", function () { setSidebarCollapsed(false); });
    if (llmTestBtn) llmTestBtn.addEventListener("click", runLlmTest);

    var storedCollapsed = "0";
    try { storedCollapsed = localStorage.getItem(SIDEBAR_KEY) || "0"; } catch (e) { /* ignored */ }
    setSidebarCollapsed(storedCollapsed === "1");

    AppCommon.applyLlmConfigToForm({});
    AppCommon.loadLlmConfig().then(function (values) {
        AppCommon.applyLlmConfigToForm(values);
    });
    AppCommon.bindLlmConfigPersistence();

    renderHistory();
})();
