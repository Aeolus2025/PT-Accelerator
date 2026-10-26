/**
 * 控制面板：调度器状态、定时任务配置、批量操作入口
 */
(function (global) {
    'use strict';

    function loadDashboard() {
        api.get('/api/scheduler-status')
            .then(function (data) {
                var statusElement = document.getElementById('scheduler-status');
                var statusBadgeElement = document.getElementById('scheduler-status-badge');
                var jobsElement = document.getElementById('scheduler-jobs');

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

                jobsElement.innerHTML = '';

                if (data.jobs && data.jobs.length > 0) {
                    data.jobs.forEach(function (job) {
                        var row = document.createElement('tr');
                        row.innerHTML = '<td>' + ui.escapeHtml(job.name) + '</td>'
                            + '<td>' + ui.escapeHtml(job.next_run) + '</td>';
                        jobsElement.appendChild(row);
                    });
                } else {
                    jobsElement.innerHTML = '<tr><td colspan="2">暂无定时任务</td></tr>';
                }
            })
            .catch(function (error) {
                console.error('获取调度器状态失败:', error);
                var statusElement = document.getElementById('scheduler-status');
                if (statusElement) {
                    statusElement.innerHTML = '<span class="text-danger">获取状态失败</span>';
                }
                var statusBadgeElement = document.getElementById('scheduler-status-badge');
                if (statusBadgeElement) {
                    statusBadgeElement.textContent = '获取失败';
                    statusBadgeElement.className = 'status-badge badge-stopped';
                }
            });
    }

    // 初始值来自 #app-config 数据岛，不必再请求一次
    function loadCloudflareConfig() {
        var cloudflareConfig = store.section('cloudflare', {});
        var enableEl = document.getElementById('cloudflare-enable');
        var cronEl = document.getElementById('cloudflare-cron');
        if (enableEl) enableEl.checked = cloudflareConfig.enable !== undefined ? cloudflareConfig.enable : true;
        if (cronEl) cronEl.value = cloudflareConfig.cron || '0 0 * * *';
    }

    function runCloudflareSpeedTest(btn) {
        btn.disabled = true;
        var spinner = document.createElement('div');
        spinner.className = 'spinner-container';
        spinner.innerHTML = '<div class="spinner-border spinner-border-sm text-light" role="status">'
            + '<span class="visually-hidden">Loading...</span></div>';
        btn.appendChild(spinner);
        api.post('/api/run-cfst-script', undefined, { timeout: 0 })
            .then(function (data) {
                ui.showToast(data.message, 'success');
                global.hostsPage.loadCurrentHosts();
                setTimeout(function () {
                    api.get('/api/task-status')
                        .then(function (res) {
                            if (res.status === 'done') {
                                global.hostsPage.loadCurrentHosts();
                                ui.showToast('Hosts已自动更新', 'success');
                            }
                        });
                }, 3000);
            })
            .catch(function (error) {
                console.error('运行IP优选与Hosts更新任务失败:', error);
                ui.showToast('运行IP优选与Hosts更新任务失败', 'danger');
            })
            .finally(function () {
                btn.disabled = false;
                if (spinner.parentNode === btn) btn.removeChild(spinner);
            });
    }

    function updateHosts(btn) {
        var originalText = btn.textContent;
        var spinner = document.createElement('span');
        spinner.className = 'spinner-border spinner-border-sm me-1';
        btn.insertBefore(spinner, btn.firstChild);
        btn.disabled = true;

        api.post('/api/update-hosts', undefined, { timeout: 120000 })
            .then(function (data) {
                ui.showToast(data.message || 'Hosts已更新', 'success');
                global.hostsPage.loadCurrentHosts();
            })
            .catch(function (error) {
                console.error('更新Hosts失败:', error);
                ui.showToast('更新Hosts失败: ' + error.message, 'danger');
            })
            .finally(function () {
                btn.disabled = false;
                btn.textContent = originalText;
            });
    }

    function saveCloudflareConfig(e) {
        e.preventDefault();
        var saveBtn = document.getElementById('btn-save-cloudflare');
        var spinner = document.getElementById('cloudflare-spinner');
        var resultSpan = document.getElementById('cloudflare-save-result');
        if (saveBtn) saveBtn.disabled = true;
        if (spinner) spinner.classList.remove('d-none');
        if (resultSpan) resultSpan.textContent = '';

        var cloudflare = {
            enable: document.getElementById('cloudflare-enable').checked,
            cron: document.getElementById('cloudflare-cron').value
        };
        store.patch({ cloudflare: cloudflare })
            .then(function () {
                ui.showToast('定时任务配置已保存', 'success');
                if (resultSpan) {
                    resultSpan.textContent = '保存成功';
                    resultSpan.className = 'ms-2 text-success';
                    setTimeout(function () { resultSpan.textContent = ''; }, 3000);
                }
                loadDashboard();
            })
            .catch(function (error) {
                console.error('保存配置失败:', error);
                ui.showToast('保存定时任务配置失败: ' + error.message, 'danger');
                if (resultSpan) {
                    resultSpan.textContent = '保存失败';
                    resultSpan.className = 'ms-2 text-danger';
                }
            })
            .finally(function () {
                if (saveBtn) saveBtn.disabled = false;
                if (spinner) spinner.classList.add('d-none');
            });
    }

    function saveBatchTrackers() {
        var domainsText = document.getElementById('tracker-domains').value;
        if (!domainsText.trim()) {
            ui.showToast('请输入至少一个域名', 'warning', 8000);
            return;
        }
        var domains = domainsText.split('\n').map(function (d) { return d.trim(); }).filter(function (d) { return d; });
        if (domains.length === 0) {
            ui.showToast('请输入至少一个有效域名', 'warning', 8000);
            return;
        }
        batchAddTrackers(domains);
    }

    // 批量添加Trackers
    function batchAddTrackers(domains, forceCloudflare) {
        if (forceCloudflare === undefined) forceCloudflare = false;
        ui.showToast('正在批量添加域名...', 'info', 8000);
        api.post('/api/batch-add-domains', { domains: domains }, { timeout: 0 })
            .then(async function (data) {
                if (forceCloudflare && Array.isArray(domains)) {
                    for (var i = 0; i < domains.length; i++) {
                        await api.post('/api/cloudflare-domains?domain=' + encodeURIComponent(domains[i]));
                    }
                }
                var msg = (data && data.message) || '';
                var status = data.status || (msg.indexOf('成功') !== -1 ? 'success' : 'warning');
                ui.showToast(msg || '批量添加域名操作已完成', status, 8000);
                if (data.filtered_domains && data.filtered_domains.length > 0) {
                    ui.showToast('以下域名未检测到Cloudflare特征，已被跳过：' + data.filtered_domains.join(', '), 'warning', 8000);
                }
                if (data.details) {
                    console.log('批量添加域名详情:', data.details);
                }
                var modal = bootstrap.Modal.getInstance(document.getElementById('batchAddTrackerModal'));
                if (modal) modal.hide();
                document.getElementById('tracker-domains').value = '';
                global.trackersPage.loadTrackers();
                global.hostsPage.loadCurrentHosts();
            })
            .catch(function (error) {
                console.error('批量添加域名失败:', error);
                ui.showToast('批量添加域名失败: ' + error.message, 'danger', 10000);
            });
    }

    // 运行CloudflareSpeedTest优选脚本
    function runCfstScript() {
        ui.showToast('正在启动IP优选与Hosts更新任务...', 'info', 8000);
        api.post('/api/run-cfst-script', undefined, { timeout: 0 })
            .then(function (data) {
                ui.showToast(data.message || 'IP优选任务已启动', 'success', 8000);
                // 留出测速时间后再刷新 Hosts 与 Tracker
                setTimeout(function () {
                    api.post('/api/update-hosts', undefined, { timeout: 120000 })
                        .then(function (hostData) {
                            ui.showToast(hostData.message || 'Hosts文件已更新', 'success', 8000);
                            loadDashboard();
                            global.trackersPage.loadTrackers();
                            global.hostsPage.loadCurrentHosts();
                        })
                        .catch(function (error) {
                            console.error('更新Hosts失败:', error);
                            ui.showToast('更新Hosts失败: ' + error.message, 'danger', 10000);
                        });
                }, 5000);
            })
            .catch(function (error) {
                console.error('启动IP优选任务失败:', error);
                ui.showToast('启动IP优选任务失败: ' + error.message, 'danger', 10000);
            });
    }

    function updateAllTrackersIp(ip) {
        ui.showToast('正在更新所有Tracker的IP...', 'info', 8000);
        api.post('/api/update-all-trackers?ip=' + encodeURIComponent(ip), undefined, { timeout: 0 })
            .then(function (data) {
                ui.showToast(data.message || ('已将所有Tracker的IP更新为 ' + ip), 'success', 8000);
                global.trackersPage.loadTrackers();
                global.hostsPage.loadCurrentHosts();
            })
            .catch(function (error) {
                console.error('更新所有Tracker的IP失败:', error);
                ui.showToast('更新所有Tracker的IP失败: ' + error.message, 'danger', 10000);
            });
    }

    function updateAllTrackersFromInput() {
        var ip = document.getElementById('batch-update-ip').value.trim();
        if (!ip) {
            ui.showToast('请输入有效的IP地址', 'warning', 8000);
            return;
        }
        if (!/^(\d{1,3}\.){3}\d{1,3}$/.test(ip)) {
            ui.showToast('请输入有效的IPv4地址，格式如：104.16.91.215', 'warning', 8000);
            return;
        }
        updateAllTrackersIp(ip);
    }

    function clearGeneratedHosts(btn) {
        ui.showConfirmModal('确认操作', '确定要删除本项目生成的 hosts 记录吗？系统原有的 hosts 内容不会受影响。', function () {
            btn.disabled = true;
            ui.showToast('正在清空生成的 hosts 记录...', 'info', 5000);
            api.post('/api/clear-generated-hosts')
                .then(function (data) {
                    ui.showToast(data.message || '已清空生成的 hosts 记录', 'success', 8000);
                    global.hostsPage.loadCurrentHosts();
                })
                .catch(function (error) {
                    ui.showToast('清空生成的 hosts 失败: ' + error.message, 'danger', 8000);
                })
                .finally(function () {
                    btn.disabled = false;
                });
        });
    }

    function clearAllTrackers(btn) {
        ui.showConfirmModal('确认操作', '确定要清空所有tracker吗？此操作不可恢复，建议先备份。', function () {
            btn.disabled = true;
            ui.showToast('正在清空所有tracker，请稍候...', 'info', 10000);
            api.post('/api/clear-all-trackers', undefined, { timeout: 0 })
                .then(function (data) {
                    ui.showToast(data.message || '已清空所有tracker', 'success', 10000);
                    global.trackersPage.loadTrackers();
                    global.hostsPage.loadCurrentHosts();
                })
                .catch(function (error) {
                    ui.showToast('清空所有tracker失败: ' + error.message, 'danger', 10000);
                })
                .finally(function () {
                    btn.disabled = false;
                });
        });
    }

    function isValidCron(str) {
        return /^([\d\*\/,\-]+\s+){4}[\d\*\/,\-]+$/.test(str);
    }

    function isValidUrl(url) {
        try {
            new URL(url);
            return true;
        } catch (e) {
            return false;
        }
    }

    // CRON 实时校验、hosts 源 URL 自动补全
    function enhanceInputValidation() {
        var cronInput = document.getElementById('cloudflare-cron');
        if (cronInput) {
            cronInput.addEventListener('input', function () {
                var resultSpan = document.getElementById('cloudflare-save-result');
                if (!resultSpan) return;
                if (!isValidCron(cronInput.value.trim())) {
                    resultSpan.textContent = 'CRON格式无效，需5段数字/星号/逗号/横线';
                    resultSpan.className = 'ms-2 text-danger';
                } else {
                    resultSpan.textContent = '';
                }
            });
        }

        var hostsUrlInput = document.getElementById('hosts-source-url');
        if (hostsUrlInput) {
            hostsUrlInput.addEventListener('blur', function () {
                var value = hostsUrlInput.value.trim();
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
    }

    function init() {
        ui.delegate(document, 'click', '#btn-run-cloudflare', function () {
            runCloudflareSpeedTest(this);
        });
        ui.delegate(document, 'click', '#btn-update-hosts', function () {
            updateHosts(this);
        });
        ui.delegate(document, 'submit', '#cloudflare-form', function (e) {
            saveCloudflareConfig(e);
        });
        ui.delegate(document, 'click', '#btn-save-batch-trackers', function () {
            saveBatchTrackers();
        });
        ui.delegate(document, 'click', '#btn-run-cfst-script', function () {
            runCfstScript();
        });
        ui.delegate(document, 'click', '#btn-update-all-trackers', function () {
            updateAllTrackersFromInput();
        });
        ui.delegate(document, 'click', '#btn-clear-generated-hosts', function () {
            clearGeneratedHosts(this);
        });
        ui.delegate(document, 'click', '#btn-clear-all-trackers', function () {
            clearAllTrackers(this);
        });

        loadDashboard();
        loadCloudflareConfig();
        enhanceInputValidation();
    }

    global.dashboardPage = {
        init: init,
        loadDashboard: loadDashboard,
        loadCloudflareConfig: loadCloudflareConfig,
        batchAddTrackers: batchAddTrackers,
        runCfstScript: runCfstScript,
        updateAllTrackersIp: updateAllTrackersIp,
        isValidCron: isValidCron,
        isValidUrl: isValidUrl
    };
})(window);
