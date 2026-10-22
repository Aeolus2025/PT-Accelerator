/**
 * Hosts 源管理与 Hosts 文件查看：列表渲染、日志查看、Hosts 直接编辑
 */
(function (global) {
    'use strict';

    // 重绘由 main.js 的 store 订阅统一负责
    function loadHostsSources() {
        store.load().catch(function (error) {
            console.error('加载Hosts源失败:', error);
            ui.showToast('加载Hosts源失败: ' + error.message, 'danger', 10000);
        });
    }

    function renderHostsSourceTable(sources) {
        ui.renderTable(document.getElementById('hosts-sources-table'), sources, [
            { key: 'name' },
            { key: 'url' },
            { render: function (s) {
                return '<div class="form-check form-switch">'
                    + '<input class="form-check-input" type="checkbox" data-action="toggle-hosts-source"'
                    + ' data-url="' + ui.escapeHtml(s.url) + '"'
                    + (s.enable ? ' checked' : '') + '>'
                    + '</div>';
            } },
            { render: function (s) {
                return '<button class="btn btn-sm btn-danger" data-action="delete-hosts-source"'
                    + ' data-url="' + ui.escapeHtml(s.url) + '">'
                    + '<i class="bi bi-trash"></i> 删除</button>';
            } }
        ], '暂无Hosts源');
    }

    function deleteHostsSource(url) {
        ui.showToast('正在删除Hosts源，请稍候...', 'info', 8000);
        api.del('/api/hosts-sources?url=' + encodeURIComponent(url))
            .then(function () {
                ui.showToast('Hosts源已删除', 'success');
                loadHostsSources();
                loadCurrentHosts();
            })
            .catch(function (error) {
                console.error('删除Hosts源失败:', error);
                ui.showToast(error.message, 'danger', 10000);
            });
    }

    function saveHostsSource() {
        var name = document.getElementById('hosts-source-name').value;
        var url = document.getElementById('hosts-source-url').value;
        var enable = document.getElementById('hosts-source-enable').checked;
        if (!name || !url) {
            ui.showToast('请填写完整信息', 'warning', 8000);
            return;
        }
        api.post('/api/hosts-sources', { name: name, url: url, enable: enable })
            .then(function () {
                var modal = bootstrap.Modal.getInstance(document.getElementById('addHostsSourceModal'));
                if (modal) modal.hide();
                document.getElementById('add-hosts-source-form').reset();
                loadHostsSources();
                loadCurrentHosts();
                ui.showToast('Hosts源已添加', 'success');
            })
            .catch(function (error) {
                console.error('添加Hosts源失败:', error);
                ui.showToast(error.message, 'danger', 10000);
            });
    }

    function loadLogs() {
        api.get('/api/logs')
            .then(function (data) {
                var logsElement = document.getElementById('logs');
                if (!logsElement) return;
                // 后端可能返回带换行的字符串或数组
                if (typeof data.logs === 'string' && data.logs.length > 0) {
                    logsElement.textContent = data.logs;
                    logsElement.scrollTop = logsElement.scrollHeight;
                } else if (Array.isArray(data.logs) && data.logs.length > 0) {
                    logsElement.textContent = data.logs.join('');
                    logsElement.scrollTop = logsElement.scrollHeight;
                } else {
                    logsElement.textContent = '暂无日志';
                }
            })
            .catch(function (error) {
                console.error('加载日志失败:', error);
                var logsElement = document.getElementById('logs');
                if (logsElement) logsElement.textContent = '加载日志失败';
            });
    }

    function clearLogs(btn) {
        ui.showConfirmModal('确认操作', '确定要清空系统日志吗？此操作不可恢复。', function () {
            btn.disabled = true;
            api.post('/api/logs/clear')
                .then(function (res) {
                    if (res && res.success) {
                        ui.showToast(res.message || '日志已清空', 'success');
                        var logsElement = document.getElementById('logs');
                        if (logsElement) logsElement.textContent = '';
                        loadLogs();
                    } else {
                        ui.showToast((res && res.message) || '清空日志失败', 'danger');
                    }
                })
                .catch(function (err) {
                    console.error('清空日志失败:', err);
                    ui.showToast('清空日志失败: ' + err.message, 'danger');
                })
                .finally(function () {
                    btn.disabled = false;
                });
        });
    }

    function loadCurrentHosts() {
        api.get('/api/current-hosts')
            .then(function (data) {
                var hostsElement = document.getElementById('current-hosts');
                if (!hostsElement) return;
                if (data.hosts && data.hosts.length > 0) {
                    hostsElement.textContent = data.hosts.join('');
                } else {
                    hostsElement.textContent = '获取hosts文件失败';
                }
            })
            .catch(function (error) {
                console.error('获取hosts文件失败:', error);
                var hostsElement = document.getElementById('current-hosts');
                if (hostsElement) hostsElement.textContent = '获取hosts文件失败';
            });
    }

    function openHostsEditor() {
        ui.showConfirmModal('确认操作', '此操作将修改系统Hosts文件，如果你不知道接下来该干什么请取消！', function () {
            api.get('/api/current-hosts')
                .then(function (data) {
                    var content = Array.isArray(data.hosts) ? data.hosts.join('') : (data.hosts || '');
                    var textarea = document.getElementById('edit-hosts-textarea');
                    if (textarea) textarea.value = content;
                    var modal = new bootstrap.Modal(document.getElementById('editHostsModal'));
                    modal.show();
                })
                .catch(function (err) {
                    ui.showToast('加载当前hosts失败: ' + err.message, 'danger');
                });
        });
    }

    function saveHostsContent(btn) {
        var textarea = document.getElementById('edit-hosts-textarea');
        var content = textarea.value;
        btn.disabled = true;
        api.post('/api/save-hosts-content', { content: content })
            .then(function (res) {
                if (res && res.success) {
                    ui.showToast(res.message || 'Hosts已保存', 'success');
                    loadCurrentHosts();
                    var modal = bootstrap.Modal.getInstance(document.getElementById('editHostsModal'));
                    if (modal) modal.hide();
                } else {
                    ui.showToast((res && res.message) || '保存失败', 'danger');
                }
            })
            .catch(function (err) {
                ui.showToast('保存失败: ' + err.message, 'danger');
            })
            .finally(function () {
                btn.disabled = false;
            });
    }

    function init() {
        var tbody = document.getElementById('hosts-sources-table');
        if (tbody) {
            ui.delegate(tbody, 'change', '[data-action="toggle-hosts-source"]', function () {
                var el = this;
                var url = el.dataset.url;
                var checked = el.checked;
                store.patchArray('hosts_sources', 'url', url, { enable: checked })
                    .then(function () {
                        ui.showToast('Hosts源已更新', 'success');
                        loadCurrentHosts();
                    })
                    .catch(function (error) {
                        el.checked = !checked;
                        console.error('更新Hosts源失败:', error);
                        ui.showToast('更新Hosts源失败: ' + error.message, 'danger', 10000);
                    });
            });

            ui.delegate(tbody, 'click', '[data-action="delete-hosts-source"]', function () {
                var url = this.dataset.url;
                if (confirm('确定要删除Hosts源 "' + url + '" 吗？')) {
                    deleteHostsSource(url);
                }
            });
        }

        ui.delegate(document, 'click', '#btn-save-hosts-source', function () {
            saveHostsSource();
        });
        ui.delegate(document, 'click', '#btn-refresh-logs', function () {
            loadLogs();
        });
        ui.delegate(document, 'click', '#btn-clear-logs', function () {
            clearLogs(this);
        });
        ui.delegate(document, 'click', '#btn-edit-hosts', function () {
            openHostsEditor();
        });
        ui.delegate(document, 'click', '#btn-save-hosts', function () {
            saveHostsContent(this);
        });

        loadHostsSources();
        loadLogs();
        loadCurrentHosts();
    }

    global.hostsPage = {
        init: init,
        loadHostsSources: loadHostsSources,
        renderHostsSourceTable: renderHostsSourceTable,
        deleteHostsSource: deleteHostsSource,
        loadLogs: loadLogs,
        loadCurrentHosts: loadCurrentHosts
    };
})(window);
