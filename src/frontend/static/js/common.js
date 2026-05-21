(function () {
    function fetchJson(url, options) {
        return fetch(url, options || {}).then(async function (response) {
            var data = await response.json();
            if (!response.ok) {
                throw new Error((data && (data.msg || data.detail)) || ("HTTP " + response.status));
            }
            return data;
        });
    }

    function platformLabel(platform) {
        return ({
            auto: "聚合搜索",
            bilibili: "B站",
            baidu: "百度",
            weibo: "微博"
        })[platform] || platform;
    }

    function formatSize(bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / 1024 / 1024).toFixed(1) + " MB";
    }

    function escapeHtml(text) {
        return String(text == null ? "" : text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatTaskNo(taskNo) {
        var num = Number(taskNo || 0);
        if (!num) return "-";
        return "#" + String(num).padStart(4, "0");
    }

    function formatDateTime(value) {
        if (!value) return "";
        var normalized = String(value).replace(" ", "T");
        var date = new Date(normalized);
        if (Number.isNaN(date.getTime())) {
            return String(value).replace("T", " ");
        }
        var yyyy = date.getFullYear();
        var mm = String(date.getMonth() + 1).padStart(2, "0");
        var dd = String(date.getDate()).padStart(2, "0");
        var hh = String(date.getHours()).padStart(2, "0");
        var mi = String(date.getMinutes()).padStart(2, "0");
        return yyyy + "-" + mm + "-" + dd + " " + hh + ":" + mi;
    }

    // LLM 配置持久化：存储在服务端进程内存中，进程重启即清空
    var LLM_LEGACY_KEY = "vibe.llm.config.v1";
    var LLM_FIELDS = [
        "llm_base_url",
        "llm_api_key",
        "llm_model",
        "llm_question",
        "llm_context_format"
    ];

    try { localStorage.removeItem(LLM_LEGACY_KEY); } catch (e) { /* ignore */ }

    // 返回配置字典的 Promise，失败时返回空对象
    function loadLlmConfig() {
        return fetchJson("/api/llm/config")
            .then(function (response) {
                if (response && response.code === 0 && response.data) {
                    return response.data;
                }
                return {};
            })
            .catch(function () { return {}; });
    }

    // 即发即忘，失败不阻塞页面
    function saveLlmConfig(values) {
        var body = {};
        LLM_FIELDS.forEach(function (field) {
            body[field] = (values && typeof values[field] === "string") ? values[field] : "";
        });
        fetchJson("/api/llm/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        }).catch(function () { /* ignore */ });
    }

    function applyLlmConfigToForm(values) {
        values = values || {};
        LLM_FIELDS.forEach(function (field) {
            var node = document.getElementById(field);
            if (!node) return;
            if (typeof values[field] === "string") {
                node.value = values[field];
            }
        });
    }

    function collectLlmConfigFromForm() {
        var out = {};
        LLM_FIELDS.forEach(function (field) {
            var node = document.getElementById(field);
            out[field] = node ? node.value.trim() : "";
        });
        return out;
    }

    // 输入变化时自动持久化，切换页面也能保留配置
    function bindLlmConfigPersistence() {
        LLM_FIELDS.forEach(function (field) {
            var node = document.getElementById(field);
            if (!node) return;
            node.addEventListener("change", function () {
                saveLlmConfig(collectLlmConfigFromForm());
            });
        });
    }

    // 将 Markdown 文本渲染为安全 HTML
    function renderMarkdown(text) {
        var raw = String(text == null ? "" : text);
        if (typeof window.marked === "undefined") {
            return escapeHtml(raw).replace(/\n/g, "<br>");
        }
        try {
            return window.marked.parse(raw, { breaks: true, gfm: true });
        } catch (e) {
            return escapeHtml(raw).replace(/\n/g, "<br>");
        }
    }

    window.AppCommon = {
        fetchJson: fetchJson,
        platformLabel: platformLabel,
        formatSize: formatSize,
        escapeHtml: escapeHtml,
        formatTaskNo: formatTaskNo,
        formatDateTime: formatDateTime,
        loadLlmConfig: loadLlmConfig,
        saveLlmConfig: saveLlmConfig,
        applyLlmConfigToForm: applyLlmConfigToForm,
        collectLlmConfigFromForm: collectLlmConfigFromForm,
        bindLlmConfigPersistence: bindLlmConfigPersistence,
        renderMarkdown: renderMarkdown
    };

    // LLM 侧边栏拖拽调整宽度，双击重置为默认值
    var SIDEBAR_WIDTH_KEY = "vibe.llm.sidebar.width";
    var MIN_W = 280;
    var MAX_W = 720;

    function clampSidebarWidth(width) {
        var dynamicMax = Math.min(window.innerWidth * 0.5, MAX_W);
        if (dynamicMax < MIN_W) dynamicMax = MIN_W;
        if (width < MIN_W) return MIN_W;
        if (width > dynamicMax) return dynamicMax;
        return width;
    }

    function applySidebarWidth(sidebar, width) {
        var w = clampSidebarWidth(width);
        sidebar.style.width = w + "px";
        sidebar.style.flexBasis = w + "px";
        sidebar.style.setProperty("--sidebar-w", w + "px");
    }

    function clearSidebarWidth(sidebar) {
        sidebar.style.removeProperty("width");
        sidebar.style.removeProperty("flex-basis");
        sidebar.style.removeProperty("--sidebar-w");
    }

    function initSidebarResizer() {
        var resizer = document.getElementById("llm-sidebar-resizer");
        var sidebar = document.getElementById("llm-sidebar");
        var shell = document.getElementById("llm-shell");
        if (!resizer || !sidebar || !shell) return;

        // 恢复之前保存的宽度
        try {
            var saved = parseFloat(localStorage.getItem(SIDEBAR_WIDTH_KEY));
            if (!isNaN(saved) && saved > 0) {
                applySidebarWidth(sidebar, saved);
            }
        } catch (e) { /* ignore */ }

        var startX = 0;
        var startW = 0;
        var dragging = false;

        function onPointerDown(event) {
            if (event.button !== undefined && event.button !== 0) return;
            dragging = true;
            startX = event.clientX;
            startW = sidebar.getBoundingClientRect().width;
            resizer.classList.add("dragging");
            shell.classList.add("resizing");
            try { resizer.setPointerCapture(event.pointerId); } catch (e) { /* ignore */ }
            event.preventDefault();
        }

        function onPointerMove(event) {
            if (!dragging) return;
            applySidebarWidth(sidebar, startW + (event.clientX - startX));
        }

        function endDrag(event) {
            if (!dragging) return;
            dragging = false;
            resizer.classList.remove("dragging");
            shell.classList.remove("resizing");
            if (event && event.pointerId !== undefined) {
                try { resizer.releasePointerCapture(event.pointerId); } catch (e) { /* ignore */ }
            }
            try {
                localStorage.setItem(
                    SIDEBAR_WIDTH_KEY,
                    String(sidebar.getBoundingClientRect().width)
                );
            } catch (e) { /* ignore */ }
        }

        function onDoubleClick() {
            clearSidebarWidth(sidebar);
            try { localStorage.removeItem(SIDEBAR_WIDTH_KEY); } catch (e) { /* ignore */ }
        }

        // 视口缩小时重新限制宽度
        function onResize() {
            var current = sidebar.getBoundingClientRect().width;
            var clamped = clampSidebarWidth(current);
            if (Math.abs(clamped - current) > 0.5) {
                applySidebarWidth(sidebar, clamped);
            }
        }

        resizer.addEventListener("pointerdown", onPointerDown);
        resizer.addEventListener("pointermove", onPointerMove);
        resizer.addEventListener("pointerup", endDrag);
        resizer.addEventListener("pointercancel", endDrag);
        resizer.addEventListener("dblclick", onDoubleClick);
        window.addEventListener("resize", onResize);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initSidebarResizer);
    } else {
        initSidebarResizer();
    }
})();
