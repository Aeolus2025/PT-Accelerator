/**
 * 通知设置：渠道列表渲染、增删改、单渠道测试
 */
(function (global) {
    'use strict';

    var TYPE_NAMES = {
        wecom_bot: '企业微信Bot',
        wecom_app: '企业微信App',
        telegram: 'Telegram',
        smtp: '邮件',
        bark: 'Bark',
        serverj: 'Server酱',
        chat: 'Synology Chat',
        feishu: '飞书机器人',
        dingding: '钉钉机器人',
        igot: 'iGot 聚合推送',
        webhook: '自定义Webhook',
        mediasaber: 'MediaSaber'
    };

    var CHANNEL_TYPES = Object.keys(TYPE_NAMES);

    function getChannelTypeName(type) {
        return TYPE_NAMES[type] || type;
    }

    function el(id) {
        return document.getElementById(id);
    }

    // 读输入框的值，元素不存在时返回空串
    function val(id) {
        var node = el(id);
        return node ? node.value : '';
    }

    function checked(id) {
        var node = el(id);
        return !!(node && node.checked);
    }

    // ---------------------------------------------------------------- 渲染

    function renderNotifyChannels(channels) {
        var container = el('notifyChannelsList');
        if (!container) return;

        if (!channels || Object.keys(channels).length === 0) {
            container.innerHTML = '<div class="text-center text-muted py-4">'
                + '<i class="bi bi-bell-slash fs-1"></i>'
                + '<p class="mt-2">暂无通知渠道配置</p></div>';
            return;
        }

        container.innerHTML = Object.keys(channels).map(function (key) {
            return renderChannelCard(key, channels[key] || {});
        }).join('');
    }

    function renderChannelCard(key, config) {
        var typeName = getChannelTypeName(config.type || key);
        var enabled = !!config.enable;
        var escapedKey = ui.escapeHtml(key);

        var badges = ['<span class="badge bg-secondary ms-2 me-2">' + ui.escapeHtml(typeName) + '</span>'];

        var method = (config.WEBHOOK_METHOD || '').toUpperCase();
        if (method) badges.push('<span class="badge bg-warning text-white me-2">' + ui.escapeHtml(method) + '</span>');

        var url = config.WEBHOOK_URL || '';
        var urlLine = url
            ? '<div class="small mb-1 text-muted d-flex align-items-start">'
              + '<i class="bi bi-link-45deg me-1 flex-shrink-0 mt-1"></i>'
              + '<span class="text-break" style="word-break: break-all;">' + ui.escapeHtml(url) + '</span>'
              + '</div>'
            : '';

        var metaParts = [];
        if (config.WEBHOOK_CONTENT_TYPE) {
            metaParts.push(ui.escapeHtml(config.WEBHOOK_CONTENT_TYPE));
        }
        if (config.WEBHOOK_BODY && String(config.WEBHOOK_BODY).trim()) {
            metaParts.push('自定义Body');
        }
        var metaLine = metaParts.length
            ? '<div class="small text-muted">' + metaParts.join(' | ') + '</div>'
            : '';

        var switchHtml = '<div class="form-check form-switch ms-auto ms-md-1 d-none d-md-block">'
            + '<input class="form-check-input" type="checkbox" data-action="toggle-channel"'
            + ' data-key="' + escapedKey + '"' + (enabled ? ' checked' : '') + '>'
            + '</div>';

        var switchMobile = '<div class="form-check form-switch d-block d-md-none ms-3">'
            + '<input class="form-check-input" type="checkbox" data-action="toggle-channel"'
            + ' data-key="' + escapedKey + '"' + (enabled ? ' checked' : '') + '>'
            + '</div>';

        return '<div class="card mb-3">'
            + '<div class="card-body py-3">'
            + '<div class="d-flex flex-column flex-md-row align-items-start align-items-md-center justify-content-between">'
            + '<div class="flex-grow-1 pe-md-3 mb-2 mb-md-0">'
            + '<div class="d-flex flex-wrap align-items-center mb-1">'
            + '<span class="fw-semibold me-2">' + ui.escapeHtml(config.name || key) + '</span>'
            + badges.join('')
            + switchHtml
            + '</div>'
            + urlLine
            + metaLine
            + '</div>'
            + '<div class="d-flex flex-row align-items-center gap-1">'
            + '<button class="btn btn-sm btn-outline-secondary d-flex align-items-center text-nowrap"'
            + ' data-action="test-channel" data-key="' + escapedKey + '">'
            + '<i class="bi bi-send me-1"></i><span>测试</span></button>'
            + '<button class="btn btn-sm btn-outline-warning d-flex align-items-center text-nowrap"'
            + ' data-action="edit-channel" data-key="' + escapedKey + '">'
            + '<i class="bi bi-pencil-square me-1"></i><span>编辑</span></button>'
            + '<button class="btn btn-sm btn-outline-danger d-flex align-items-center text-nowrap"'
            + ' data-action="delete-channel" data-key="' + escapedKey + '">'
            + '<i class="bi bi-trash me-1"></i><span>删除</span></button>'
            + switchMobile
            + '</div>'
            + '</div></div></div>';
    }

    // ---------------------------------------------------------------- 加载

    async function loadNotifyConfig() {
        try {
            var notifyConfig = await notifyStore.load(true);

            var enabledEl = el('notifyEnabled');
            if (enabledEl) enabledEl.checked = !!notifyConfig.enable;

            renderNotifyChannels(notifyConfig.channels || {});
        } catch (error) {
            console.error('加载通知配置失败:', error);
            toast('加载通知配置失败: ' + error.message, 'danger');
        }
    }

    // ---------------------------------------------------------------- 事件

    function bindNotifyEvents() {
        // 防重复绑定
        if (bindNotifyEvents.__bound) return;
        bindNotifyEvents.__bound = true;

        var enabledEl = el('notifyEnabled');
        if (enabledEl) enabledEl.addEventListener('change', updateNotifyEnabled);

        var addBtn = el('add-notify-channel-btn');
        if (addBtn) addBtn.addEventListener('click', openAddNotifyChannelModal);

        var typeSelect = el('channel-type');
        if (typeSelect) typeSelect.addEventListener('change', showChannelConfig);

        var saveBtn = el('save-notify-channel');
        if (saveBtn) {
            saveBtn.addEventListener('click', function (e) {
                try { e.currentTarget && e.currentTarget.blur && e.currentTarget.blur(); } catch (_) {}
                saveNotifyChannel();
            });
        }

        var list = el('notifyChannelsList');
        if (!list) return;

        ui.delegate(list, 'change', '[data-action="toggle-channel"]', function () {
            var input = this;
            var key = input.dataset.key;
            var next = input.checked;
            setChannelEnabled(key, next).catch(function (error) {
                input.checked = !next;
                console.error('切换渠道状态失败:', error);
                toast('操作失败: ' + error.message, 'danger');
            });
        });

        ui.delegate(list, 'click', '[data-action="test-channel"]', function () {
            testSingleChannel(this.dataset.key);
        });
        ui.delegate(list, 'click', '[data-action="edit-channel"]', function () {
            editChannel(this.dataset.key);
        });
        ui.delegate(list, 'click', '[data-action="delete-channel"]', function () {
            var key = this.dataset.key;
            confirmModal('确认删除', '确定要删除这个通知渠道吗？', function () {
                performDeleteChannel(key);
            });
        });
    }

    // ---------------------------------------------------------------- 写入

    // 渠道级修改统一走这里：基于本地副本改一处，合并提交
    function patchChannels(mutator) {
        var channels = Object.assign({}, notifyStore.section('channels', {}));
        mutator(channels);
        return notifyStore.patch({ channels: channels });
    }

    async function updateNotifyEnabled() {
        var input = el('notifyEnabled');
        var enabled = input.checked;

        try {
            await notifyStore.patch({ enable: enabled });
            toast('通知功能已' + (enabled ? '启用' : '禁用'), 'success');
        } catch (error) {
            console.error('更新通知状态失败:', error);
            input.checked = !enabled;
            toast('更新失败: ' + error.message, 'danger');
        }
    }

    async function setChannelEnabled(channelKey, enabled) {
        await patchChannels(function (channels) {
            if (!channels[channelKey]) throw new Error('未找到该通知渠道');
            channels[channelKey] = Object.assign({}, channels[channelKey], { enable: enabled });
        });
        toast('渠道已' + (enabled ? '启用' : '禁用'), 'success');
    }

    async function performDeleteChannel(channelKey) {
        try {
            await patchChannels(function (channels) {
                if (!channels[channelKey]) throw new Error('未找到该通知渠道');
                delete channels[channelKey];
            });
            toast('渠道已删除', 'success');
            renderNotifyChannels(notifyStore.section('channels', {}));
        } catch (error) {
            console.error('删除渠道失败:', error);
            toast('删除失败: ' + error.message, 'danger');
        }
    }

    // ---------------------------------------------------------------- 表单

    function showChannelConfig() {
        var type = val('channel-type');
        document.querySelectorAll('.channel-config').forEach(function (node) {
            node.style.display = 'none';
        });

        if (!type) return;
        var configId = (type === 'wecom_bot') ? 'wecom-config' : (type + '-config');
        var target = el(configId);
        if (target) target.style.display = 'block';
    }

    // 从表单读出一个渠道的完整配置
    function collectChannelData() {
        var data = {
            name: val('channel-name'),
            type: val('channel-type'),
            enable: checked('channel-enable')
        };

        switch (data.type) {
            case 'igot':
                data.IGOT_PUSH_KEY = val('igot-key');
                break;
            case 'dingding':
                data.DD_BOT_TOKEN = val('dd-bot-token');
                data.DD_BOT_SECRET = val('dd-bot-secret');
                break;
            case 'feishu':
                data.FSKEY = val('feishu-key');
                break;
            case 'chat':
                data.CHAT_URL = val('chat-url');
                data.CHAT_TOKEN = val('chat-token');
                break;
            case 'serverj':
                data.PUSH_KEY = val('serverj-push-key');
                break;
            case 'wecom_app': {
                // QYWX_AM 格式：corpid,corpsecret,touser,agentid[,media_id]
                var parts = [
                    val('weapp-corpid').trim(),
                    val('weapp-corpsecret').trim(),
                    val('weapp-touser').trim(),
                    val('weapp-agentid').trim()
                ].filter(Boolean);
                var media = val('weapp-mediaid').trim();
                if (media) parts.push(media);
                data.QYWX_AM = parts.join(',');
                data.QYWX_ORIGIN = val('weapp-origin').trim();
                break;
            }
            case 'wecom_bot':
                data.QYWX_KEY = val('wecom-key');
                break;
            case 'telegram':
                data.TG_BOT_TOKEN = val('tg-bot-token');
                data.TG_USER_ID = val('tg-user-id');
                data.TG_API_HOST = val('tg-api-host');
                data.TG_PROXY_HOST = val('tg-proxy-host');
                data.TG_PROXY_PORT = val('tg-proxy-port');
                data.TG_PROXY_AUTH = val('tg-proxy-auth');
                break;
            case 'smtp': {
                data.SMTP_SERVER = val('smtp-server');
                data.SMTP_EMAIL = val('smtp-email');
                data.SMTP_PASSWORD = val('smtp-password');
                data.SMTP_NAME = val('smtp-name');
                data.SMTP_SSL = checked('smtp-ssl') ? 'true' : 'false';
                // 端口单独填写且 server 未带端口时拼成 host:port
                var port = val('smtp-port').trim();
                if (port && data.SMTP_SERVER && data.SMTP_SERVER.indexOf(':') === -1) {
                    data.SMTP_SERVER = data.SMTP_SERVER + ':' + port;
                }
                break;
            }
            case 'bark':
                data.BARK_PUSH = val('bark-url');
                data.BARK_GROUP = val('bark-group');
                data.BARK_SOUND = val('bark-sound');
                data.BARK_ICON = val('bark-icon');
                data.BARK_LEVEL = val('bark-level');
                data.BARK_URL = val('bark-jump-url');
                data.BARK_ARCHIVE = checked('bark-archive') ? '1' : '';
                break;
            case 'webhook':
                data.WEBHOOK_URL = val('webhook-url');
                data.WEBHOOK_METHOD = val('webhook-method');
                data.WEBHOOK_CONTENT_TYPE = val('webhook-content-type');
                data.WEBHOOK_HEADERS = val('webhook-headers');
                data.WEBHOOK_BODY = val('webhook-body');
                break;
            case 'mediasaber':
                data.MEDIASABER_HOST = val('mediasaber-host');
                data.MEDIASABER_APIKEY = val('mediasaber-apikey');
                break;
        }

        return data;
    }

    // 把一个渠道的配置回填到表单
    function fillChannelForm(ch) {
        var nameInput = el('channel-name');
        var typeSelect = el('channel-type');
        var enableSwitch = el('channel-enable');
        if (nameInput) nameInput.value = ch.name || '';
        if (typeSelect) typeSelect.value = ch.type || 'webhook';
        if (enableSwitch) enableSwitch.checked = !!ch.enable;

        var type = ch.type || 'webhook';

        if (type === 'wecom_app') {
            var arr = String(ch.QYWX_AM || '').split(',');
            [['weapp-corpid', 0], ['weapp-corpsecret', 1], ['weapp-touser', 2],
             ['weapp-agentid', 3], ['weapp-mediaid', 4]].forEach(function (pair) {
                var node = el(pair[0]);
                if (node) node.value = arr[pair[1]] || '';
            });
            var origin = el('weapp-origin');
            if (origin) origin.value = ch.QYWX_ORIGIN || 'https://qyapi.weixin.qq.com';
        } else if (type === 'smtp') {
            var server = ch.SMTP_SERVER || '';
            if (el('smtp-server')) el('smtp-server').value = server;
            var idx = server.lastIndexOf(':');
            if (el('smtp-port')) el('smtp-port').value = idx > -1 ? server.slice(idx + 1) : '';
            if (el('smtp-email')) el('smtp-email').value = ch.SMTP_EMAIL || '';
            if (el('smtp-password')) el('smtp-password').value = ch.SMTP_PASSWORD || '';
            if (el('smtp-name')) el('smtp-name').value = ch.SMTP_NAME || '';
            if (el('smtp-ssl')) el('smtp-ssl').checked = String(ch.SMTP_SSL || 'false') === 'true';
        } else if (type === 'bark') {
            var barkMap = [
                ['bark-url', 'BARK_PUSH'], ['bark-group', 'BARK_GROUP'], ['bark-sound', 'BARK_SOUND'],
                ['bark-icon', 'BARK_ICON'], ['bark-level', 'BARK_LEVEL'], ['bark-jump-url', 'BARK_URL']
            ];
            barkMap.forEach(function (pair) {
                var node = el(pair[0]);
                if (node) node.value = ch[pair[1]] || '';
            });
            if (el('bark-archive')) el('bark-archive').checked = !!(ch.BARK_ARCHIVE && ch.BARK_ARCHIVE !== '');
        } else {
            var FIELD_MAP = {
                igot: [['igot-key', 'IGOT_PUSH_KEY']],
                dingding: [['dd-bot-token', 'DD_BOT_TOKEN'], ['dd-bot-secret', 'DD_BOT_SECRET']],
                feishu: [['feishu-key', 'FSKEY']],
                chat: [['chat-url', 'CHAT_URL'], ['chat-token', 'CHAT_TOKEN']],
                serverj: [['serverj-push-key', 'PUSH_KEY']],
                wecom_bot: [['wecom-key', 'QYWX_KEY']],
                telegram: [['tg-bot-token', 'TG_BOT_TOKEN'], ['tg-user-id', 'TG_USER_ID'],
                           ['tg-api-host', 'TG_API_HOST'], ['tg-proxy-host', 'TG_PROXY_HOST'],
                           ['tg-proxy-port', 'TG_PROXY_PORT'], ['tg-proxy-auth', 'TG_PROXY_AUTH']],
                mediasaber: [['mediasaber-host', 'MEDIASABER_HOST'], ['mediasaber-apikey', 'MEDIASABER_APIKEY']],
                webhook: [['webhook-url', 'WEBHOOK_URL'], ['webhook-headers', 'WEBHOOK_HEADERS'],
                          ['webhook-body', 'WEBHOOK_BODY'],
                          ['webhook-method', 'WEBHOOK_METHOD'],
                          ['webhook-content-type', 'WEBHOOK_CONTENT_TYPE']]
            };
            var defaults = { 'webhook-method': 'POST', 'webhook-content-type': 'application/json' };

            (FIELD_MAP[type] || []).forEach(function (pair) {
                var node = el(pair[0]);
                if (node) node.value = ch[pair[1]] || defaults[pair[0]] || '';
            });
            Object.keys(defaults).forEach(function (id) {
                var node = el(id);
                if (node && !node.value) node.value = defaults[id];
            });
        }
    }

    async function saveNotifyChannel() {
        var form = el('notify-channel-form');
        var channelData = collectChannelData();

        if (!channelData.name) {
            toast('请填写渠道名称', 'danger');
            return;
        }

        try {
            var editingKey = form && form.dataset.editingKey ? form.dataset.editingKey : null;

            await patchChannels(function (channels) {
                if (editingKey && editingKey !== channelData.name) delete channels[editingKey];
                channels[channelData.name] = channelData;
            });

            toast('通知渠道已保存', 'success');

            var modalEl = el('notifyChannelModal');
            if (modalEl && document.activeElement && modalEl.contains(document.activeElement)) {
                try { document.activeElement.blur(); } catch (_) {}
            }
            var inst = bootstrap.Modal.getInstance(modalEl);
            if (inst) inst.hide();

            if (form) {
                form.reset();
                delete form.dataset.editingKey;
            }

            renderNotifyChannels(notifyStore.section('channels', {}));
        } catch (error) {
            console.error('保存通知渠道失败:', error);
            toast('保存失败: ' + error.message, 'danger');
        }
    }

    function editChannel(channelKey) {
        var channels = notifyStore.section('channels', {});
        var ch = channels[channelKey];
        if (!ch) {
            toast('未找到该通知渠道', 'danger');
            return;
        }

        var form = el('notify-channel-form');
        if (!form) return;

        form.dataset.editingKey = channelKey;
        fillChannelForm(ch);
        showChannelConfig();

        var titleEl = el('notifyChannelModalLabel');
        var saveBtn = el('save-notify-channel');
        if (titleEl) titleEl.textContent = '编辑通知渠道';
        if (saveBtn) saveBtn.textContent = '更新';

        bootstrap.Modal.getOrCreateInstance(el('notifyChannelModal')).show();
    }

    function openAddNotifyChannelModal() {
        var form = el('notify-channel-form');
        if (form) {
            form.reset();
            delete form.dataset.editingKey;
        }

        var titleEl = el('notifyChannelModalLabel');
        var saveBtn = el('save-notify-channel');
        if (titleEl) titleEl.textContent = '添加通知渠道';
        if (saveBtn) saveBtn.textContent = '保存';

        var typeSelect = el('channel-type');
        if (typeSelect) {
            typeSelect.value = '';
            document.querySelectorAll('.channel-config').forEach(function (node) {
                node.style.display = 'none';
            });
        }
    }

    // ---------------------------------------------------------------- 测试

    async function testSingleChannel(channelKey) {
        try {
            var ch = notifyStore.section('channels', {})[channelKey];
            if (!ch) {
                toast('渠道不存在', 'warning');
                return;
            }
            if (!ch.enable) {
                toast('该渠道未启用', 'warning');
                return;
            }

            var payload = {
                title: 'PT-Accelerator通知测试',
                content: '这是一条测试消息，用于验证通知功能是否正常工作。',
                channels: {}
            };
            payload.channels[channelKey] = ch;

            var data = await api.post('/api/notify/test', payload);
            if (data && data.success) {
                toast('测试通知已发送', 'success');
            } else {
                throw new Error((data && data.message) || '发送失败');
            }
        } catch (error) {
            console.error('测试通知失败:', error);
            toast('测试失败: ' + error.message, 'danger');
        }
    }

    // ---------------------------------------------------------------- 初始化

    function initNotifySettings() {
        // 模板回填依赖通知配置加载完成，放在其后执行
        loadNotifyConfig().then(loadNotifyTemplate).catch(function () {
            loadNotifyTemplate();
        });
        bindNotifyEvents();
        bindNotifyTemplate();
    }

    function loadNotifyTemplate() {
        var tpl = notifyStore.section('template', {}) || {};
        var titleEl = el('notify-template-title');
        var contentEl = el('notify-template-content');
        if (titleEl) titleEl.value = tpl.title || '';
        if (contentEl) contentEl.value = tpl.content || '';
    }

    function readNotifyTemplate() {
        var titleEl = el('notify-template-title');
        var contentEl = el('notify-template-content');
        return {
            title: (titleEl && titleEl.value) || '',
            content: (contentEl && contentEl.value) || ''
        };
    }

    function showTemplateError(msg) {
        var box = el('notify-template-error');
        if (!box) return;
        if (!msg) {
            box.classList.add('d-none');
            box.textContent = '';
            return;
        }
        box.textContent = msg;
        box.classList.remove('d-none');
    }

    function bindNotifyTemplate() {
        ui.delegate(document, 'click', '#btn-preview-template', function () {
            var payload = readNotifyTemplate();
            api.post('/api/notify/template/preview', payload)
                .then(function (res) {
                    if (!res || !res.success) throw new Error((res && res.message) || '预览失败');
                    var errs = res.errors || {};
                    var msgs = [];
                    if (errs.title) msgs.push('标题: ' + errs.title);
                    if (errs.content) msgs.push('内容: ' + errs.content);
                    showTemplateError(msgs.join('；'));
                    el('preview-title').textContent = res.title;
                    el('preview-content').textContent = res.content;
                    el('notify-template-preview').classList.remove('d-none');
                })
                .catch(function (e) { toast('预览失败: ' + e.message, 'danger'); });
        });

        ui.delegate(document, 'click', '#btn-save-template', function () {
            notifyStore.patch({ template: readNotifyTemplate() })
                .then(function () {
                    showTemplateError('');
                    toast('模板已保存', 'success');
                })
                .catch(function (e) { toast('保存失败: ' + e.message, 'danger'); });
        });

        ui.delegate(document, 'click', '#btn-reset-template', function () {
            var titleEl = el('notify-template-title');
            var contentEl = el('notify-template-content');
            if (titleEl) titleEl.value = '';
            if (contentEl) contentEl.value = '';
            showTemplateError('');
            toast('已清空，保存后恢复默认格式', 'info');
        });
    }

    global.notifyPage = {
        getChannelTypeName: getChannelTypeName,
        CHANNEL_TYPES: CHANNEL_TYPES,
        renderNotifyChannels: renderNotifyChannels,
        loadNotifyConfig: loadNotifyConfig,
        initNotifySettings: initNotifySettings,
        bindNotifyEvents: bindNotifyEvents,
        showChannelConfig: showChannelConfig,
        openAddNotifyChannelModal: openAddNotifyChannelModal,
        saveNotifyChannel: saveNotifyChannel,
        editChannel: editChannel,
        deleteChannel: function (key) {
            confirmModal('确认删除', '确定要删除这个通知渠道吗？', function () {
                performDeleteChannel(key);
            });
        },
        testSingleChannel: testSingleChannel,
        updateNotifyEnabled: updateNotifyEnabled
    };
})(window);
