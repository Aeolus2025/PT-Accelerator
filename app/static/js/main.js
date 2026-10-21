document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM fully loaded and parsed');
    // 加载初始数据
    loadDashboard();
    loadCloudflareConfig();
    loadTrackers();       // 这里会 store.load()，下面的 hosts 源复用同一份
    loadHostsSources();
    loadLogs();
    loadCurrentHosts();
    loadCustomAcceleratedSites();
    // 绑定事件
    bindEvents();
    bindTrackerEvents();
    bindHostsSourceEvents();
    enhanceInputValidation();
    // 页面模块初始化（通知 / 认证）
    initNotifySettings();
    authPage.initAuthSettings();
});

function bindEvents() {
    // 下载器管理在 pages/clients.js 的 DOMContentLoaded 中初始化，避免重复
    // 运行CloudflareSpeedTest按钮事件
    const btnRunCloudflare = document.getElementById('btn-run-cloudflare');
    if (btnRunCloudflare) {
        btnRunCloudflare.addEventListener('click', function() {
            this.disabled = true;
            const spinner = document.createElement('div');
            spinner.className = 'spinner-container';
            spinner.innerHTML = '<div class="spinner-border spinner-border-sm text-light" role="status"><span class="visually-hidden">Loading...</span></div>';
            this.appendChild(spinner);
            fetch('/api/run-cfst-script', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    showActionResult(data.message, 'success');
                    loadCurrentHosts();
                    setTimeout(() => {
                        fetch('/api/task-status')
                            .then(res => res.json())
                            .then(res => {
                                if (res.status === 'done') {
                                    loadCurrentHosts();
                                    showToast('Hosts已自动更新', 'success');
                                }
                            });
                    }, 3000);
                })
                .catch(error => {
                    console.error('运行IP优选与Hosts更新任务失败:', error);
                    showActionResult('运行IP优选与Hosts更新任务失败', 'danger');
                })
                .finally(() => {
                    this.disabled = false;
                    this.removeChild(spinner);
                });
        });
    }
    // 更新Hosts
    const btnUpdateHosts = document.getElementById('btn-update-hosts');
    if (btnUpdateHosts) {
        btnUpdateHosts.addEventListener('click', function() {
            const resultElement = document.getElementById('action-result');
            resultElement.innerHTML = '<div class="alert alert-info">正在更新Hosts...</div>';
            fetch('/api/update-hosts', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    resultElement.innerHTML = `<div class="alert alert-success">${data.message}</div>`;
                    loadCurrentHosts();
                    setTimeout(() => { resultElement.innerHTML = ''; }, 5000);
                })
                .catch(error => {
                    console.error('更新Hosts失败:', error);
                    resultElement.innerHTML = '<div class="alert alert-danger">更新Hosts失败</div>';
                });
        });
    }
    // 保存Cloudflare配置
    const cloudflareForm = document.getElementById('cloudflare-form');
    if (cloudflareForm) {
        cloudflareForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const saveBtn = document.getElementById('save-cloudflare-btn');
            const spinner = document.getElementById('cloudflare-spinner');
            const resultSpan = document.getElementById('cloudflare-save-result');
            if (saveBtn) saveBtn.disabled = true;
            if (spinner) spinner.classList.remove('d-none');
            if (resultSpan) resultSpan.textContent = '';
            const config = {
                cloudflare: {
                    enable: document.getElementById('cloudflare-enable').checked,
                    cron: document.getElementById('cloudflare-cron').value
                }
            };
            fetch('/api/config')
                .then(response => response.json())
                .then(fullConfig => {
                    const updatedConfig = { ...fullConfig, cloudflare: config.cloudflare };
                    return fetch('/api/config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(updatedConfig)
                    });
                })
                .then(response => response.json())
                .then(() => {
                    showToast('定时任务配置已保存', 'success');
                    if (resultSpan) {
                        resultSpan.textContent = '保存成功';
                        resultSpan.className = 'ms-2 text-success';
                        setTimeout(() => { resultSpan.textContent = ''; }, 3000);
                    }
                    loadDashboard();
                })
                .catch(error => {
                    console.error('保存配置失败:', error);
                    showToast('保存定时任务配置失败: ' + error.message, 'danger');
                    if (resultSpan) {
                        resultSpan.textContent = '保存失败';
                        resultSpan.className = 'ms-2 text-danger';
                    }
                })
                .finally(() => {
                    if (saveBtn) saveBtn.disabled = false;
                    if (spinner) spinner.classList.add('d-none');
                });
        });
    }
    // 添加Tracker
    const saveTrackerBtn = document.getElementById('save-tracker');
    if (saveTrackerBtn) {
        saveTrackerBtn.addEventListener('click', function() {
            const name = document.getElementById('tracker-name').value;
            const domain = document.getElementById('tracker-domain').value;
            const enable = document.getElementById('tracker-enable').checked;
            const forceCloudflare = document.getElementById('tracker-force-cloudflare') ? document.getElementById('tracker-force-cloudflare').checked : false;
            if (!name || !domain) {
                showToast('请填写完整信息', 'warning', 8000);
                return;
            }
            const tracker = { name, domain, enable, ip: '' };
            this.disabled = true;
            const originalText = this.textContent;
            this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 处理中...';
            showToast('正在添加Tracker，请稍候...', 'info', 8000);
            fetch(`/api/trackers?force_cloudflare=${forceCloudflare}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(tracker)
            })
                .then(response => response.json())
                .then(data => {
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addTrackerModal'));
                    if (modal) modal.hide();
                    document.getElementById('add-tracker-form').reset();
                    loadTrackers();
                    showToast(data.message || 'Tracker已添加', 'success');
                })
                .catch(error => {
                    console.error('添加Tracker失败:', error);
                    showToast(error.message, 'danger', 10000);
                })
                .finally(() => {
                    this.disabled = false;
                    this.innerHTML = originalText;
                });
        });
    }
    // 添加Hosts源
    const saveHostsSourceBtn = document.getElementById('save-hosts-source');
    if (saveHostsSourceBtn) {
        saveHostsSourceBtn.addEventListener('click', function() {
            const name = document.getElementById('hosts-source-name').value;
            const url = document.getElementById('hosts-source-url').value;
            const enable = document.getElementById('hosts-source-enable').checked;
            if (!name || !url) {
                showToast('请填写完整信息', 'warning', 8000);
                return;
            }
            const source = { name, url, enable };
            fetch('/api/hosts-sources', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(source)
            })
                .then(response => response.json())
                .then(data => {
                    const modal = bootstrap.Modal.getInstance(document.getElementById('addHostsSourceModal'));
                    if (modal) modal.hide();
                    document.getElementById('add-hosts-source-form').reset();
                    loadHostsSources();
                    loadCurrentHosts();
                    showToast('Hosts源已添加', 'success');
                })
                .catch(error => {
                    console.error('添加Hosts源失败:', error);
                    showToast(error.message, 'danger', 10000);
                });
        });
    }
    // 刷新日志
    const refreshLogsBtn = document.getElementById('refresh-logs');
    if (refreshLogsBtn) {
        refreshLogsBtn.addEventListener('click', function() { loadLogs(); });
    }
    // 清空日志
    const clearLogsBtn = document.getElementById('clear-logs');
    if (clearLogsBtn) {
        clearLogsBtn.addEventListener('click', function() {
            showConfirmModal('确认操作', '确定要清空系统日志吗？此操作不可恢复。', function onConfirm() {
                clearLogsBtn.disabled = true;
                fetch('/api/logs/clear', { method: 'POST' })
                    .then(res => res.json())
                    .then(res => {
                        if (res && res.success) {
                            showToast(res.message || '日志已清空', 'success');
                            const logsElement = document.getElementById('logs');
                            logsElement.textContent = '';
                            // 成功清空后自动刷新一次最新日志
                            loadLogs();
                        } else {
                            showToast((res && res.message) || '清空日志失败', 'danger');
                        }
                    })
                    .catch(err => {
                        console.error('清空日志失败:', err);
                        showToast('清空日志失败: ' + err.message, 'danger');
                    })
                    .finally(() => {
                        clearLogsBtn.disabled = false;
                    });
            });
        });
    }
    // 批量添加Tracker
    const saveBatchTrackersBtn = document.getElementById('save-batch-trackers');
    if (saveBatchTrackersBtn) {
        saveBatchTrackersBtn.addEventListener('click', function() {
            const domainsText = document.getElementById('tracker-domains').value;
            if (!domainsText.trim()) {
                showToast('请输入至少一个域名', 'warning', 8000);
                return;
            }
            const domains = domainsText.split('\n').map(d => d.trim()).filter(d => d);
            if (domains.length === 0) {
                showToast('请输入至少一个有效域名', 'warning', 8000);
                return;
            }
            batchAddTrackers(domains);
        });
    }
    // 运行优选脚本按钮
    const btnRunCfstScript = document.getElementById('btn-run-cfst-script');
    if (btnRunCfstScript) {
        btnRunCfstScript.addEventListener('click', function() { runCfstScript(); });
    }
    // 批量更新IP按钮
    const btnUpdateAllTrackers = document.getElementById('btn-update-all-trackers');
    if (btnUpdateAllTrackers) {
        btnUpdateAllTrackers.addEventListener('click', function() {
            const ip = document.getElementById('batch-update-ip').value.trim();
            if (!ip) {
                showToast('请输入有效的IP地址', 'warning', 8000);
                return;
            }
            const ipv4Regex = /^(\d{1,3}\.){3}\d{1,3}$/;
            if (!ipv4Regex.test(ip)) {
                showToast('请输入有效的IPv4地址，格式如：104.16.91.215', 'warning', 8000);
                return;
            }
            updateAllTrackersIp(ip);
        });
    }
    // 清空hosts并更新按钮
    const btnClearAndUpdateHosts = document.getElementById('btn-clear-and-update-hosts');
    if (btnClearAndUpdateHosts) {
        btnClearAndUpdateHosts.addEventListener('click', function() {
            showConfirmModal('确认操作', '确定要清理由本项目写入的 hosts 分区并重新生成吗？此操作不会清空您原有的 hosts 内容。建议先备份。', function onConfirm() {
                btnClearAndUpdateHosts.disabled = true;
                showToast('正在执行清理并更新hosts，请稍候...', 'info', 10000);
                fetch('/api/clear-and-update-hosts', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        showToast(data.message || '已清理项目分区并更新hosts', 'success', 10000);
                        loadCurrentHosts();
                    })
                    .catch(error => {
                        showToast('清理并更新hosts失败: ' + error.message, 'danger', 10000);
                    })
                    .finally(() => {
                        btnClearAndUpdateHosts.disabled = false;
                    });
            });
        });
    }
    // Hosts编辑按钮
    const btnEditHosts = document.getElementById('btn-edit-hosts');
    if (btnEditHosts) {
        btnEditHosts.addEventListener('click', function() {
            showConfirmModal('确认操作', '此操作将修改系统Hosts文件，如果你不知道接下来该干什么请取消！', function onConfirm() {
                // 打开编辑模态框并加载当前内容
                fetch('/api/current-hosts')
                    .then(res => res.json())
                    .then(data => {
                        const content = Array.isArray(data.hosts) ? data.hosts.join('') : (data.hosts || '');
                        const textarea = document.getElementById('edit-hosts-textarea');
                        textarea.value = content;
                        const modal = new bootstrap.Modal(document.getElementById('editHostsModal'));
                        modal.show();
                    })
                    .catch(err => {
                        showToast('加载当前hosts失败: ' + err.message, 'danger');
                    });
            });
        });
    }
    // 保存Hosts
    const saveHostsBtn = document.getElementById('save-hosts-btn');
    if (saveHostsBtn) {
        saveHostsBtn.addEventListener('click', function() {
            const textarea = document.getElementById('edit-hosts-textarea');
            const content = textarea.value;
            saveHostsBtn.disabled = true;
            fetch('/api/save-hosts-content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content })
            })
            .then(res => res.json())
            .then(res => {
                if (res && res.success) {
                    showToast(res.message || 'Hosts已保存', 'success');
                    loadCurrentHosts();
                    const modalEl = document.getElementById('editHostsModal');
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                } else {
                    showToast((res && res.message) || '保存失败', 'danger');
                }
            })
            .catch(err => {
                showToast('保存失败: ' + err.message, 'danger');
            })
            .finally(() => {
                saveHostsBtn.disabled = false;
            });
        });
    }
    // 清空所有tracker按钮
    const btnClearAllTrackers = document.getElementById('btn-clear-all-trackers');
    if (btnClearAllTrackers) {
        btnClearAllTrackers.addEventListener('click', function() {
            showConfirmModal('确认操作', '确定要清空所有tracker吗？此操作不可恢复，建议先备份。', function onConfirm() {
                btnClearAllTrackers.disabled = true;
                showToast('正在清空所有tracker，请稍候...', 'info', 10000);
                fetch('/api/clear-all-trackers', { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        showToast(data.message || '已清空所有tracker', 'success', 10000);
                        loadTrackers();
                        loadCurrentHosts();
                    })
                    .catch(error => {
                        showToast('清空所有tracker失败: ' + error.message, 'danger', 10000);
                    })
                    .finally(() => {
                        btnClearAllTrackers.disabled = false;
                    });
            });
        });
    }
    // ----- 自定义站点加速功能相关事件绑定 -----
    const addCustomSiteBtn = document.getElementById('add-custom-site-btn');
    if (addCustomSiteBtn) {
        addCustomSiteBtn.addEventListener('click', addCustomAcceleratedSite);
    }

    const refreshCustomSitesBtn = document.getElementById('refresh-custom-sites-btn');
    if (refreshCustomSitesBtn) {
        refreshCustomSitesBtn.addEventListener('click', loadCustomAcceleratedSites);
    }

    // 监听自定义站点加速选项卡的显示事件
    const customSitesTab = document.getElementById('custom-sites-tab');
    if (customSitesTab) {
        customSitesTab.addEventListener('shown.bs.tab', function (event) {
            loadCustomAcceleratedSites();
        });
    }
    // ----- 自定义站点加速功能相关事件绑定 END -----
}

// 加载控制面板数据
function loadDashboard() {
    console.log('Loading dashboard data'); // 添加日志
    // 获取调度器状态
    fetch('/api/scheduler-status')
        .then(response => response.json())
        .then(data => {
            const statusElement = document.getElementById('scheduler-status');
            const statusBadgeElement = document.getElementById('scheduler-status-badge');
            const jobsElement = document.getElementById('scheduler-jobs');
            
            if (data.running) {
                statusElement.innerHTML = '<span class="text-success">运行中</span>';
                if (statusBadgeElement) {
                    statusBadgeElement.textContent = '运行中';
                    statusBadgeElement.className = 'status-badge badge-running';
                }
            } else {
                statusElement.innerHTML = '<span class="text-danger">已停止</span>';
                if (statusBadgeElement) {
                    statusBadgeElement.textContent = '已停止';
                    statusBadgeElement.className = 'status-badge badge-stopped';
                }
            }
            
            // 清空任务列表
            jobsElement.innerHTML = '';
            
            // 添加任务
            if (data.jobs && data.jobs.length > 0) {
                data.jobs.forEach(job => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${job.name}</td>
                        <td>${job.next_run}</td>
                    `;
                    jobsElement.appendChild(row);
                });
            } else {
                jobsElement.innerHTML = '<tr><td colspan="2">暂无定时任务</td></tr>';
            }
        })
        .catch(error => {
            console.error('获取调度器状态失败:', error);
            document.getElementById('scheduler-status').innerHTML = 
                '<span class="text-danger">获取状态失败</span>';
            
            const statusBadgeElement = document.getElementById('scheduler-status-badge');
            if (statusBadgeElement) {
                statusBadgeElement.textContent = '获取失败';
                statusBadgeElement.className = 'status-badge badge-stopped';
            }
        });
}

