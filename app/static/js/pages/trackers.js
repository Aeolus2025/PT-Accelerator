/**
 * Tracker 管理：列表渲染、增删、Cloudflare 白名单
 */
(function (global) {
    'use strict';

    // 重绘由 main.js 的 store 订阅统一负责
    function loadTrackers() {
        store.load().catch(function (error) {
            console.error('加载Trackers失败:', error);
            ui.showToast('加载Trackers失败: ' + error.message, 'danger', 10000);
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

    function deleteTracker(domain) {
        api.del('/api/trackers/' + encodeURIComponent(domain))
            .then(function () {
                ui.showToast('Tracker已删除', 'success');
                return store.load(true);
            })
            .then(function () {
                global.hostsPage.loadCurrentHosts();
            })
            .catch(function (error) {
                console.error('删除Tracker失败:', error);
                ui.showToast(error.message, 'danger', 10000);
            });
    }

    function saveTracker(btn) {
        var name = document.getElementById('tracker-name').value;
        var domain = document.getElementById('tracker-domain').value;
        var enable = document.getElementById('tracker-enable').checked;
        var forceEl = document.getElementById('tracker-force-cloudflare');
        var forceCloudflare = forceEl ? forceEl.checked : false;

        if (!name || !domain) {
            ui.showToast('请填写完整信息', 'warning', 8000);
            return;
        }

        var tracker = { name: name, domain: domain, enable: enable, ip: '' };
        var originalText = btn.textContent;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 处理中...';
        ui.showToast('正在添加Tracker，请稍候...', 'info', 8000);

        api.post('/api/trackers?force_cloudflare=' + forceCloudflare, tracker)
            .then(function (data) {
                var modal = bootstrap.Modal.getInstance(document.getElementById('addTrackerModal'));
                if (modal) modal.hide();
                document.getElementById('add-tracker-form').reset();
                loadTrackers();
                ui.showToast(data.message || 'Tracker已添加', 'success');
            })
            .catch(function (error) {
                console.error('添加Tracker失败:', error);
                ui.showToast(error.message, 'danger', 10000);
            })
            .finally(function () {
                btn.disabled = false;
                btn.innerHTML = originalText;
            });
    }

    // ===== Cloudflare 白名单 =====
    async function loadCloudflareDomains() {
        var container = document.getElementById('cloudflare-domains-list');
        if (!container) return;
        try {
            var data = await api.get('/api/cloudflare-domains');
            var list = (data && data.cloudflare_domains) || [];
            container.innerHTML = list.map(function (domain) {
                return '<li class="list-group-item d-flex justify-content-between align-items-center">'
                    + '<span>' + ui.escapeHtml(domain) + '</span>'
                    + '<button class="btn btn-sm btn-danger" data-action="remove-cloudflare-domain"'
                    + ' data-domain="' + ui.escapeHtml(domain) + '">移除</button>'
                    + '</li>';
            }).join('');
        } catch (error) {
            console.error('加载Cloudflare白名单失败:', error);
            ui.showToast('加载失败: ' + error.message, 'danger');
        }
    }

    async function addCloudflareDomain() {
        var input = document.getElementById('cloudflare-domain-input');
        if (!input) return;
        // 去掉协议前缀和路径，与 tracker 域名口径一致
        var domain = input.value.trim().replace(/^https?:\/\//i, '').split('/')[0];
        if (!domain) return;
        try {
            await api.post('/api/cloudflare-domains?domain=' + encodeURIComponent(domain));
            input.value = '';
            loadCloudflareDomains();
            ui.showToast('已添加到Cloudflare白名单', 'success');
        } catch (error) {
            console.error('添加Cloudflare白名单失败:', error);
            ui.showToast('添加失败: ' + error.message, 'danger');
        }
    }

    async function removeCloudflareDomain(domain) {
        try {
            await api.del('/api/cloudflare-domains?domain=' + encodeURIComponent(domain));
            loadCloudflareDomains();
            ui.showToast('已移除Cloudflare白名单', 'success');
        } catch (error) {
            console.error('移除Cloudflare白名单失败:', error);
            ui.showToast('移除失败: ' + error.message, 'danger');
        }
    }

    function init() {
        // 打开「添加」弹窗时清空上次输入：失败后取消再打开不该残留旧值
        var addModal = document.getElementById('addTrackerModal');
        if (addModal) {
            addModal.addEventListener('show.bs.modal', function () {
                var form = document.getElementById('add-tracker-form');
                if (form) form.reset();
            });
        }

        var tbody = document.getElementById('trackers-table');
        if (tbody) {
            ui.delegate(tbody, 'change', '[data-action="toggle-tracker"]', function () {
                var el = this;
                var domain = el.dataset.domain;
                var checked = el.checked;
                store.patchArray('trackers', 'domain', domain, { enable: checked })
                    .then(function () {
                        ui.showToast('Tracker已更新', 'success');
                        global.hostsPage.loadCurrentHosts();
                    })
                    .catch(function (error) {
                        el.checked = !checked;
                        console.error('更新Tracker失败:', error);
                        ui.showToast('更新Tracker失败: ' + error.message, 'danger', 10000);
                    });
            });

            ui.delegate(tbody, 'click', '[data-action="delete-tracker"]', function () {
                var domain = this.dataset.domain;
                if (confirm('确定要删除Tracker "' + domain + '" 吗？')) {
                    deleteTracker(domain);
                }
            });
        }

        ui.delegate(document, 'click', '#btn-save-tracker', function () {
            saveTracker(this);
        });

        // 白名单弹窗打开时拉取
        ui.delegate(document, 'click', '[data-action="open-cloudflare-domains"]', function () {
            loadCloudflareDomains();
        });
        ui.delegate(document, 'click', '[data-action="add-cloudflare-domain"]', function () {
            addCloudflareDomain();
        });
        ui.delegate(document.getElementById('cloudflare-domains-list'), 'click',
            '[data-action="remove-cloudflare-domain"]', function () {
                removeCloudflareDomain(this.dataset.domain);
            });
    }

    global.trackersPage = {
        init: init,
        loadTrackers: loadTrackers,
        renderTrackerTable: renderTrackerTable,
        deleteTracker: deleteTracker,
        loadCloudflareDomains: loadCloudflareDomains,
        addCloudflareDomain: addCloudflareDomain,
        removeCloudflareDomain: removeCloudflareDomain
    };
})(window);
