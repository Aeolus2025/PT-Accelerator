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
        var currentInput = el('currentPassword');
        var newInput = el('newPassword');
        var confirmInput = el('confirmPassword');
        if (!currentInput || !newInput || !confirmInput) return;

        function needsCurrentPassword() {
            var checkbox = el('enableAuth');
            return !!(checkbox && checkbox.checked && initialAuthConfig && initialAuthConfig.password_hash);
        }

        function validateConfirm() {
            var feedback = el('confirmPasswordFeedback');
            var validFeedback = el('confirmPasswordValid');
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
            var feedback = el('newPasswordFeedback');
            var validFeedback = el('newPasswordValid');
            var currentFeedback = el('currentPasswordFeedback');

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
            var feedback = el('currentPasswordFeedback');

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
            ['toggleCurrentPassword', 'currentPassword'],
            ['toggleNewPassword', 'newPassword'],
            ['toggleConfirmPassword', 'confirmPassword']
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

    // ---------------------------------------------------------------- 错误建议

    function getErrorSuggestion(message) {
        var text = String(message || '');

        function hasAny() {
            for (var i = 0; i < arguments.length; i++) {
                if (text.indexOf(arguments[i]) !== -1) return true;
            }
            return false;
        }

        if (hasAny('当前密码错误', '当前密码不正确', 'Current password is incorrect',
                   '密码验证失败', 'Invalid current password', 'password verification failed')) {
            return '请检查输入的当前密码是否正确，注意大小写和特殊字符。您可以尝试重新输入或使用密码显示功能确认输入内容。';
        }
        if (hasAny('密码长度')) {
            return '新密码必须包含至少8个字符，建议使用大小写字母、数字和特殊字符的组合以提高安全性。';
        }
        if (hasAny('密码不匹配', '新密码与确认密码不匹配')) {
            return '请确保新密码和确认密码输入完全一致。建议使用复制粘贴或密码显示功能来避免输入错误。';
        }
        if (hasAny('需要提供当前密码', '修改密码需要')) {
            return '由于系统已设置密码且认证已启用，修改密码时必须先验证当前密码以确保安全性。';
        }
        if (hasAny('密码强度', '不符合安全要求')) {
            return '密码应包含大小写字母、数字或特殊字符以提高安全性。建议使用至少包含2种类型字符的组合。';
        }
        if (hasAny('TOAST: Option "delay"', 'Bootstrap Toast')) {
            return '页面脚本执行出现问题，请刷新页面后重试。这通常是临时的前端错误。';
        }
        if (hasAny('请求失败') && !hasAny('TOAST')) {
            return '网络连接可能存在问题，请检查网络连接状态后重试。如果问题持续，请检查服务器状态。';
        }
        if (hasAny('无权修改', '权限')) {
            return '您当前没有足够的权限执行此操作，请确认您已正确登录管理员账户。';
        }
        if (hasAny('配置更新失败')) {
            return '配置文件可能被其他进程占用或权限不足，请稍后重试或检查文件权限。';
        }
        if (hasAny('系统中没有设置密码')) {
            return '当前系统中尚未设置密码，请清空当前密码字段，只输入新密码即可完成首次设置。';
        }
        return '如果问题持续存在，请查看系统日志获取详细信息或联系管理员寻求帮助。';
    }

    // ---------------------------------------------------------------- 保存

    function updateAuthUI(authConfig) {
        var checkbox = el('enableAuth');
        var fields = el('authFields');
        var username = el('authUsername');

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
            ['currentPassword', 'currentPasswordFeedback', null],
            ['newPassword', 'newPasswordFeedback', 'newPasswordValid'],
            ['confirmPassword', 'confirmPasswordFeedback', 'confirmPasswordValid']
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

    async function fetchAuthConfig() {
        try {
            var config = await api.get('/api/config');
            return (config && config.auth) ? config.auth : initialAuthConfig;
        } catch (error) {
            console.error('获取认证配置失败:', error);
            return initialAuthConfig;
        }
    }

    function showError(title, message, suggestion, retry) {
        console.error(title, message);
        showToast(message, 'danger');
        showErrorModal(title, message, suggestion || '', !!retry, retry || null);
    }

    async function saveAuthSettings() {
        var form = el('authSettingsForm');
        if (!form) return;

        var formData = new FormData(form);
        var newPassword = formData.get('new_password');
        var confirmPassword = formData.get('confirm_password');
        var currentPassword = formData.get('current_password');
        var checkbox = el('enableAuth');

        if (newPassword) {
            if (!validatePassword(newPassword).valid) {
                showError('密码验证失败', '新密码不符合安全要求', getErrorSuggestion('密码强度'));
                return;
            }
            if (newPassword !== confirmPassword) {
                showError('密码验证失败', '新密码与确认密码不匹配', getErrorSuggestion('密码不匹配'));
                return;
            }
            if (checkbox && checkbox.checked && initialAuthConfig.password_hash && !currentPassword) {
                showError('身份验证需要', '修改密码需要输入当前密码', getErrorSuggestion('需要提供当前密码'));
                var currentInput = el('currentPassword');
                if (currentInput) currentInput.focus();
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

        var saveButton = el('save-auth-settings');
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
                var fields = el('authFields');
                if (fields) fields.classList.add('d-none');
                showSuccessModal('设置更新成功', successMsg, '', {
                    countdown: 10,
                    confirmText: '立即刷新',
                    onDone: function () { window.location.replace(window.location.pathname); }
                });
            } else {
                var updated = await fetchAuthConfig();
                initialAuthConfig = updated;
                store.patch({ auth: Object.assign({}, store.section('auth', {}), updated) })
                    .catch(function (e) { console.warn('同步认证配置到 store 失败', e); });
                updateAuthUI(updated);
                showSuccessModal('设置更新成功', successMsg);
            }

            showToast(successMsg, 'success');
            clearPasswordFields();
        } catch (error) {
            var message = (error && error.message) || String(error) || '请求失败';
            showError('网络请求失败', message, getErrorSuggestion(message), saveAuthSettings);
        } finally {
            if (saveButton) {
                saveButton.innerHTML = originalText;
                saveButton.disabled = false;
            }
        }
    }

    // ---------------------------------------------------------------- 初始化

    function initAuthSettings() {
        initialAuthConfig = store.section('auth', {}) || {};

        var checkbox = el('enableAuth');
        var fields = el('authFields');
        if (checkbox && fields) {
            updateAuthUI(initialAuthConfig);

            checkbox.addEventListener('change', function () {
                if (!this.checked) {
                    fields.classList.add('d-none');
                    return;
                }
                fields.classList.remove('d-none');
            });
        }

        setupPasswordValidation();
        setupPasswordToggle();

        var saveButton = el('save-auth-settings');
        if (saveButton) {
            saveButton.addEventListener('click', function (e) {
                e.preventDefault();
                saveAuthSettings();
            });
        }
    }

    global.authPage = {
        validatePassword: validatePassword,
        getErrorSuggestion: getErrorSuggestion,
        saveAuthSettings: saveAuthSettings,
        fetchAuthConfig: fetchAuthConfig,
        initAuthSettings: initAuthSettings
    };

    // 兼容现有调用点
    global.validatePassword = validatePassword;
    global.getErrorSuggestion = getErrorSuggestion;
    global.saveAuthSettings = saveAuthSettings;
    global.fetchAuthConfig = fetchAuthConfig;
    global.setupPasswordValidation = setupPasswordValidation;
    global.setupPasswordToggle = setupPasswordToggle;
})(window);