// 加载Cloudflare配置
function loadCloudflareConfig() {
    // 初始值来自 #app-config 数据岛，不必再请求一次
    const cloudflareConfig = store.section('cloudflare', {});

    document.getElementById('cloudflare-enable').checked =
        cloudflareConfig.enable !== undefined ? cloudflareConfig.enable : true;
    document.getElementById('cloudflare-cron').value =
        cloudflareConfig.cron || '0 0 * * *';
}

// 加载Trackers
function loadTrackers() {
    store.load().then(function (config) {
        renderTrackerTable(config.trackers || []);
    }).catch(function (error) {
        console.error('加载Trackers失败:', error);
        showToast('加载Trackers失败: ' + error.message, 'danger', 10000);
    });
}

function renderTrackerTable(trackers) {
    ui.renderTable(document.getElementById('trackers-table'), trackers, [
        { key: 'name' },
        { key: 'domain' },
        { render: function (t) { return ui.escapeHtml(t.ip || '未设置'); } },
        { render: function (t) {
            return '<div class="form-check form-switch">'
                + '<input class="form-check-input" type="checkbox" data-action="toggle-tracker"'
                + ' data-domain="' + ui.escapeHtml(t.domain) + '"'
                + (t.enable === true ? ' checked' : '') + '>'
                + '</div>';
        } },
        { render: function (t) {
            return '<button class="btn btn-sm btn-danger" data-action="delete-tracker"'
                + ' data-domain="' + ui.escapeHtml(t.domain) + '">'
                + '<i class="bi bi-trash"></i> 删除</button>';
        } }
    ], '暂无Tracker');
}

