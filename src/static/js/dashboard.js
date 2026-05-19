(function () {
    var root = document.getElementById("dashboard-root");
    if (!root) return;

    var taskId = root.getAttribute("data-task-id");
    var readyBlock = document.getElementById("dashboard-ready");
    var progressBar = document.getElementById("progress-bar");
    var progressLabel = document.getElementById("progress-label");
    var progressCount = document.getElementById("progress-count");
    var progressMessage = document.getElementById("progress-message");
    var charts = { pie: null, bar: null };
    var socket = null;

    var STATUS_LABELS = {
        crawling: "采集中",
        preprocessing: "清洗中",
        analyzing: "情感分析",
        wordcloud: "统计词频",
        llm: "生成解读",
        completed: "已完成",
        failed: "失败",
        keepalive: "心跳"
    };

    function setProgress(data) {
        var total = Math.max(1, data.total || 1);
        var current = data.current || 0;
        var width = Math.min(100, Math.round((current / total) * 100));
        var status = data.status || "pending";
        var label = STATUS_LABELS[status] || status || "准备中";
        progressCount.textContent = current + " / " + total;
        progressMessage.textContent = data.message || "";
        progressLabel.innerHTML = (status === "completed" || status === "failed" ? "" : '<span class="dot-pulse"></span> ') + label;
        progressBar.style.width = (status === "completed" || status === "failed" ? 100 : width) + "%";
        progressBar.className = "progress-bar";
        if (status === "completed") {
            progressBar.classList.add("bg-success");
        } else if (status === "failed") {
            progressBar.classList.add("bg-danger");
        } else {
            progressBar.classList.add("progress-bar-striped", "progress-bar-animated");
        }
    }

    function renderInsight(insight) {
        var card = document.getElementById("insight-card");
        if (!insight || !(insight.title || insight.answer || insight.question)) {
            card.classList.add("d-none");
            return;
        }
        card.classList.remove("d-none");
        document.getElementById("insight-question").textContent = insight.question || "";
        document.getElementById("insight-title").textContent = insight.title || "";
        document.getElementById("insight-answer").textContent = insight.answer || "";
        if (insight.context_text) {
            document.getElementById("insight-context-wrap").classList.remove("d-none");
            document.getElementById("insight-context-summary").textContent = "查看发送给模型的 " + String(insight.context_format || "xml").toUpperCase() + " 上下文";
            document.getElementById("insight-context").textContent = insight.context_text;
        } else {
            document.getElementById("insight-context-wrap").classList.add("d-none");
        }
    }

    function renderTaskMeta(task) {
        document.getElementById("task-no-label").textContent = "任务编号 " + AppCommon.formatTaskNo(task.task_no);
        var startWrap = document.getElementById("task-start-wrap");
        var startTime = AppCommon.formatDateTime(task.start_time);
        if (startTime) {
            document.getElementById("task-start-time").textContent = startTime;
            startWrap.classList.remove("d-none");
        } else {
            startWrap.classList.add("d-none");
        }
    }

    function renderHistory(items) {
        var card = document.getElementById("history-card");
        var list = document.getElementById("history-list");
        list.innerHTML = "";
        if (!(items || []).length) {
            card.classList.add("d-none");
            return;
        }
        card.classList.remove("d-none");
        items.forEach(function (item) {
            var row = document.createElement("a");
            row.href = item.url;
            row.className = "history-item" + (item.task_id === taskId ? " current" : "");
            row.innerHTML =
                '<div class="history-item-top">' +
                '  <span class="history-item-no">' + AppCommon.escapeHtml(item.display_no || AppCommon.formatTaskNo(item.task_no)) + '</span>' +
                '  <span class="history-item-status">' + AppCommon.escapeHtml(item.status || "") + '</span>' +
                '</div>' +
                '<div class="history-item-keyword">' + AppCommon.escapeHtml(item.keyword || "") + '</div>' +
                '<div class="history-item-meta">' +
                AppCommon.escapeHtml(AppCommon.platformLabel(item.platform || "")) +
                ' · ' + AppCommon.escapeHtml(AppCommon.formatDateTime(item.start_time || "")) +
                ' · ' + AppCommon.escapeHtml(String(item.total_count || 0)) + '条' +
                '</div>';
            list.appendChild(row);
        });
    }

    function renderCommentList(elementId, items, flavor) {
        var target = document.getElementById(elementId);
        target.innerHTML = "";
        (items || []).forEach(function (item) {
            var div = document.createElement("div");
            div.className = "comment-item " + flavor;
            div.innerHTML =
                '<div class="comment-score">情感得分: ' + AppCommon.escapeHtml(item.score) + "</div>" +
                "<div>" + AppCommon.escapeHtml(item.text) + "</div>";
            target.appendChild(div);
        });
    }

    function renderSourceItems(items) {
        var card = document.getElementById("source-card");
        var list = document.getElementById("source-list");
        var embedCol = document.getElementById("source-embed-col");
        var embedFrame = document.getElementById("source-embed-frame");
        list.innerHTML = "";
        embedCol.classList.add("d-none");
        embedFrame.src = "";

        if (!(items || []).length) {
            card.classList.add("d-none");
            return;
        }

        card.classList.remove("d-none");
        var embeddable = null;
        items.forEach(function (item) {
            var wrapper = document.createElement("div");
            wrapper.className = "source-item-card";
            wrapper.innerHTML =
                '<div class="d-flex justify-content-between align-items-start gap-3">' +
                '  <div>' +
                '    <div class="source-item-platform">' + AppCommon.escapeHtml(AppCommon.platformLabel(item.platform || "")) + '</div>' +
                '    <div class="source-item-title">' + AppCommon.escapeHtml(item.title || "原帖") + '</div>' +
                (item.subtitle ? ('<div class="source-item-subtitle">' + AppCommon.escapeHtml(item.subtitle) + '</div>') : '') +
                '  </div>' +
                '  <div class="d-flex flex-wrap gap-2 justify-content-end">' +
                (item.url ? ('<a class="btn btn-outline-primary btn-sm" href="' + AppCommon.escapeHtml(item.url) + '" target="_blank" rel="noopener">打开原页面</a>') : '') +
                (item.embed_url ? '<button class="btn btn-primary btn-sm source-embed-btn" type="button">内嵌查看</button>' : '') +
                '  </div>' +
                '</div>';

            if (!embeddable && item.embed_url) {
                embeddable = item.embed_url;
            }

            var embedBtn = wrapper.querySelector(".source-embed-btn");
            if (embedBtn && item.embed_url) {
                embedBtn.addEventListener("click", function () {
                    embedFrame.src = item.embed_url;
                    embedCol.classList.remove("d-none");
                });
            }
            list.appendChild(wrapper);
        });

        if (embeddable) {
            embedFrame.src = embeddable;
            embedCol.classList.remove("d-none");
        }
    }

    function renderExports(items) {
        var card = document.getElementById("exports-card");
        var target = document.getElementById("exports-list");
        target.innerHTML = "";
        if (!(items || []).length) {
            card.classList.add("d-none");
            return;
        }
        card.classList.remove("d-none");
        (items || []).forEach(function (item) {
            var a = document.createElement("a");
            a.className = "export-btn";
            a.href = item.url;
            a.target = "_blank";
            a.rel = "noopener";
            a.innerHTML =
                '<i class="bi bi-file-earmark-arrow-down"></i> ' +
                AppCommon.escapeHtml(({ raw: "原始评论", cleaned: "清洗后评论", analysed: "带情感分数", summary: "摘要" }[item.kind] || item.kind)) +
                ' <span class="text-muted small">(' + AppCommon.escapeHtml(AppCommon.formatSize(item.size || 0)) + ")</span>";
            target.appendChild(a);
        });
    }

    function renderCloud(kind, image, message) {
        var wrap = document.getElementById(kind + "-cloud-wrap");
        var img = document.getElementById(kind + "-cloud");
        var empty = document.getElementById(kind + "-cloud-empty");
        if (image) {
            img.src = "data:image/png;base64," + image;
            wrap.classList.remove("d-none");
            empty.classList.add("d-none");
        } else {
            wrap.classList.add("d-none");
            empty.textContent = message || "未生成";
            empty.classList.remove("d-none");
        }
    }

    function renderPie(data) {
        if (!charts.pie) {
            charts.pie = window.echarts.init(document.getElementById("chart-pie"));
            window.addEventListener("resize", function () {
                if (charts.pie) charts.pie.resize();
            });
        }
        charts.pie.setOption({
            tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
            legend: { bottom: 0, icon: "circle" },
            color: ["#2eb872", "#f0b400", "#e64545"],
            series: [{
                type: "pie",
                radius: ["45%", "70%"],
                itemStyle: { borderRadius: 8, borderColor: "#fff", borderWidth: 2 },
                label: { show: true, formatter: "{b}\n{d}%" },
                data: data
            }]
        });
    }

    function renderBar(data) {
        if (!charts.bar) {
            charts.bar = window.echarts.init(document.getElementById("chart-bar"));
            window.addEventListener("resize", function () {
                if (charts.bar) charts.bar.resize();
            });
        }
        var reversed = (data || []).slice().reverse();
        charts.bar.setOption({
            tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
            grid: { left: "18%", right: "8%", bottom: "5%", top: "5%" },
            xAxis: { type: "value", splitLine: { lineStyle: { color: "#eef0f5" } } },
            yAxis: {
                type: "category",
                data: reversed.map(function (item) { return item.name; }),
                axisLine: { show: false },
                axisTick: { show: false }
            },
            series: [{
                type: "bar",
                data: reversed.map(function (item) { return item.value; }),
                itemStyle: {
                    color: new window.echarts.graphic.LinearGradient(0, 0, 1, 0, [
                        { offset: 0, color: "#4f7ec7" },
                        { offset: 1, color: "#1a3d8f" }
                    ]),
                    borderRadius: [0, 6, 6, 0]
                }
            }]
        });
    }

    function loadXmlContext() {
        var pre = document.getElementById("xml-context-pre");
        var copyBtn = document.getElementById("xml-context-copy");
        if (!pre) return;
        AppCommon.fetchJson("/api/result/" + taskId + "/xml-context").then(function (response) {
            if (response.code === 0 && response.data && response.data.xml) {
                pre.textContent = response.data.xml;
            } else {
                pre.textContent = response.msg || "上下文不可用";
            }
        }).catch(function (err) {
            pre.textContent = "加载失败：" + err.message;
        });
        if (copyBtn && !copyBtn.dataset.bound) {
            copyBtn.dataset.bound = "1";
            copyBtn.addEventListener("click", function () {
                var text = pre.textContent || "";
                if (!text) return;
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(text).then(function () {
                        flashCopied(copyBtn);
                    });
                } else {
                    var range = document.createRange();
                    range.selectNodeContents(pre);
                    var sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    try { document.execCommand("copy"); flashCopied(copyBtn); } catch (e) { /* ignore */ }
                    sel.removeAllRanges();
                }
            });
        }
    }

    function flashCopied(btn) {
        var original = btn.innerHTML;
        btn.innerHTML = '<i class="bi bi-check2 me-1"></i>已复制';
        setTimeout(function () { btn.innerHTML = original; }, 1500);
    }

    function loadDashboard() {
        return Promise.all([
            AppCommon.fetchJson("/api/result/" + taskId + "/summary"),
            AppCommon.fetchJson("/api/result/" + taskId + "/sentiment-pie"),
            AppCommon.fetchJson("/api/result/" + taskId + "/top-words"),
            AppCommon.fetchJson("/api/result/" + taskId + "/exports"),
            AppCommon.fetchJson("/api/result/" + taskId + "/wordcloud/positive").catch(function () { return { code: 1 }; }),
            AppCommon.fetchJson("/api/result/" + taskId + "/wordcloud/negative").catch(function () { return { code: 1 }; })
        ]).then(function (responses) {
            var summary = responses[0];
            var pie = responses[1];
            var bar = responses[2];
            var exportsData = responses[3];
            var positiveCloud = responses[4];
            var negativeCloud = responses[5];

            if (summary.code === 0) {
                readyBlock.classList.remove("d-none");
                document.getElementById("stat-total").textContent = summary.data.total;
                document.getElementById("stat-elapsed").textContent = summary.data.elapsed + "s";
                document.getElementById("stat-keyword").textContent = summary.data.keyword || "-";
                document.getElementById("stat-platform").textContent = AppCommon.platformLabel(summary.data.platform);
                renderSourceItems(summary.data.source_items || []);
                renderInsight(summary.data.llm_insight);
                renderCommentList("top-positive-list", summary.data.top_positive, "positive");
                renderCommentList("top-negative-list", summary.data.top_negative, "negative");
                loadXmlContext();
            }
            if (pie.code === 0) renderPie(pie.data);
            if (bar.code === 0) renderBar(bar.data);
            if (exportsData.code === 0) renderExports(exportsData.data);
            renderCloud(
                "positive",
                positiveCloud.code === 0 && positiveCloud.data ? positiveCloud.data.image : "",
                positiveCloud.msg
            );
            renderCloud(
                "negative",
                negativeCloud.code === 0 && negativeCloud.data ? negativeCloud.data.image : "",
                negativeCloud.msg
            );
        });
    }

    function setFatal(message) {
        setProgress({
            status: "failed",
            current: 1,
            total: 1,
            message: message
        });
    }

    function connectWebSocket() {
        var scheme = location.protocol === "https:" ? "wss" : "ws";
        socket = new WebSocket(scheme + "://" + location.host + "/ws/task/" + taskId);
        socket.onmessage = function (event) {
            var data = JSON.parse(event.data);
            if (data.status === "keepalive") return;
            setProgress(data);
            if (data.status === "completed") {
                loadDashboard();
            } else if (data.status === "failed") {
                setFatal(data.message || data.error || "任务失败");
            }
        };
        socket.onerror = function () {
            progressMessage.textContent = "WebSocket 连接异常，正在等待任务状态...";
        };
    }

    window.addEventListener("beforeunload", function () {
        if (socket) socket.close();
    });

    AppCommon.fetchJson("/api/task/" + taskId + "/status").then(function (status) {
        AppCommon.fetchJson("/api/tasks/history").then(function (history) {
            if (history.code === 0) {
                renderHistory(history.data || []);
            }
        }).catch(function () {});
        if (status.code === 0 && status.data) {
            renderTaskMeta(status.data);
            if (status.data.status === "completed") {
                setProgress({
                    status: "completed",
                    current: status.data.total_count,
                    total: Math.max(1, status.data.total_count),
                    message: "任务已完成"
                });
                return loadDashboard();
            }
            if (status.data.status === "failed") {
                setFatal(status.data.error || "任务失败");
                return null;
            }
        }
        connectWebSocket();
        return null;
    }).catch(function (error) {
        setFatal("初始化失败: " + error.message);
    });
})();
