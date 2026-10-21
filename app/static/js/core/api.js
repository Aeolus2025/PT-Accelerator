/**
 * 统一请求层：超时中止、JSON 序列化、错误归一、401 跳登录
 */
(function (global) {
    'use strict';

    var DEFAULT_TIMEOUT = 180000;

    function request(path, options) {
        options = options || {};

        var controller = new AbortController();
        // 显式传 0 表示不设超时；未传才用默认值
        var timeout = (options.timeout === undefined) ? DEFAULT_TIMEOUT : options.timeout;
        var timer = timeout > 0 ? setTimeout(function () { controller.abort(); }, timeout) : null;
        var hasBody = options.body !== undefined && options.body !== null;
        var isForm = typeof FormData !== 'undefined' && options.body instanceof FormData;

        return fetch(path, {
            method: options.method || 'GET',
            headers: Object.assign(
                (hasBody && !isForm) ? { 'Content-Type': 'application/json' } : {},
                options.headers || {}
            ),
            body: hasBody ? (isForm ? options.body : JSON.stringify(options.body)) : undefined,
            signal: controller.signal,
            credentials: 'same-origin'
        }).then(function (res) {
            if (res.status === 401) {
                global.location.href = '/login';
                var authErr = new Error('登录已失效');
                authErr.status = 401;
                throw authErr;
            }

            return res.text().then(function (text) {
                var data = null;
                if (text) {
                    try {
                        data = JSON.parse(text);
                    } catch (e) {
                        data = text;
                    }
                }

                if (!res.ok) {
                    var detail = (data && (data.detail || data.message))
                        || ('HTTP ' + res.status);
                    var err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
                    err.status = res.status;
                    err.data = data;
                    throw err;
                }

                return data;
            });
        }).catch(function (e) {
            if (e && e.name === 'AbortError') {
                var te = new Error('请求超时，请稍后刷新页面查看结果');
                te.timeout = true;
                throw te;
            }
            throw e;
        }).then(function (value) {
            clearTimeout(timer);
            return value;
        }, function (e) {
            clearTimeout(timer);
            throw e;
        });
    }

    global.api = {
        request: request,
        get: function (p, o) {
            return request(p, Object.assign({ method: 'GET' }, o || {}));
        },
        post: function (p, body, o) {
            return request(p, Object.assign({ method: 'POST', body: body }, o || {}));
        },
        // FormData 直传，交由浏览器生成 multipart 边界
        postForm: function (p, formData, o) {
            return request(p, Object.assign({ method: 'POST', body: formData }, o || {}));
        },
        put: function (p, body, o) {
            return request(p, Object.assign({ method: 'PUT', body: body }, o || {}));
        },
        del: function (p, o) {
            return request(p, Object.assign({ method: 'DELETE' }, o || {}));
        }
    };
})(window);
