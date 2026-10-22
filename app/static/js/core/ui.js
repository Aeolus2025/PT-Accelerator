/**
 * 通用 UI：转义、事件委托、表格渲染、toast / 确认框 / 进度框
 *
 * 事件委托只绑一次，节点增删由冒泡兜住，避免渲染后重绑导致的漏绑和重复触发。
 */
(function (global) {
    'use strict';

    var ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

    function escapeHtml(v) {
        return String(v === null || v === undefined ? '' : v).replace(/[&<>"']/g, function (c) {
            return ESC[c];
        });
    }

    // 在 root 上委托一次，同一 (type, selector) 不会重复绑定
    function delegate(root, type, selector, handler) {
        if (!root) return;
        root.__delegated = root.__delegated || {};
        var key = type + '|' + selector;
        if (root.__delegated[key]) return;
        root.__delegated[key] = true;

        root.addEventListener(type, function (e) {
            var target = e.target.closest ? e.target.closest(selector) : null;
            if (target && root.contains(target)) handler.call(target, e, target);
        });
    }

    // columns: [{ key, render? }]。有 render 时按原始 HTML 插入，调用方负责转义
    function renderTable(tbody, rows, columns, emptyText) {
        if (!tbody) return;

        if (!rows || rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="' + columns.length
                + '" class="text-center text-muted">' + escapeHtml(emptyText || '暂无数据') + '</td></tr>';
            return;
        }

        tbody.innerHTML = rows.map(function (row) {
            var cells = columns.map(function (col) {
                var html = col.render ? col.render(row) : escapeHtml(row[col.key]);
                return '<td>' + html + '</td>';
            }).join('');
            return '<tr>' + cells + '</tr>';
        }).join('');
    }

    function showToast(message, type, delay) {
        if (type === undefined || type === null) type = 'info';
        if (typeof delay !== 'number') {
            delay = parseInt(delay, 10) || 8000;
        }

        // 相同内容已在显示中：先关掉旧的
        document.querySelectorAll('.toast').forEach(function (toast) {
            var body = toast.querySelector('.toast-body');
            if (body && body.textContent.trim() === String(message)) {
                var inst = bootstrap.Toast.getInstance(toast);
                if (inst) inst.hide();
            }
        });

        var toastElement = document.createElement('div');
        toastElement.className = 'toast align-items-center text-white bg-' + type + ' border-0';
        toastElement.setAttribute('role', 'alert');
        toastElement.setAttribute('aria-live', 'assertive');
        toastElement.setAttribute('aria-atomic', 'true');
        toastElement.innerHTML = '<div class="d-flex">'
            + '<div class="toast-body">' + message + '</div>'
            + '<button type="button" class="btn-close btn-close-white me-2 m-auto"'
            + ' data-bs-dismiss="toast" aria-label="Close"></button>'
            + '</div>';

        var container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            document.body.appendChild(container);
        }
        container.appendChild(toastElement);

        var toast = new bootstrap.Toast(toastElement, { autohide: true, delay: delay });

        var paused = false;
        var remaining = delay;
        var hideTimeout;

        // 悬停时暂停倒计时，移开后按剩余时间继续
        toastElement.addEventListener('mouseenter', function () {
            paused = true;
            toast._config.autohide = false;
            clearTimeout(hideTimeout);
        });
        toastElement.addEventListener('mouseleave', function () {
            paused = false;
            toast._config.autohide = true;
            hideTimeout = setTimeout(function () { toast.hide(); }, remaining);
        });
        toastElement.addEventListener('shown.bs.toast', function () {
            var start = Date.now();
            hideTimeout = setTimeout(function () {
                if (!paused) toast.hide();
            }, remaining);
            toastElement.addEventListener('mouseenter', function () {
                remaining -= Date.now() - start;
            }, { once: true });
        });

        toast.show();

        toastElement.addEventListener('hidden.bs.toast', function () {
            try {
                if (toastElement.parentNode) toastElement.parentNode.removeChild(toastElement);
                if (container && container.parentNode && container.children.length === 0) {
                    container.parentNode.removeChild(container);
                }
            } catch (e) {
                console.warn('Toast cleanup warning:', e);
            }
        });
    }

    function showConfirmModal(title, message, onConfirm) {
        var titleEl = document.getElementById('confirmModalLabel');
        var messageEl = document.getElementById('confirm-message');
        var okBtn = document.getElementById('btn-confirm-ok');
        var modalEl = document.getElementById('confirmModal');

        if (!titleEl || !messageEl || !okBtn || !modalEl) {
            if (confirm(message)) {
                if (typeof onConfirm === 'function') onConfirm();
            }
            return;
        }

        titleEl.textContent = title || '确认操作';
        messageEl.textContent = message || '确定要执行此操作吗？';
        var modal = bootstrap.Modal.getOrCreateInstance(modalEl);

        // 清掉上一次残留的回调，避免点一次触发多个
        if (global.__confirmOkHandler) {
            try { okBtn.removeEventListener('click', global.__confirmOkHandler); } catch (e) { /* noop */ }
            global.__confirmOkHandler = null;
        }

        var handler = function () {
            modal.hide();
            try { okBtn.removeEventListener('click', handler); } catch (e) { /* noop */ }
            global.__confirmOkHandler = null;
            if (typeof onConfirm === 'function') onConfirm();
        };
        okBtn.addEventListener('click', handler);
        global.__confirmOkHandler = handler;

        var cleanup = function () {
            if (global.__confirmOkHandler) {
                try { okBtn.removeEventListener('click', global.__confirmOkHandler); } catch (e) { /* noop */ }
                global.__confirmOkHandler = null;
            }
            modalEl.removeEventListener('hidden.bs.modal', cleanup);
        };
        modalEl.addEventListener('hidden.bs.modal', cleanup);
        modal.show();
    }

    // 返回轮询函数，任务完成后自动隐藏弹窗并回调；返回的 intervalId 可提前中止
    function showProgressModal(message) {
        $('#progressModal').modal({ backdrop: 'static', keyboard: false });
        $('#progressModal').modal('show');
        $('#progress-message').text(message || '请稍候，操作正在进行中...');

        return function pollTaskStatus(callback) {
            var intervalId = setInterval(function () {
                $.ajax({
                    url: '/api/task-status',
                    type: 'GET',
                    success: function (response) {
                        console.log('Task status response:', response);
                        if (response.message) {
                            $('#progress-message').text(response.message);
                        }
                        if (response.status === 'done') {
                            clearInterval(intervalId);
                            hideProgressModal();
                            if (typeof callback === 'function') callback(response);
                        }
                    },
                    error: function (xhr, status, error) {
                        console.error('Poll task status failed:', status, error);
                        clearInterval(intervalId);
                        hideProgressModal();
                        showToast('查询任务状态失败: ' + error, 'danger');
                    }
                });
            }, 2000);
            return intervalId;
        };
    }

    function hideProgressModal() {
        $('#progressModal').modal('hide');
    }

    // ---------------------------------------------------------------- 结果弹窗

    var successCountdownTimer = null;

    function clearSuccessCountdown() {
        if (successCountdownTimer) {
            clearInterval(successCountdownTimer);
            successCountdownTimer = null;
        }
    }

    function showErrorModal(title, message, suggestion, showRetry, retryCallback) {
        var labelEl = document.getElementById('errorModalLabel');
        var messageEl = document.getElementById('error-message');
        var suggestionEl = document.getElementById('error-suggestion');
        var retryBtn = document.getElementById('btn-error-retry');
        var modalEl = document.getElementById('errorModal');
        if (!labelEl || !messageEl || !modalEl) return;

        labelEl.innerHTML = '<i class="bi bi-exclamation-triangle-fill me-2"></i>' + escapeHtml(title);
        messageEl.textContent = message;

        if (suggestionEl) {
            suggestionEl.textContent = suggestion || '';
            suggestionEl.style.display = suggestion ? 'block' : 'none';
        }

        if (retryBtn) {
            if (showRetry && typeof retryCallback === 'function') {
                retryBtn.style.display = 'inline-block';
                retryBtn.onclick = function () {
                    var inst = bootstrap.Modal.getInstance(modalEl);
                    if (inst) inst.hide();
                    retryCallback();
                };
            } else {
                retryBtn.style.display = 'none';
            }
        }

        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    // options.countdown + options.onDone：倒计时归零或点「确定」都立即执行 onDone
    // options.confirmText：倒计时模式下按钮文案
    function showSuccessModal(title, message, note, options) {
        options = options || {};

        var labelEl = document.getElementById('successModalLabel');
        var messageEl = document.getElementById('success-message');
        var noteEl = document.getElementById('success-note');
        var confirmBtn = document.getElementById('btn-success-modal-confirm');
        var countdownEl = document.getElementById('success-countdown');
        var modalEl = document.getElementById('successModal');
        if (!labelEl || !messageEl || !modalEl) return;

        labelEl.innerHTML = '<i class="bi bi-check-circle-fill me-2"></i>' + escapeHtml(title);
        messageEl.textContent = message;

        if (noteEl) {
            noteEl.textContent = note || '';
            noteEl.style.display = note ? 'block' : 'none';
        }

        var countdown = options.countdown;
        var onDone = options.onDone;
        clearSuccessCountdown();

        if (typeof countdown === 'number' && countdown > 0 && typeof onDone === 'function') {
            var remaining = countdown;

            if (confirmBtn) {
                confirmBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i>'
                    + escapeHtml(options.confirmText || '立即刷新');
                confirmBtn.onclick = function () {
                    clearSuccessCountdown();
                    onDone();
                };
            }

            if (countdownEl) {
                countdownEl.classList.remove('d-none');
                countdownEl.textContent = remaining + ' 秒后自动刷新…';
            }

            successCountdownTimer = setInterval(function () {
                remaining -= 1;
                if (remaining <= 0) {
                    clearSuccessCountdown();
                    onDone();
                    return;
                }
                if (countdownEl) countdownEl.textContent = remaining + ' 秒后自动刷新…';
            }, 1000);
        } else {
            if (confirmBtn) {
                confirmBtn.innerHTML = '<i class="bi bi-check-lg me-1"></i>确定';
                confirmBtn.onclick = null;
            }
            if (countdownEl) {
                countdownEl.classList.add('d-none');
                countdownEl.textContent = '';
            }
        }

        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    // 弹窗关闭后定时器仍在跑会误刷新，这里统一收掉
    document.addEventListener('DOMContentLoaded', function () {
        var modalEl = document.getElementById('successModal');
        if (modalEl) modalEl.addEventListener('hidden.bs.modal', clearSuccessCountdown);
    });

    global.ui = {
        escapeHtml: escapeHtml,
        delegate: delegate,
        renderTable: renderTable,
        showToast: showToast,
        showConfirmModal: showConfirmModal,
        showProgressModal: showProgressModal,
        hideProgressModal: hideProgressModal,
        showSuccessModal: showSuccessModal,
        showErrorModal: showErrorModal
    };
})(window);
