/**
 * 认证设置：密码校验、显示切换、保存
 */
(function (global) {
    'use strict';

    var initialAuthConfig = {};

    function el(id) {
        return document.getElementById(id);
    }

    // ---------------------------------------------------------------- 密码校验

    function validatePassword(password) {
        var hasUpper = /[A-Z]/.test(password);
        var hasLower = /[a-z]/.test(password);
        var hasNumber = /\d/.test(password);
        var hasSpecial = /[!@#$%^&*()_+\-=[\]{};':"\\|,.<>/?]/.test(password);
        var strength = (hasUpper ? 1 : 0) + (hasLower ? 1 : 0) + (hasNumber ? 1 : 0) + (hasSpecial ? 1 : 0);

        return {
            length: password.length >= 8,
            strength: strength,
            valid: password.length >= 8 && strength >= 2
        };
    }

    function setupPasswordValidation() {
        var currentInput = el('current-password');
        var newInput = el('new-password');
        var confirmInput = el('confirm-password');
        if (!currentInput || !newInput || !confirmInput) return;

        function needsCurrentPassword() {
            var checkbox = el('enable-auth');
            return !!(checkbox && checkbox.checked && initialAuthConfig && initialAuthConfig.password_set);
        }

        function validateConfirm() {
            var feedback = el('confirm-password-feedback');
            var validFeedback = el('confirm-password-valid');
            var value = confirmInput.value;

            if (!value) {
                confirmInput.classList.remove('is-valid', 'is-invalid');
                if (feedback) feedback.textContent = '';
                if (validFeedback) validFeedback.textContent = '';
                return;
            }

            if (newInput.value !== value) {
                confirmInput.classList.add('is-invalid');
                confirmInput.classList.remove('is-valid');
                if (feedback) feedback.textContent = '密码不匹配，请重新输入';
                if (validFeedback) validFeedback.textContent = '';
            } else {
                confirmInput.classList.add('is-valid');
                confirmInput.classList.remove('is-invalid');
                if (feedback) feedback.textContent = '';
                if (validFeedback) validFeedback.textContent = '密码匹配';
            }
        }

        newInput.addEventListener('input', function () {
            var password = this.value;
            var feedback = el('new-password-feedback');
            var validFeedback = el('new-password-valid');
            var currentFeedback = el('current-password-feedback');

            if (!password) {
                this.classList.remove('is-valid', 'is-invalid');
                if (feedback) feedback.textContent = '';
                if (validFeedback) validFeedback.textContent = '';
                currentInput.classList.remove('is-invalid', 'is-valid');
                if (currentFeedback) currentFeedback.textContent = '';
                return;
            }

            var result = validatePassword(password);

            if (!result.length) {
                this.classList.add('is-invalid');
                this.classList.remove('is-valid');
                if (feedback) feedback.textContent = '密码长度至少需要8位字符';
                if (validFeedback) validFeedback.textContent = '';
            } else if (result.strength < 2) {
                this.classList.add('is-invalid');
                this.classList.remove('is-valid');
                if (feedback) feedback.textContent = '密码强度较弱，建议包含大小写字母、数字或特殊字符';
                if (validFeedback) validFeedback.textContent = '';
            } else {
                this.classList.add('is-valid');
                this.classList.remove('is-invalid');
                if (feedback) feedback.textContent = '';
                if (validFeedback) validFeedback.textContent = result.strength >= 3 ? '密码强度优秀' : '密码强度良好';
            }

            if (!currentInput.value && needsCurrentPassword()) {
                currentInput.classList.add('is-invalid');
                currentInput.classList.remove('is-valid');
                if (currentFeedback) currentFeedback.textContent = '修改密码需要输入当前密码';
            }

            if (confirmInput.value) validateConfirm();
        });

        confirmInput.addEventListener('input', validateConfirm);

        currentInput.addEventListener('input', function () {
            var feedback = el('current-password-feedback');

            if (!this.value && newInput.value && needsCurrentPassword()) {
                this.classList.add('is-invalid');
                this.classList.remove('is-valid');
                if (feedback) feedback.textContent = '修改密码需要输入当前密码';
            } else {
                this.classList.remove('is-invalid', 'is-valid');
                if (feedback) feedback.textContent = '';
            }
        });
    }

    function setupPasswordToggle() {
        [
            ['toggle-current-password', 'current-password'],
            ['toggle-new-password', 'new-password'],
            ['toggle-confirm-password', 'confirm-password']
        ].forEach(function (pair) {
            var btn = el(pair[0]);
            var input = el(pair[1]);
            if (!btn || !input) return;

            btn.addEventListener('click', function () {
                input.setAttribute('type', input.getAttribute('type') === 'password' ? 'text' : 'password');
                this.classList.toggle('bi-eye');
                this.classList.toggle('bi-eye-slash');
            });
        });
    }

    // ---------------------------------------------------------------- 错误分类

    // 表单填错（当前密码错、两次不一致等）是用户自己就能改的问题：
    // 标红对应输入框即可，不弹窗，也不给「重试」——原样再提交一次必然同样失败。
    var FIELD_ERRORS = [
        {
            match: ['当前密码错误', '当前密码不正确'],
            field: 'current-password', title: '当前密码错误',
            hint: '请重新输入当前密码'
        },
        {
            match: ['没有设置密码'],
            field: 'current-password', title: '当前没有设置密码',
            hint: '请清空当前密码，只填写新密码'
        },
        {
            match: ['需要提供当前密码', '需要当前密码'],
            field: 'current-password', title: '需要当前密码',
            hint: '修改密码前需先验证当前密码'
        },
        {
            match: ['不匹配'],
            field: 'confirm-password', title: '两次密码不一致',
            hint: '请确认新密码与确认密码完全相同'
        },
        {
            match: ['长度'],
            field: 'new-password', title: '密码长度不足',
            hint: '新密码至少 8 位'
        },
        {
            match: ['强度', '安全要求'],
            field: 'new-password', title: '密码强度不足',
            hint: '至少包含大小写字母、数字、特殊字符中的两类'
        }
    ];

    var FIELD_FEEDBACK = {
        'current-password': 'current-password-feedback',
        'new-password': 'new-password-feedback',
        'confirm-password': 'confirm-password-feedback'
    };

    /**
     * 把请求错误分成三类，决定提示形态：
     *  - 字段级（4xx 且能对应到某个输入框）：标红该字段，不弹窗
     *  - 服务端/网络（超时、5xx、请求没发出去）：弹窗，带重试
     *  - 其他 4xx（403 等）：弹窗，不给重试
     */
    function classifyError(error) {
        var status = error && error.status;
        var message = String((error && error.message) || '');

        if (error && error.timeout) {
            return { title: '请求超时', message: '服务器响应超时，请稍后重试', retry: true };
        }

        // 没有 status：请求根本没到服务端（断网、服务未启动、被代理拦截）
        if (!status) {
            return {
                title: '无法连接服务器',
                message: message || '请检查网络连接，或确认服务是否正常运行',
                retry: true
            };
        }

        if (status >= 500) {
            return { title: '服务器处理失败', message: message || '服务端发生错误，详情见系统日志', retry: true };
        }

        if (status === 403) {
            return { title: '无权修改', message: message || '当前账户没有修改认证配置的权限', retry: false };
        }

        for (var i = 0; i < FIELD_ERRORS.length; i++) {
            var rule = FIELD_ERRORS[i];
            for (var j = 0; j < rule.match.length; j++) {
                if (message.indexOf(rule.match[j]) !== -1) {
                    return {
                        title: rule.title,
                        message: message,
                        hint: rule.hint,
                        field: rule.field,
                        retry: false
                    };
                }
            }
        }

        return {
            title: '操作未完成',
            message: message || ('请求被拒绝（HTTP ' + status + '）'),
            retry: false
        };
    }

    function markFieldInvalid(fieldId, hint) {
        var input = el(fieldId);
        if (!input) return;

        input.classList.add('is-invalid');
        input.classList.remove('is-valid');

        var feedback = el(FIELD_FEEDBACK[fieldId]);
        if (feedback) feedback.textContent = hint || '';

        input.focus();
        if (input.select) {
            try { input.select(); } catch (e) { /* 部分输入类型不支持 select */ }
        }
    }

    function reportError(error) {
        var info = classifyError(error);
        console.error('[AUTH] 保存失败:', info.title, error);

        if (info.field) {
            // 字段级问题：只标红 + 一条轻提示，不打断操作
            markFieldInvalid(info.field, info.hint);
            ui.showToast(info.hint ? info.title + '：' + info.hint : info.title, 'danger');
            return;
        }

        ui.showErrorModal(info.title, info.message, '', info.retry, info.retry ? saveAuthSettings : null);
    }

    function updateAuthUI(authConfig) {
        var checkbox = el('enable-auth');
        var fields = el('auth-fields');
        var username = el('auth-username');

        if (checkbox) checkbox.checked = !!authConfig.enable;
        if (username) username.value = authConfig.username || '';
        if (fields) {
            if (authConfig.enable) {
                fields.classList.remove('d-none');
            } else {
                fields.classList.add('d-none');
            }
        }
    }

    function clearPasswordFields() {
        [
            ['current-password', 'current-password-feedback', null],
            ['new-password', 'new-password-feedback', 'new-password-valid'],
            ['confirm-password', 'confirm-password-feedback', 'confirm-password-valid']
        ].forEach(function (triple) {
            var input = el(triple[0]);
            var feedback = el(triple[1]);
            if (input) {
                input.value = '';
                input.classList.remove('is-valid', 'is-invalid');
            }
            if (feedback) feedback.textContent = '';
            if (triple[2]) {
                var validFeedback = el(triple[2]);
                if (validFeedback) validFeedback.textContent = '';
            }
        });
    }

    // 认证配置只在页面初始化时读取，直接用 store 里的缓存
    function fetchAuthConfig() {
        return store.section('auth', initialAuthConfig) || initialAuthConfig;
    }

    async function saveAuthSettings() {
        var form = el('auth-settings-form');
        if (!form) return;

        var formData = new FormData(form);
        var newPassword = formData.get('new_password');
        var confirmPassword = formData.get('confirm_password');
        var currentPassword = formData.get('current_password');
        var checkbox = el('enable-auth');

        if (newPassword) {
            var strength = validatePassword(newPassword);
            if (!strength.length) {
                markFieldInvalid('new-password', '密码长度至少需要8位字符');
                ui.showToast('密码长度至少需要8位字符', 'danger');
                return;
            }
            if (strength.strength < 2) {
                markFieldInvalid('new-password', '密码强度较弱，建议包含大小写字母、数字或特殊字符');
                ui.showToast('密码强度较弱，建议包含大小写字母、数字或特殊字符', 'danger');
                return;
            }
            if (newPassword !== confirmPassword) {
                markFieldInvalid('confirm-password', '密码不匹配，请重新输入');
                ui.showToast('新密码与确认密码不匹配', 'danger');
                return;
            }
            if (checkbox && checkbox.checked && initialAuthConfig.password_set && !currentPassword) {
                markFieldInvalid('current-password', '修改密码需要输入当前密码');
                ui.showToast('修改密码需要输入当前密码', 'danger');
                return;
            }
        }

        formData.set('enable_auth', checkbox ? checkbox.checked : false);

        // 没填新密码时不要提交密码字段，避免误清空
        if (!newPassword) {
            formData.delete('new_password');
            formData.delete('confirm_password');
            formData.delete('current_password');
        }

        var saveButton = el('btn-save-auth-settings');
        var originalText = saveButton ? saveButton.innerHTML : '';
        if (saveButton) {
            saveButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>保存中...';
            saveButton.disabled = true;
        }

        try {
            var result = await api.postForm('/api/auth/config', formData);
            var successMsg = (result && result.message) || '认证设置已更新。';

            var targetEnable = checkbox ? checkbox.checked : false;
            var becomingEnabled = Boolean(targetEnable && !(initialAuthConfig && initialAuthConfig.enable));
            var msg = String(successMsg);
            var needReload = becomingEnabled
                || msg.indexOf('建议重新登录') !== -1
                || msg.indexOf('下次访问生效') !== -1
                || msg.indexOf('已自动登出') !== -1;

            if (needReload) {
                var fields = el('auth-fields');
                if (fields) fields.classList.add('d-none');
                ui.showSuccessModal('设置更新成功', successMsg, '', {
                    countdown: 10,
                    confirmText: '立即刷新',
                    onDone: function () { window.location.replace(window.location.pathname); }
                });
            } else {
                var updated = fetchAuthConfig();
                initialAuthConfig = updated;
                store.patch({ auth: Object.assign({}, store.section('auth', {}), updated) })
                    .catch(function (e) { console.warn('同步认证配置到 store 失败', e); });
                updateAuthUI(updated);
                ui.showSuccessModal('设置更新成功', successMsg);
            }

            ui.showToast(successMsg, 'success');
            clearPasswordFields();
        } catch (error) {
            reportError(error);
        } finally {
            if (saveButton) {
                saveButton.innerHTML = originalText;
                saveButton.disabled = false;
            }
        }
    }

    // ---------------------------------------------------------------- 初始化

    function initAuthSettings() {
        // 防重复绑定
        if (initAuthSettings.__bound) return;
        initAuthSettings.__bound = true;

        initialAuthConfig = store.section('auth', {}) || {};

        var checkbox = el('enable-auth');
        var fields = el('auth-fields');
        if (checkbox && fields) {
            updateAuthUI(initialAuthConfig);

            checkbox.addEventListener('change', function () {
                if (!this.checked) {
                    fields.classList.add('d-none');
                    return;
                }
                fields.classList.remove('d-none');
            });

            // 首屏若拿到空配置（如数据岛缺失），配置加载完成后再校正一次开关状态
            store.load().then(function () {
                initialAuthConfig = store.section('auth', {}) || {};
                updateAuthUI(initialAuthConfig);
            }).catch(function () { /* 加载失败时保持现状 */ });
        }

        setupPasswordValidation();
        setupPasswordToggle();

        var saveButton = el('btn-save-auth-settings');
        if (saveButton) {
            saveButton.addEventListener('click', function (e) {
                e.preventDefault();
                saveAuthSettings();
            });
        }
    }

    global.authPage = {
        validatePassword: validatePassword,
        classifyError: classifyError,
        saveAuthSettings: saveAuthSettings,
        fetchAuthConfig: fetchAuthConfig,
        initAuthSettings: initAuthSettings
    };
})(window);