function bindTrackerEvents() {
    var tbody = document.getElementById('trackers-table');
    if (!tbody) return;

    ui.delegate(tbody, 'change', '[data-action="toggle-tracker"]', function () {
        var el = this;
        var domain = el.dataset.domain;
        var checked = el.checked;

        store.patchArray('trackers', 'domain', domain, { enable: checked })
            .then(function () {
                showToast('Tracker已更新', 'success');
                loadCurrentHosts();
            })
            .catch(function (error) {
                el.checked = !checked;
                console.error('更新Tracker失败:', error);
                showToast('更新Tracker失败: ' + error.message, 'danger', 10000);
            });
    });

    ui.delegate(tbody, 'click', '[data-action="delete-tracker"]', function () {
        var domain = this.dataset.domain;
        if (confirm('确定要删除Tracker "' + domain + '" 吗？')) {
            deleteTracker(domain);
        }
    });

    // Cloudflare 白名单：打开弹窗时拉取，添加/移除在本页操作
    ui.delegate(document, 'click', '[data-action="open-cloudflare-domains"]', function () {
        loadCloudflareDomains();
    });

    ui.delegate(document, 'click', '[data-action="add-cloudflare-domain"]', function () {
        addCloudflareDomain();
    });

    var cfList = document.getElementById('cloudflare-domains-list');
    ui.delegate(cfList, 'click', '[data-action="remove-cloudflare-domain"]', function () {
        removeCloudflareDomain(this.dataset.domain);
    });
}

