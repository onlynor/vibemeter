(function () {
    var form = document.getElementById("task-form");
    if (!form) return;

    var keywordInput = document.getElementById("keyword");
    var errorNode = document.getElementById("form-error");
    var submitButton = document.getElementById("submit-button");
    var submitText = submitButton.querySelector("span");
    var hotspotLoading = document.getElementById("hotspot-loading");
    var hotspotError = document.getElementById("hotspot-error");
    var hotspotList = document.getElementById("hotspot-list");
    var hotspotSection = document.getElementById("hotspot-section");
    var llmShell = document.getElementById("llm-shell");
    var llmOpen = document.getElementById("llm-open");
    var llmClose = document.getElementById("llm-close");
    var llmPreview = document.getElementById("llm-preview");
    var llmTestBtn = document.getElementById("llm-test-btn");
    var llmTestStatus = document.getElementById("llm-test-status");

    var SIDEBAR_KEY = "vibe.llm.sidebar.collapsed";

    function setError(message) {
        errorNode.textContent = message || "";
        errorNode.classList.toggle("d-none", !message);
    }

    function updatePreview() {
        var question = document.getElementById("llm_question").value.trim();
        llmPreview.textContent = question ? question : "留空则不调用";
    }

    function setSidebarCollapsed(collapsed) {
        llmShell.classList.toggle("sidebar-collapsed", collapsed);
        try {
            localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0");
        } catch (e) {
            /* storage may be disabled — degrade gracefully */
        }
    }

    function setTestStatus(text, kind) {
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

    function renderHotspots(items) {
        hotspotList.innerHTML = "";
        if (!items.length) {
            hotspotSection.classList.add("d-none");
            return;
        }
        hotspotSection.classList.remove("d-none");
        hotspotList.classList.remove("d-none");

        items.forEach(function (item) {
            var jumpLabel = item.is_mock ? "打开搜索页" : "打开来源页";
            var button = document.createElement("button");
            button.type = "button";
            button.className = "hotspot-item";
            button.innerHTML =
                '<div class="d-flex gap-3">' +
                '  <span class="hotspot-rank">' + AppCommon.escapeHtml(item.rank) + '</span>' +
                '  <div class="flex-grow-1">' +
                '    <div class="d-flex justify-content-between gap-2">' +
                '      <div class="hotspot-title">' + AppCommon.escapeHtml(item.title) + '</div>' +
                '      <span class="hotspot-source"><i class="bi bi-fire"></i><span>' + AppCommon.escapeHtml(AppCommon.platformLabel(item.source)) + '</span></span>' +
                '    </div>' +
                '    <div class="text-muted small mt-1">' + AppCommon.escapeHtml(item.subtitle || "暂无摘要") + '</div>' +
                '    <div class="d-flex justify-content-between align-items-center gap-2 mt-2">' +
                '      <div class="hotspot-meta">热度值：' + AppCommon.escapeHtml(item.score || "—") + '</div>' +
                (item.url ? ('<a class="hotspot-jump" href="' + AppCommon.escapeHtml(item.url) + '" target="_blank" rel="noopener">' + jumpLabel + '</a>') : "") +
                '    </div>' +
                '  </div>' +
                '</div>';
            button.addEventListener("click", function (event) {
                if (event.target.closest("a")) return;
                keywordInput.value = item.title || "";
                keywordInput.focus();
            });
            hotspotList.appendChild(button);
        });
    }

    function loadHotspots() {
        hotspotSection.classList.remove("d-none");
        hotspotLoading.classList.remove("d-none");
        hotspotError.classList.add("d-none");
        hotspotList.classList.add("d-none");
        AppCommon.fetchJson("/api/hotspots").then(function (payload) {
            var items = (payload.data || []).filter(function (item) {
                return item && item.title;
            });
            renderHotspots(items);
        }).catch(function (error) {
            hotspotSection.classList.add("d-none");
            hotspotError.textContent = "热搜加载失败：" + error.message;
        }).finally(function () {
            hotspotLoading.classList.add("d-none");
        });
    }

    function submitTask(event) {
        event.preventDefault();
        setError("");

        if (!keywordInput.value.trim()) {
            setError("请输入关键词");
            return;
        }

        submitButton.disabled = true;
        submitText.textContent = "正在创建任务...";

        var llmValues = AppCommon.collectLlmConfigFromForm();
        AppCommon.saveLlmConfig(llmValues);

        var payload = {
            keyword: keywordInput.value.trim(),
            platform: document.getElementById("platform").value,
            count: Number(document.getElementById("count").value || 500),
            llm_base_url: llmValues.llm_base_url,
            llm_model: llmValues.llm_model,
            llm_api_key: llmValues.llm_api_key,
            llm_question: llmValues.llm_question,
            llm_context_format: llmValues.llm_context_format || "xml"
        };

        AppCommon.fetchJson("/api/task", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        }).then(function (response) {
            var taskId = response && response.data && response.data.task_id;
            if (!taskId) throw new Error("任务创建失败");
            location.href = "/result/" + taskId;
        }).catch(function (error) {
            setError("任务创建失败：" + error.message);
        }).finally(function () {
            submitButton.disabled = false;
            submitText.textContent = "开始分析";
        });
    }

    document.getElementById("refresh-hotspots").addEventListener("click", loadHotspots);
    form.addEventListener("submit", submitTask);
    document.getElementById("llm_question").addEventListener("input", updatePreview);

    if (llmClose) llmClose.addEventListener("click", function () { setSidebarCollapsed(true); });
    if (llmOpen) llmOpen.addEventListener("click", function () { setSidebarCollapsed(false); });
    if (llmTestBtn) llmTestBtn.addEventListener("click", runLlmTest);

    // ---- Recent tasks ---------------------------------------------------
    var historyLoading = document.getElementById("history-loading");
    var historyError = document.getElementById("history-error");
    var historyEmpty = document.getElementById("history-empty");
    var historyList = document.getElementById("history-list");
    var historyRefresh = document.getElementById("refresh-history");

    function setHistoryState(state) {
        // state: "loading" | "error" | "empty" | "ready"
        historyLoading.classList.toggle("d-none", state !== "loading");
        historyError.classList.toggle("d-none", state !== "error");
        historyEmpty.classList.toggle("d-none", state !== "empty");
        historyList.classList.toggle("d-none", state !== "ready");
    }

    function renderHistory(items) {
        historyList.innerHTML = "";
        if (!(items || []).length) {
            setHistoryState("empty");
            return;
        }
        items.forEach(function (item) {
            var row = document.createElement("a");
            row.href = item.url;
            row.className = "history-item";
            row.innerHTML =
                '<div class="history-item-top">' +
                '  <span class="history-item-no">' +
                AppCommon.escapeHtml(item.display_no || AppCommon.formatTaskNo(item.task_no)) +
                '  </span>' +
                '  <span class="history-item-status">' + AppCommon.escapeHtml(item.status || "") + '</span>' +
                '</div>' +
                '<div class="history-item-keyword">' + AppCommon.escapeHtml(item.keyword || "") + '</div>' +
                '<div class="history-item-meta">' +
                AppCommon.escapeHtml(AppCommon.platformLabel(item.platform || "")) +
                ' · ' + AppCommon.escapeHtml(AppCommon.formatDateTime(item.start_time || "")) +
                ' · ' + AppCommon.escapeHtml(String(item.total_count || 0)) + '条' +
                '</div>';
            historyList.appendChild(row);
        });
        setHistoryState("ready");
    }

    function loadHistory() {
        setHistoryState("loading");
        AppCommon.fetchJson("/api/tasks/history").then(function (response) {
            // /api/tasks/history wraps in {code, data}; tolerate either shape.
            var items = response && response.data ? response.data : response;
            renderHistory(Array.isArray(items) ? items : []);
        }).catch(function (err) {
            historyError.textContent = "加载历史任务失败：" + err.message;
            setHistoryState("error");
        });
    }

    if (historyRefresh) historyRefresh.addEventListener("click", loadHistory);

    var storedCollapsed = "0";
    try { storedCollapsed = localStorage.getItem(SIDEBAR_KEY) || "0"; } catch (e) { /* ignored */ }
    setSidebarCollapsed(storedCollapsed === "1");

    // Restore previously entered LLM config so the user doesn't re-type
    // every visit, then persist any further edits on change. Config now
    // lives in server memory rather than localStorage, so this is async.
    AppCommon.loadLlmConfig().then(function (values) {
        AppCommon.applyLlmConfigToForm(values);
        updatePreview();
    });
    AppCommon.bindLlmConfigPersistence();

    updatePreview();
    loadHotspots();
    loadHistory();
})();
