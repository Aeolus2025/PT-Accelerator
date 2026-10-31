/**
 * 优选设置：CloudflareSpeedTest 命令行参数
 *
 * 表单完全由后端下发的 schema（#cfst-schema 数据岛）渲染：默认值、取值范围、
 * 中文说明、官方原文都来自 app/services/cfst_params.py，这里不重复维护一份。
 */
(function (global) {
    'use strict';

    var schemaData = null;
    var defaultsMap = {};

    function el(id) {
        return document.getElementById(id);
    }

    // ---------------------------------------------------------------- schema

    function readSchema() {
        if (schemaData) return schemaData;
        var node = el('cfst-schema');
        try {
            schemaData = node ? JSON.parse(node.textContent) : null;
        } catch (e) {
            console.error('[CFST] schema 解析失败', e);
            schemaData = null;
        }
        if (!schemaData || !schemaData.params) {
            schemaData = { groups: [], params: [] };
        }
        defaultsMap = {};
        schemaData.params.forEach(function (p) {
            defaultsMap[p.key] = p.default;
        });
        return schemaData;
    }

    function params() {
        return readSchema().params || [];
    }

    function flagToKey(flag) {
        var list = params();
        for (var i = 0; i < list.length; i++) {
            if (list[i].flag === flag) return list[i].key;
        }
        return null;
    }

    // ---------------------------------------------------------------- 渲染

    function renderField(p) {
        var id = 'cfst-' + p.key;
        var officialIcon = '';
        if (p.official) {
            // 官方原文比较长，用悬浮气泡按需展示，不占表单高度
            officialIcon = '<i class="bi bi-info-circle cfst-official" tabindex="0"'
                + ' data-bs-toggle="popover" data-bs-trigger="hover focus"'
                + ' data-bs-placement="top" data-bs-custom-class="cfst-popover"'
                + ' data-bs-title="官方说明"'
                + ' data-bs-content="' + ui.escapeHtml(p.official) + '"></i>';
        }
        var label = '<label class="col-sm-4 col-form-label" for="' + id + '">'
            + ui.escapeHtml(p.label)
            + ' <code class="text-muted small">' + ui.escapeHtml(p.flag) + '</code>'
            + officialIcon + '</label>';
        var control = '';

        if (p.type === 'bool') {
            control = '<div class="form-check form-switch mt-2">'
                + '<input class="form-check-input" type="checkbox" role="switch" id="' + id + '"'
                + ' data-key="' + p.key + '" data-type="bool">'
                + '<label class="form-check-label" for="' + id + '">开启</label></div>';
        } else if (p.type === 'int' || p.type === 'float') {
            var step = p.type === 'int' ? '1' : '0.01';
            var minAttr = (p.min === null || p.min === undefined) ? '' : ' min="' + p.min + '"';
            var maxAttr = (p.max === null || p.max === undefined) ? '' : ' max="' + p.max + '"';
            control = '<input type="number" class="form-control" id="' + id + '"'
                + ' data-key="' + p.key + '" data-type="' + p.type + '"'
                + minAttr + maxAttr + ' step="' + step + '">';
        } else {
            control = '<input type="text" class="form-control" id="' + id + '"'
                + ' data-key="' + p.key + '" data-type="str"'
                + (p.key === 'cfcolo' ? ' style="text-transform:uppercase" placeholder="留空表示不限制"' : '')
                + '>';
        }

        var help = '';
        if (p.desc) {
            help += '<div class="form-text">' + ui.escapeHtml(p.desc) + '</div>';
        }
        help += '<div class="form-text d-none" data-note="' + p.key + '"></div>';
        help += '<div class="form-text text-danger d-none" data-error="' + p.key + '"></div>';

        return '<div class="row mb-3" data-param="' + p.key + '">'
            + label
            + '<div class="col-sm-8">' + control + help + '</div>'
            + '</div>';
    }

    function render() {
        var container = el('cfst-form');
        if (!container) return;
        var schema = readSchema();
        var html = '';

        schema.groups.forEach(function (group) {
            var list = schema.params.filter(function (p) { return p.group === group.key; });
            if (!list.length) return;
            html += '<div class="card"><div class="card-header">' + ui.escapeHtml(group.label) + '</div>'
                + '<div class="card-body">'
                + '<p class="text-muted small mb-3">' + ui.escapeHtml(group.hint) + '</p>';
            list.forEach(function (p) { html += renderField(p); });
            html += '</div></div>';
        });

        disposePopovers();
        container.innerHTML = html || '<div class="alert alert-warning mb-0">未能加载参数定义，请刷新页面重试。</div>';
        initPopovers();
        applyValues(collectFromStore());
        applyDependencies();
    }

    // ---------------------------------------------------------------- 官方说明气泡

    function initPopovers() {
        var Popover = global.bootstrap && global.bootstrap.Popover;
        if (!Popover) return;
        document.querySelectorAll('#cfst-form [data-bs-toggle="popover"]').forEach(function (node) {
            Popover.getOrCreateInstance ? Popover.getOrCreateInstance(node) : new Popover(node);
        });
    }

    function disposePopovers() {
        var Popover = global.bootstrap && global.bootstrap.Popover;
        if (!Popover || !Popover.getInstance) return;
        document.querySelectorAll('#cfst-form [data-bs-toggle="popover"]').forEach(function (node) {
            var instance = Popover.getInstance(node);
            if (instance) instance.dispose();
        });
    }

    // ---------------------------------------------------------------- 取值与回填

    function collectFromStore() {
        var saved = store.section('cfst', {}) || {};
        var merged = {};
        Object.keys(defaultsMap).forEach(function (key) {
            merged[key] = Object.prototype.hasOwnProperty.call(saved, key) ? saved[key] : defaultsMap[key];
        });
        return merged;
    }

    function applyValues(values) {
        params().forEach(function (p) {
            var input = el('cfst-' + p.key);
            if (!input) return;
            var value = Object.prototype.hasOwnProperty.call(values, p.key) ? values[p.key] : p.default;
            if (p.type === 'bool') {
                input.checked = !!value;
            } else if (p.type === 'int') {
                input.value = String(parseInt(value, 10) || 0);
            } else if (p.type === 'float') {
                var fv = value === null || value === undefined ? 0 : value;
                // 固定小数位：tlr 显示 1.00 而不是 1，与上游写法一致
                input.value = p.precision ? Number(fv).toFixed(p.precision) : String(fv);
            } else {
                input.value = value === null || value === undefined ? '' : String(value);
            }
        });
    }

    function collect() {
        var out = {};
        params().forEach(function (p) {
            var input = el('cfst-' + p.key);
            if (!input) return;
            if (p.type === 'bool') {
                // 必须取真布尔：字符串 "false" 存进 YAML 后会被当成真值
                out[p.key] = !!input.checked;
            } else if (p.type === 'int') {
                var iv = parseInt(input.value, 10);
                out[p.key] = isNaN(iv) ? p.default : iv;
            } else if (p.type === 'float') {
                var fv = parseFloat(input.value);
                out[p.key] = isNaN(fv) ? p.default : fv;
            } else {
                out[p.key] = String(input.value || '').trim();
            }
        });
        return out;
    }

    // ---------------------------------------------------------------- 依赖联动

    function setNote(key, text) {
        var note = document.querySelector('[data-note="' + key + '"]');
        if (!note) return;
        note.textContent = text || '';
        note.classList.toggle('d-none', !text);
    }

    function setDisabled(key, disabled, note) {
        var input = el('cfst-' + key);
        if (input) input.disabled = !!disabled;
        setNote(key, disabled ? note : '');
    }

    function applyDependencies() {
        var dd = el('cfst-dd');
        var httping = el('cfst-httping');
        var downloadOff = !!(dd && dd.checked);
        var httpingOff = !(httping && httping.checked);

        ['dn', 'dt', 'sl'].forEach(function (key) {
            setDisabled(key, downloadOff, '已开启「仅测延迟」，本项不生效');
        });
        // 测速地址不禁用：HTTPing 模式下它同时是延迟测速地址
        setNote('url', httpingOff ? '' : 'HTTPing 模式下，这里同时作为延迟测速地址');

        ['httping_code', 'cfcolo'].forEach(function (key) {
            setDisabled(key, httpingOff, '仅在开启「使用 HTTP 协议测速」后生效');
        });
    }

    // ---------------------------------------------------------------- 字段校验

    /**
     * 单字段校验，规则与后端 cfst_params.validate 保持一致。
     * 前端先挡一道是为了即时反馈，保存时后端仍会再校验一次。
     */
    function fieldError(p, raw) {
        if (p.type === 'int' || p.type === 'float') {
            var text = String(raw === undefined || raw === null ? '' : raw).trim();
            if (!text) return '不能为空';
            var num = Number(text);
            if (!isFinite(num)) return '必须是数字';
            if (p.type === 'int' && Math.floor(num) !== num) return '必须是整数';
            if (p.min !== null && p.min !== undefined && num < p.min) return '不能小于 ' + p.min;
            if (p.max !== null && p.max !== undefined && num > p.max) return '不能大于 ' + p.max;
            return null;
        }
        if (p.type === 'str') {
            var value = String(raw || '').trim();
            if (p.key === 'url') {
                if (!value) return '不能为空';
                if (!/^https?:\/\//i.test(value)) return '必须以 http:// 或 https:// 开头';
                if (/\s/.test(value)) return '不能包含空格';
            }
            if (p.key === 'cfcolo' && value && !/^[A-Z]{3}(,[A-Z]{3})*$/.test(value.toUpperCase())) {
                return '格式应为 HKG 或 HKG,LAX';
            }
            return null;
        }
        return null;
    }

    function showFieldError(p, message) {
        var input = el('cfst-' + p.key);
        var box = document.querySelector('[data-error="' + p.key + '"]');
        if (input) {
            input.classList.toggle('is-invalid', !!message);
            if (message) input.classList.remove('is-valid');
        }
        if (box) {
            box.textContent = message || '';
            box.classList.toggle('d-none', !message);
        }
    }

    function validateAll() {
        var problems = [];
        params().forEach(function (p) {
            if (p.type === 'bool') return;
            var input = el('cfst-' + p.key);
            if (!input) return;
            var message = fieldError(p, input.value);
            showFieldError(p, message);
            if (message) {
                problems.push({ p: p, message: message });
            }
        });
        return problems;
    }

    function paramByKey(key) {
        var list = params();
        for (var i = 0; i < list.length; i++) {
            if (list[i].key === key) return list[i];
        }
        return null;
    }

    // ---------------------------------------------------------------- 保存

    function markInvalid(errorText) {
        document.querySelectorAll('#cfst-form .is-invalid').forEach(function (node) {
            node.classList.remove('is-invalid');
        });
        // 后端错误格式：<中文名> (-flag)：<原因>，按 -flag 找回输入框
        String(errorText || '').split('；').forEach(function (piece) {
            var match = piece.match(/\((-[a-z-]+)\)/);
            if (!match) return;
            var key = flagToKey(match[1]);
            var input = key && el('cfst-' + key);
            if (input) input.classList.add('is-invalid');
        });
    }

    function save() {
        var problems = validateAll();
        if (problems.length) {
            var first = problems[0];
            var input = el('cfst-' + first.p.key);
            if (input) input.focus();
            ui.showToast(
                '有 ' + problems.length + ' 项参数不合法：' + first.p.label
                + ' (' + first.p.flag + ') ' + first.message,
                'danger', 10000
            );
            return Promise.resolve();
        }

        var button = el('btn-save-cfst');
        var original = button ? button.innerHTML : '';
        if (button) {
            button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>保存中...';
            button.disabled = true;
        }

        var next = Object.assign({}, store.section('cfst', {}), collect());
        return store.patch({ cfst: next })
            .then(function () {
                ui.showToast('优选参数已保存', 'success');
                markInvalid('');
            })
            .catch(function (error) {
                var message = (error && error.message) || '保存失败';
                markInvalid(message);
                ui.showToast('保存失败：' + message, 'danger', 12000);
            })
            .then(function () {
                if (button) {
                    button.innerHTML = original;
                    button.disabled = false;
                }
            });
    }

    function resetDefaults() {
        ui.showConfirmModal('恢复默认参数', '将把本页所有参数恢复为 cfst 官方默认值，保存后生效。', function () {
            var next = Object.assign({}, store.section('cfst', {}), defaultsMap);
            store.patch({ cfst: next })
                .then(function () {
                    applyValues(defaultsMap);
                    applyDependencies();
                    ui.showToast('已恢复默认参数', 'success');
                })
                .catch(function (error) {
                    ui.showToast('恢复默认失败：' + ((error && error.message) || '未知错误'), 'danger');
                });
        });
    }

    // ---------------------------------------------------------------- 命令预览

    function showCommand() {
        var output = el('cfst-command-text');
        var modalEl = el('cfstCommandModal');
        if (!output || !modalEl) return;

        // 先开弹窗再请求：网络慢时用户能立刻看到反馈，而不是点了没反应
        output.textContent = '正在生成...';
        bootstrap.Modal.getOrCreateInstance(modalEl).show();

        api.post('/api/cfst/preview', { cfst: collect() })
            .then(function (data) {
                output.textContent = (data && data.command) || '(无参数)';
            })
            .catch(function (error) {
                output.textContent = '生成失败';
                ui.showToast('生成命令失败：' + ((error && error.message) || '未知错误'), 'danger');
            });
    }

    // ---------------------------------------------------------------- 立即运行

    function runNow() {
        var poll = ui.showProgressModal('正在启动优选任务...');
        api.post('/api/run-cfst-script', undefined, { timeout: 0 })
            .then(function (data) {
                ui.showToast((data && data.message) || '优选任务已启动', 'success', 8000);
                // 稍等一下再开始轮询，让后台任务先把状态置为 running
                setTimeout(function () {
                    poll(function (status) {
                        var message = (status && status.message) || '优选完成';
                        var failed = message.indexOf('失败') !== -1;
                        ui.showToast(message, failed ? 'danger' : 'success', 12000);
                        if (global.trackersPage) global.trackersPage.loadTrackers();
                        if (global.hostsPage) global.hostsPage.loadCurrentHosts();
                    });
                }, 1200);
            })
            .catch(function (error) {
                ui.hideProgressModal();
                ui.showToast('启动优选失败：' + ((error && error.message) || '未知错误'), 'danger', 12000);
            });
    }

    // ---------------------------------------------------------------- 初始化

    function init() {
        if (init.__bound) return;
        init.__bound = true;

        render();

        ui.delegate(document, 'click', '#btn-save-cfst', save);
        ui.delegate(document, 'click', '#btn-reset-cfst', resetDefaults);
        ui.delegate(document, 'click', '#btn-preview-cfst', showCommand);
        ui.delegate(document, 'click', '#btn-run-cfst', runNow);

        ui.delegate(document, 'change', '#cfst-form input', applyDependencies);

        // 边输边校验：离开输入框前就能看到「不能大于 1000」这类提示
        ui.delegate(document, 'input', '#cfst-form input', function () {
            var p = paramByKey(this.dataset.key);
            if (!p || p.type === 'bool') return;
            showFieldError(p, fieldError(p, this.value));
        });

        // 刻意不订阅 store 变化：后台任务结束会触发 load(true) 并重绘订阅者，
        // 那样会把用户填了一半还没保存的值冲掉。配置改了刷新页面即可。
    }

    global.cfstPage = {
        init: init,
        save: save,
        resetDefaults: resetDefaults,
        showCommand: showCommand,
        runNow: runNow,
        collect: collect,
        applyDependencies: applyDependencies
    };
})(window);