// 删除Tracker
function deleteTracker(domain) {
    api.del('/api/trackers/' + encodeURIComponent(domain))
        .then(function () {
            showToast('Tracker已删除', 'success');
            return store.load(true);
        })
        .then(function (config) {
            renderTrackerTable(config.trackers || []);
            loadCurrentHosts();
        })
        .catch(function (error) {
            console.error('删除Tracker失败:', error);
            showToast(error.message, 'danger', 10000);
        });
}

// 加载Hosts源
function loadHostsSources() {
    store.load().then(function (config) {
        renderHostsSourceTable(config.hosts_sources || []);
    }).catch(function (error) {
        console.error('加载Hosts源失败:', error);
        showToast('加载Hosts源失败: ' + error.message, 'danger', 10000);
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

function bindHostsSourceEvents() {
    var tbody = document.getElementById('hosts-sources-table');
    if (!tbody) return;

    ui.delegate(tbody, 'change', '[data-action="toggle-hosts-source"]', function () {
        var el = this;
        var url = el.dataset.url;
        var checked = el.checked;

        store.patchArray('hosts_sources', 'url', url, { enable: checked })
            .then(function () {
                showToast('Hosts源已更新', 'success');
                loadCurrentHosts();
            })
            .catch(function (error) {
                el.checked = !checked;
                console.error('更新Hosts源失败:', error);
                showToast('更新Hosts源失败: ' + error.message, 'danger', 10000);
            });
    });

    ui.delegate(tbody, 'click', '[data-action="delete-hosts-source"]', function () {
        var url = this.dataset.url;
        if (confirm('确定要删除Hosts源 "' + url + '" 吗？')) {
            deleteHostsSource(url);
        }
    });
}

// 加载日志
function loadLogs() {
    fetch('/api/logs')
        .then(response => response.json())
        .then(data => {
            const logsElement = document.getElementById('logs');
            // 适配后端返回的带换行字符串
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
        .catch(error => {
            console.error('加载日志失败:', error);
            document.getElementById('logs').textContent = '加载日志失败';
        });
}

// 加载当前Hosts文件
function loadCurrentHosts() {
    fetch('/api/current-hosts')
        .then(response => response.json())
        .then(data => {
            const hostsElement = document.getElementById('current-hosts');
            
            if (data.hosts && data.hosts.length > 0) {
                hostsElement.textContent = data.hosts.join('');
            } else {
                hostsElement.textContent = '获取hosts文件失败';
            }
        })
        .catch(error => {
            console.error('获取hosts文件失败:', error);
            document.getElementById('current-hosts').textContent = '获取hosts文件失败';
        });
}

// 删除Hosts源
function deleteHostsSource(url) {
    showToast('正在删除Hosts源，请稍候...', 'info', 8000);
    fetch(`/api/hosts-sources?url=${encodeURIComponent(url)}`, {
        method: 'DELETE'
    })
        .then(response => {
            if (response.ok) {
                return response.json();
            } else {
                return response.json().then(data => {
                    throw new Error(data.detail || '删除Hosts源失败');
                });
            }
        })
        .then(data => {
            showToast('Hosts源已删除', 'success');
            loadHostsSources();
            loadCurrentHosts();
        })
        .catch(error => {
            console.error('删除Hosts源失败:', error);
            showToast(error.message, 'danger', 10000);
        });
}

// showToast / showConfirmModal / showProgressModal 已迁至 core/ui.js
// （ui.js 末尾保留了同名全局别名，现有调用点无需改动）
// fetchWithTimeout工具函数，支持超时
function fetchWithTimeout(resource, options = {}, timeout = 180000) {
    return Promise.race([
        fetch(resource, options),
        new Promise((_, reject) => setTimeout(() => reject(new Error('导入任务已提交，处理时间较长请耐心等待，稍后可刷新页面查看结果')), timeout))
    ]);
}

// 批量添加Trackers
function batchAddTrackers(domains, forceCloudflare = false) {
    showToast('正在批量添加域名...', 'info', 8000);
    fetch('/api/batch-add-domains', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ domains })
    })
    .then(response => response.json())
    .then(async data => {
        // 新增：如forceCloudflare为true，批量写入白名单
        if (forceCloudflare && Array.isArray(domains)) {
            for (const d of domains) {
                await fetch(`/api/cloudflare-domains?domain=${encodeURIComponent(d)}`, { method: 'POST' });
            }
        }
        const status = data.status || (data.message.includes('成功') ? 'success' : 'warning');
        showToast(data.message || '批量添加域名操作已完成', status, 8000);
        if (data.filtered_domains && data.filtered_domains.length > 0) {
            showToast('以下域名未检测到Cloudflare特征，已被跳过：' + data.filtered_domains.join(', '), 'warning', 8000);
        }
        if (data.details) {
            console.log('批量添加域名详情:', data.details);
        }
        const modal = bootstrap.Modal.getInstance(document.getElementById('batchAddTrackerModal'));
        if (modal) {
            modal.hide();
        }
        document.getElementById('tracker-domains').value = '';
        loadTrackers();
        loadCurrentHosts();
    })
    .catch(error => {
        console.error('批量添加域名失败:', error);
        showToast('批量添加域名失败: ' + error.message, 'danger', 10000);
    });
}

// 运行CloudflareSpeedTest优选脚本
function runCfstScript() {
    showToast('正在启动IP优选与Hosts更新任务...', 'info', 8000);
    fetch('/api/run-cfst-script', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
    .then(response => response.json())
    .then(data => {
        showToast(data.message || 'IP优选任务已启动', 'success', 8000);
        // 延迟一段时间后，确保IP优选有足够时间完成
        setTimeout(() => {
            // 先调用更新hosts API
            fetch('/api/update-hosts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            })
            .then(res => res.json())
            .then(hostData => {
                showToast(hostData.message || 'Hosts文件已更新', 'success', 8000);
                // 然后刷新界面显示
                loadDashboard();
                loadTrackers(); // 强制刷新Tracker列表，确保IP显示最新
                loadCurrentHosts();
            })
            .catch(error => {
                console.error('更新Hosts失败:', error);
                showToast('更新Hosts失败: ' + error.message, 'danger', 10000);
            });
        }, 5000); // 增加等待时间到5秒，确保IP优选有足够时间完成
    })
    .catch(error => {
        console.error('启动IP优选任务失败:', error);
        showToast('启动IP优选任务失败: ' + error.message, 'danger', 10000);
    });
}

// 批量更新所有Tracker的IP
function updateAllTrackersIp(ip) {
    showToast('正在更新所有Tracker的IP...', 'info', 8000);
    
    fetch(`/api/update-all-trackers?ip=${encodeURIComponent(ip)}`, {
        method: 'POST'
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('更新所有Tracker的IP失败');
        }
        return response.json();
    })
    .then(data => {
        showToast(data.message || `已将所有Tracker的IP更新为 ${ip}`, 'success', 8000);
        
        // 重新加载Tracker列表
        loadTrackers();
        
        // 更新hosts文件显示
        loadCurrentHosts();
    })
    .catch(error => {
        console.error('更新所有Tracker的IP失败:', error);
        showToast('更新所有Tracker的IP失败: ' + error.message, 'danger', 10000);
    });
}

// 显示操作结果
function showActionResult(message, type = 'info') {
    const resultElement = document.getElementById('action-result');
    if (!resultElement) return;
    
    resultElement.innerHTML = `<div class="alert alert-${type} mt-3">${message}</div>`;
    
    // 5秒后自动清除
    setTimeout(() => {
        resultElement.innerHTML = '';
    }, 5000);
}

// ========== 前端输入校验增强 ========== //

function enhanceInputValidation() {
    // CRON表达式校验
    const cronInput = document.getElementById('cloudflare-cron');
    if (cronInput) {
        cronInput.addEventListener('input', function() {
            const value = cronInput.value.trim();
            const resultSpan = document.getElementById('cloudflare-save-result');
            if (!isValidCron(value)) {
                resultSpan.textContent = 'CRON格式无效，需5段数字/星号/逗号/横线';
                resultSpan.className = 'ms-2 text-danger';
            } else {
                resultSpan.textContent = '';
            }
        });
    }
    // hosts源URL校验和自动补全
    const hostsUrlInput = document.getElementById('hosts-source-url');
    if (hostsUrlInput) {
        hostsUrlInput.addEventListener('blur', function() {
            let value = hostsUrlInput.value.trim();
            if (value && !/^https?:\/\//i.test(value)) {
                value = 'https://' + value;
                hostsUrlInput.value = value;
            }
            if (!isValidUrl(value)) {
                hostsUrlInput.classList.add('is-invalid');
            } else {
                hostsUrlInput.classList.remove('is-invalid');
            }
        });
    }
    // 下载器主机和端口校验
    const qbHost = document.getElementById('qbittorrent-host');
    const qbPort = document.getElementById('qbittorrent-port');
    const trHost = document.getElementById('transmission-host');
    const trPort = document.getElementById('transmission-port');
    [qbHost, trHost].forEach(input => {
        if (input) {
            input.addEventListener('blur', function() {
                if (!isValidHost(input.value.trim())) {
                    input.classList.add('is-invalid');
                } else {
                    input.classList.remove('is-invalid');
                }
            });
        }
    });
    [qbPort, trPort].forEach(input => {
        if (input) {
            input.addEventListener('blur', function() {
                if (!isValidPort(input.value.trim())) {
                    input.classList.add('is-invalid');
                } else {
                    input.classList.remove('is-invalid');
                }
            });
        }
    });
}

function isValidCron(str) {
    // 简单校验：5段，允许数字、*、,、-、/，不做复杂语义校验
    return /^([\d\*\/,\-]+\s+){4}[\d\*\/,\-]+$/.test(str);
}
function isValidUrl(url) {
    try {
        new URL(url);
        return true;
    } catch {
        return false;
    }
}
function isValidHost(host) {
    // 简单校验IP或域名
    return /^(?:[a-zA-Z0-9\-\.]+|\d{1,3}(?:\.\d{1,3}){3})$/.test(host);
}
function isValidPort(port) {
    const n = Number(port);
    return Number.isInteger(n) && n >= 1 && n <= 65535;
}

// ===== Cloudflare白名单管理UI =====
async function loadCloudflareDomains() {
    const container = document.getElementById('cloudflare-domains-list');
    if (!container) return;

    try {
        const data = await api.get('/api/cloudflare-domains');
        const list = (data && data.cloudflare_domains) || [];

        container.innerHTML = list.map(function (domain) {
            return '<li class="list-group-item d-flex justify-content-between align-items-center">'
                + '<span>' + ui.escapeHtml(domain) + '</span>'
                + '<button class="btn btn-sm btn-danger" data-action="remove-cloudflare-domain"'
                + ' data-domain="' + ui.escapeHtml(domain) + '">移除</button>'
                + '</li>';
        }).join('');
    } catch (error) {
        console.error('加载Cloudflare白名单失败:', error);
        showToast('加载失败: ' + error.message, 'danger');
    }
}

async function addCloudflareDomain() {
    const input = document.getElementById('cloudflare-domain-input');
    if (!input) return;

    // 去掉协议前缀和路径，与 tracker 域名口径一致
    const domain = input.value.trim().replace(/^https?:\/\//i, '').split('/')[0];
    if (!domain) return;

    try {
        await api.post('/api/cloudflare-domains?domain=' + encodeURIComponent(domain));
        input.value = '';
        loadCloudflareDomains();
        showToast('已添加到Cloudflare白名单', 'success');
    } catch (error) {
        console.error('添加Cloudflare白名单失败:', error);
        showToast('添加失败: ' + error.message, 'danger');
    }
}

async function removeCloudflareDomain(domain) {
    try {
        await api.del('/api/cloudflare-domains?domain=' + encodeURIComponent(domain));
        loadCloudflareDomains();
        showToast('已移除Cloudflare白名单', 'success');
    } catch (error) {
        console.error('移除Cloudflare白名单失败:', error);
        showToast('移除失败: ' + error.message, 'danger');
    }
}

// ----- 自定义站点加速功能 ----- 
function loadCustomAcceleratedSites() {
    const listElement = document.getElementById('custom-sites-list');
    const loadingElement = document.getElementById('custom-sites-loading');

    if (!listElement || !loadingElement) return;

    loadingElement.style.display = 'block'; // 显示加载提示
    // 清空现有列表项（除了加载提示）
    while (listElement.firstChild && listElement.firstChild !== loadingElement) {
        listElement.removeChild(listElement.firstChild);
    }
    
    fetch('/api/custom-accelerated-sites')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(sites => {
            loadingElement.style.display = 'none'; // 隐藏加载提示
            listElement.innerHTML = ''; // 彻底清空，包括可能残留的loading
            if (sites.length === 0) {
                listElement.innerHTML = '<li class="list-group-item text-center text-muted p-3">暂无自定义加速站点。</li>';
                return;
            }
            sites.forEach(site => {
                const listItem = document.createElement('li');
                listItem.className = 'list-group-item d-flex justify-content-between align-items-center';
                listItem.textContent = site;

                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'btn btn-danger btn-sm';
                deleteBtn.innerHTML = '<i class="bi bi-trash"></i> 删除';
                deleteBtn.onclick = function() { deleteCustomAcceleratedSite(site); };

                listItem.appendChild(deleteBtn);
                listElement.appendChild(listItem);
            });
        })
        .catch(error => {
            loadingElement.style.display = 'none';
            listElement.innerHTML = '<li class="list-group-item text-center text-danger p-3">加载站点列表失败，请稍后重试。</li>';
            console.error('加载自定义加速站点列表失败:', error);
            showToast('加载自定义站点列表失败: ' + error.message, 'danger');
        });
}

function addCustomAcceleratedSite() {
    const domainInput = document.getElementById('custom-site-domain-input');
    const feedbackElement = document.getElementById('add-custom-site-feedback');
    const domain = domainInput.value.trim();

    if (!domain) {
        showToast('请输入要加速的站点域名', 'warning');
        domainInput.classList.add('is-invalid');
        if (feedbackElement) feedbackElement.innerHTML = '<div class="text-danger">域名不能为空。</div>';
        return;
    }
    // 简单的域名格式校验
    const domainRegex = /^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6}$/;
    if (!domainRegex.test(domain)) {
        showToast('域名格式无效，请输入正确的域名，例如：mysite.example.com', 'warning');
        domainInput.classList.add('is-invalid');
        if (feedbackElement) feedbackElement.innerHTML = '<div class="text-danger">域名格式无效。</div>';
        return;
    }
    domainInput.classList.remove('is-invalid');
    if (feedbackElement) feedbackElement.innerHTML = '';

    const formData = new FormData();
    formData.append('domain', domain);

    const addBtn = document.getElementById('add-custom-site-btn');
    const originalBtnText = addBtn.innerHTML;
    addBtn.disabled = true;
    addBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 添加中...';

    fetch('/api/custom-accelerated-sites', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (response.status === 409) { // Conflict - Domain already exists
            return response.json().then(err => { throw new Error(err.detail || '站点已存在'); });
        }
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.detail || `HTTP error! status: ${response.status}`); });
        }
        return response.json();
    })
    .then(data => {
        showSuccessModal('操作成功', data.message || `站点 ${domain} 已成功添加并触发hosts更新。`);
        //showToast(data.message || `站点 ${domain} 已成功添加并触发hosts更新。`, 'success');
        domainInput.value = ''; // 清空输入框
        loadCustomAcceleratedSites(); // 刷新列表
        loadCurrentHosts(); // 更新当前hosts显示
    })
    .catch(error => {
        console.error('添加自定义加速站点失败:', error);
        showErrorModal('添加失败', error.message || '添加站点时发生未知错误。');
        //showToast('添加站点失败: ' + error.message, 'danger');
        domainInput.classList.add('is-invalid');
        if (feedbackElement) feedbackElement.innerHTML = `<div class="text-danger">${error.message}</div>`;
    })
    .finally(() => {
        addBtn.disabled = false;
        addBtn.innerHTML = originalBtnText;
    });
}

function deleteCustomAcceleratedSite(domain) {
    if (!confirm(`确定要删除加速站点 ${domain} 吗？`)) {
        return;
    }
    showProgressModal(`正在删除站点 ${domain}...`);

    fetch(`/api/custom-accelerated-sites/${encodeURIComponent(domain)}`, {
        method: 'DELETE'
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.detail || `HTTP error! status: ${response.status}`); });
        }
        return response.json();
    })
    .then(data => {
        hideProgressModal();
        showSuccessModal('操作成功', data.message || `站点 ${domain} 已成功删除并触发hosts更新。`);
        //showToast(data.message || `站点 ${domain} 已成功删除并触发hosts更新。`, 'success');
        loadCustomAcceleratedSites(); // 刷新列表
        loadCurrentHosts(); // 更新当前hosts显示
    })
    .catch(error => {
        hideProgressModal();
        console.error(`删除自定义加速站点 ${domain} 失败:`, error);
        showErrorModal('删除失败', error.message || `删除站点 ${domain} 时发生未知错误。`);
        //showToast(`删除站点 ${domain} 失败: ` + error.message, 'danger');
    });
}
// ----- 自定义站点加速功能 END -----
