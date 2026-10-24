/**
 * 日志面板：级别筛选、增量轮询、滚动跟随。
 */
(function (global) {
    'use strict';

    var POLL_MS = 3000;
    var MAX_DOM_RECORDS = 2000;
    var NEAR_BOTTOM_PX = 40;
    var MAX_FAILURES = 3;
    var PAGE_LINES = 1000;

    var state = {
        offset: 0,
        records: [],
        levels: { DEBUG: false, INFO: true, WARNING: true, ERROR: true },
        streaming: false,
        // 是否在日志 tab 上，决定要不要真的跑定时器
        active: false,
        timer: null,
        // 在飞的请求，后来者排队等它结束而不是直接丢弃
        inflight: null,
        failures: 0,
        loaded: false
    };

    function el() {
        return document.getElementById('logs');
    }

    function selectedLevels() {
        return Object.keys(state.levels).filter(function (name) {
            return state.levels[name];
        });
    }

    function recordHtml(record) {
        var level = (record.level || 'INFO').toLowerCase();
        // <pre> 只接受 phrasing content，这里用 span + CSS display:block
        return '<span class="log-rec lv-' + ui.escapeHtml(level) + '">' +
            ui.escapeHtml(record.text) + '</span>';
    }

    function isNearBottom(node) {
        return node.scrollHeight - node.scrollTop - node.clientHeight <= NEAR_BOTTOM_PX;
    }

    function renderAll() {
        var node = el();
        if (!node) return;

        var visible = state.records.filter(function (record) {
            return state.levels[record.level] !== false;
        });
        // 只保留尾部，避免长会话把 DOM 撑大
        if (visible.length > MAX_DOM_RECORDS) {
            visible = visible.slice(-MAX_DOM_RECORDS);
        }

        node.innerHTML = visible.length
            ? visible.map(recordHtml).join('')
            : '<span class="log-empty">暂无日志</span>';
        node.scrollTop = node.scrollHeight;
        updateStatus();
    }

    function appendRecords(records) {
        var node = el();
        if (!node || !records.length) return;

        // 追加前判断，追加后 scrollHeight 已变大，判断会永远为 false
        var stick = isNearBottom(node);
        var visible = records.filter(function (record) {
            return state.levels[record.level] !== false;
        });
        if (visible.length) {
            // 视图里可能还留着"暂无日志"占位，追加前必须清掉
            if (!node.querySelector('.log-rec')) {
                node.innerHTML = '';
            }
            node.insertAdjacentHTML('beforeend', visible.map(recordHtml).join(''));
        }

        // DOM 超限时整体重绘一次，丢弃最早的部分
        var count = node.querySelectorAll('.log-rec').length;
        if (count > MAX_DOM_RECORDS) {
            renderAll();
            return;
        }
        if (stick) {
            node.scrollTop = node.scrollHeight;
        }
        updateStatus();
    }

    function updateStatus() {
        var node = document.getElementById('log-status');
        if (!node) return;
        var total = state.records.length;
        var shown = state.records.filter(function (record) {
            return state.levels[record.level] !== false;
        }).length;
        var parts = ['显示 ' + shown + ' / ' + total + ' 条'];
        if (state.streaming) parts.push('持续滚动中');
        node.textContent = parts.join(' · ');
    }

    function fetchLogs(reset) {
        // 丢弃会让调用方以为已刷新，这里排队等前一个结束再跑
        if (state.inflight) {
            return state.inflight.then(function () {
                return fetchLogs(reset);
            });
        }

        var query = ['lines=' + PAGE_LINES, 'offset=' + (reset ? 0 : state.offset)];
        var levels = selectedLevels();
        // 全选时不传，省掉一次服务端过滤
        if (levels.length && levels.length < 4) {
            query.push('level=' + encodeURIComponent(levels.join(',')));
        }

        var request = api.get('/api/logs?' + query.join('&'))
            .then(function (data) {
                state.failures = 0;
                var incoming = data.records || [];
                // truncated 表示手里的 offset 已作废，等同于重新拉一次
                if (reset || data.truncated) {
                    state.records = incoming;
                    state.offset = data.offset || 0;
                    state.loaded = true;
                    renderAll();
                    return;
                }
                if (incoming.length) {
                    state.records = state.records.concat(incoming);
                    appendRecords(incoming);
                }
                state.offset = data.offset || 0;
                state.loaded = true;
                // 没有新记录但视图还没渲染过（空文件首屏）也要画一次
                if (!incoming.length && !state.records.length) {
                    renderAll();
                }
            })
            .catch(function (error) {
                state.failures += 1;
                console.error('加载日志失败:', error);
                if (state.failures >= MAX_FAILURES) {
                    stopStream();
                    ui.showToast('日志刷新连续失败，已停止自动刷新', 'danger');
                }
            })
            .finally(function () {
                state.inflight = null;
            });

        state.inflight = request;
        return request;
    }

    function clearTimer() {
        if (state.timer) {
            clearInterval(state.timer);
            state.timer = null;
        }
    }

    // 定时器只负责轮询，开关状态由 streaming 表达，两者分开才不会互相打脸
    function syncTimer() {
        var shouldRun = state.streaming && state.active && !document.hidden;
        if (shouldRun && !state.timer) {
            state.timer = setInterval(function () {
                fetchLogs(false);
            }, POLL_MS);
        } else if (!shouldRun) {
            clearTimer();
        }
    }

    function startStream() {
        if (state.streaming) return;
        state.streaming = true;
        var box = document.getElementById('chk-log-stream');
        if (box) box.checked = true;
        fetchLogs(false);
        syncTimer();
        updateStatus();
    }

    function stopStream() {
        state.streaming = false;
        clearTimer();
        var box = document.getElementById('chk-log-stream');
        if (box) box.checked = false;
        updateStatus();
    }

    function refresh() {
        return fetchLogs(true);
    }

    function clearLogs(btn) {
        ui.showConfirmModal('确认操作', '确定要清空系统日志吗？此操作不可恢复。', function () {
            var resume = state.streaming;
            // 清空与轮询并发会读到空文件，先停
            stopStream();
            if (btn) btn.disabled = true;

            api.post('/api/logs/clear')
                .then(function (res) {
                    if (res && res.success) {
                        ui.showToast(res.message || '日志已清空', 'success');
                        state.records = [];
                        state.offset = 0;
                        return fetchLogs(true);
                    }
                    ui.showToast((res && res.message) || '清空日志失败', 'danger');
                })
                .catch(function (err) {
                    console.error('清空日志失败:', err);
                    ui.showToast('清空日志失败: ' + err.message, 'danger');
                })
                .finally(function () {
                    if (btn) btn.disabled = false;
                    if (resume) startStream();
                });
        });
    }

    function bindEvents() {
        ui.delegate(document, 'click', '#btn-refresh-logs', function () {
            refresh();
        });
        ui.delegate(document, 'click', '#btn-clear-logs', function () {
            clearLogs(this);
        });
        ui.delegate(document, 'change', '#chk-log-stream', function () {
            if (this.checked) {
                startStream();
            } else {
                stopStream();
            }
        });

        ['DEBUG', 'INFO', 'WARNING', 'ERROR'].forEach(function (name) {
            ui.delegate(document, 'change', '#lv-' + name, function () {
                state.levels[name] = this.checked;
                // 已有记录里可能缺该级别，重新拉一次才完整
                refresh();
            });
        });

        // 切走时只停定时器，勾选状态保留
        document.addEventListener('hidden.bs.tab', function (event) {
            if (event.target && event.target.id === 'logs-tab') {
                state.active = false;
                syncTimer();
            }
        });
        document.addEventListener('shown.bs.tab', function (event) {
            if (event.target && event.target.id === 'logs-tab') {
                state.active = true;
                refresh();
                syncTimer();
            }
        });
        document.addEventListener('visibilitychange', function () {
            syncTimer();
        });
    }

    function init() {
        bindEvents();
        refresh();
    }

    global.logsPage = {
        init: init,
        refresh: refresh,
        startStream: startStream,
        stopStream: stopStream
    };
})(window);
