/**
 * 日志面板：级别筛选、关键词搜索、增量轮询、滚动跟随。
 *
 * 面板直接渲染 /api/logs 返回的原文，与 logs/app.log 里的那一行完全一致，
 * 不再重排字段，避免两处看到的内容对不上。
 */
(function (global) {
    'use strict';

    var POLL_MS = 3000;
    var MAX_RECORDS = 5000;       // 内存里保留的记录上限
    var MAX_DOM_RECORDS = 2000;   // 视图里最多渲染的记录数
    var NEAR_BOTTOM_PX = 40;
    var MAX_FAILURES = 3;
    var PAGE_LINES = 1000;
    var SEARCH_DEBOUNCE_MS = 200;
    var LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR'];

    var state = {
        offset: 0,
        records: [],
        // 视图筛选：ALL 表示不过滤，其余按级别精确匹配
        filter: 'ALL',
        keyword: '',
        streaming: false,
        // 是否在日志 tab 上，决定要不要真的跑定时器
        active: false,
        timer: null,
        searchTimer: null,
        // 在飞的请求，后来者排队等它结束而不是直接丢弃
        inflight: null,
        failures: 0,
        loaded: false
    };

    function el() {
        return document.getElementById('logs');
    }

    function matches(record) {
        if (state.filter !== 'ALL' && record.level !== state.filter) {
            return false;
        }
        if (!state.keyword) {
            return true;
        }
        return String(record.text || '').toLowerCase().indexOf(state.keyword) >= 0;
    }

    function visible(records) {
        return records.filter(matches);
    }

    function recordHtml(record) {
        var level = String(record.level || 'INFO').toLowerCase();
        // 原文照搬：面板与日志文件显示同一行
        return '<span class="log-rec lv-' + level + '">' +
            ui.escapeHtml(record.text || '') + '</span>';
    }

    function isNearBottom(node) {
        return node.scrollHeight - node.scrollTop - node.clientHeight <= NEAR_BOTTOM_PX;
    }

    function emptyText() {
        return (state.keyword || state.filter !== 'ALL') ? '没有匹配的日志' : '暂无日志';
    }

    function renderAll() {
        var node = el();
        if (!node) return;

        var rows = visible(state.records);
        // 只保留尾部，避免长会话把 DOM 撑大
        if (rows.length > MAX_DOM_RECORDS) {
            rows = rows.slice(-MAX_DOM_RECORDS);
        }

        node.innerHTML = rows.length
            ? rows.map(recordHtml).join('')
            : '<span class="log-empty">' + emptyText() + '</span>';
        node.scrollTop = node.scrollHeight;
        updateStatus();
    }

    function appendRecords(records) {
        var node = el();
        if (!node || !records.length) return;

        // 追加前判断，追加后 scrollHeight 已变大，判断会永远为 false
        var stick = isNearBottom(node);
        var rows = visible(records);
        if (rows.length) {
            // 视图里可能还留着"暂无日志"占位，追加前必须清掉
            if (!node.querySelector('.log-rec')) {
                node.innerHTML = '';
            }
            node.insertAdjacentHTML('beforeend', rows.map(recordHtml).join(''));
        }

        // DOM 超限时整体重绘一次，丢弃最早的部分
        if (node.querySelectorAll('.log-rec').length > MAX_DOM_RECORDS) {
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
        var parts = ['显示 ' + visible(state.records).length + ' / ' + state.records.length + ' 条'];
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

        var query = 'lines=' + PAGE_LINES + '&offset=' + (reset ? 0 : state.offset);
        var request = api.get('/api/logs?' + query)
            .then(function (data) {
                state.failures = 0;
                var incoming = (data && data.records) || [];
                // truncated 表示手里的 offset 已作废，等同于重新拉一次
                if (reset || (data && data.truncated)) {
                    state.records = incoming;
                    state.offset = (data && data.offset) || 0;
                    state.loaded = true;
                    renderAll();
                    return;
                }
                if (incoming.length) {
                    state.records = state.records.concat(incoming);
                    if (state.records.length > MAX_RECORDS) {
                        state.records = state.records.slice(-MAX_RECORDS);
                    }
                    appendRecords(incoming);
                }
                state.offset = (data && data.offset) || 0;
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
        clearTimer();
        if (!shouldRun) return;
        state.timer = setInterval(function () {
            fetchLogs(false);
        }, POLL_MS);
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

    // ---- 记录级别（写入文件的级别，与视图筛选是两件事） ----

    function renderLevel(level, envLevel) {
        var select = document.getElementById('sel-log-level');
        if (!select) return;
        if (level) select.value = level;
        select.title = envLevel
            ? '环境变量 LOG_LEVEL=' + envLevel + ' 优先，重启后按它生效'
            : '日志记录级别：低于该级别的日志不会写入文件';
    }

    function loadLevel() {
        api.get('/api/logs/level')
            .then(function (data) {
                if (!data) return;
                renderLevel(data.level, data.env_level);
            })
            .catch(function (error) {
                console.error('读取日志级别失败:', error);
            });
    }

    function saveLevel(select) {
        var level = select.value;
        select.disabled = true;
        api.post('/api/logs/level', { level: level })
            .then(function (res) {
                if (!res || !res.success) {
                    ui.showToast((res && res.message) || '设置日志级别失败', 'danger');
                    loadLevel();
                    return;
                }
                renderLevel(res.level, res.env_level);
                if (res.env_level && res.env_level !== res.level) {
                    ui.showToast('已切换为 ' + res.level + '，但环境变量 LOG_LEVEL=' +
                        res.env_level + ' 优先，重启后会回到 ' + res.env_level, 'warning', 9000);
                } else {
                    ui.showToast('日志级别已设为 ' + res.level, 'success');
                }
                // 级别变了，随后产生的日志才会进文件，这里刷一次让变化可见
                refresh();
            })
            .catch(function (err) {
                ui.showToast('设置日志级别失败: ' + err.message, 'danger');
                loadLevel();
            })
            .finally(function () {
                select.disabled = false;
            });
    }

    // ---- 视图筛选与搜索 ----

    function setFilter(value) {
        if (state.filter === value) return;
        state.filter = value;
        renderAll();
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
        ui.delegate(document, 'change', '#sel-log-level', function () {
            saveLevel(this);
        });

        ['ALL'].concat(LEVELS).forEach(function (name) {
            ui.delegate(document, 'change', '#lf-' + name, function () {
                if (this.checked) setFilter(name);
            });
        });

        ui.delegate(document, 'input', '#log-search', function () {
            var value = this.value;
            clearTimeout(state.searchTimer);
            // 只过滤已有记录，不重新请求，输入过程中不会打断滚动
            state.searchTimer = setTimeout(function () {
                state.keyword = value.trim().toLowerCase();
                renderAll();
            }, SEARCH_DEBOUNCE_MS);
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
        loadLevel();
        refresh();
    }

    global.logsPage = {
        init: init,
        refresh: refresh,
        startStream: startStream,
        stopStream: stopStream
    };
})(window);
