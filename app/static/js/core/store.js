/**
 * 配置状态：单一数据源，写操作合并提交
 *
 * POST /api/config 是整份覆盖且会重启调度器，所以前端必须持有完整配置副本，
 * 并把连续修改合并成一次提交。
 */
(function (global) {
    'use strict';

    /**
     * 创建一个配置存储
     *
     * options:
     *   endpoint  读写地址
     *   initial   首屏初始数据
     *   unwrap/wrap  响应与请求体转换（通知接口包了一层 {success, notify}）
     */
    function createStore(options) {
        var opts = options || {};
        var ENDPOINT = opts.endpoint;
        var unwrap = opts.unwrap || function (d) { return d || {}; };
        var wrap = opts.wrap || function (s) { return s; };

        var state = opts.initial || null;
        var inflight = null;
        var listeners = [];
        var dirty = false;
        var inflightWrite = null;

        function get() {
            if (state === null) state = opts.initial || {};
            return state;
        }

        function notify() {
            listeners.forEach(function (fn) {
                try {
                    fn(get());
                } catch (e) {
                    console.error('store 订阅者执行异常', e);
                }
            });
        }

        // 并发去重：多个模块同时调用只发一次请求
        function load(force) {
            if (!force && inflight) return inflight;

            inflight = global.api.get(ENDPOINT).then(function (raw) {
                state = unwrap(raw) || {};
                notify();
                return state;
            }).then(function (value) {
                inflight = null;
                return value;
            }, function (e) {
                inflight = null;
                throw e;
            });

            return inflight;
        }

        // 合并提交：在途期间的新修改标记为脏，复用同一个 Promise
        function flush() {
            if (inflightWrite) {
                dirty = true;
                return inflightWrite;
            }

            dirty = false;

            function step() {
                return global.api.post(ENDPOINT, wrap(get())).then(function () {
                    if (dirty) {
                        dirty = false;
                        return step();
                    }
                    return get();
                });
            }

            inflightWrite = step().then(function (value) {
                inflightWrite = null;
                return value;
            }, function (e) {
                inflightWrite = null;
                // 失败回源，多个调用方共享同一次回源
                return load(true).then(function () {
                    throw e;
                }, function () {
                    throw e;
                });
            });

            return inflightWrite;
        }

        // 顶层字段合并后提交
        function patch(partial) {
            var next = {};
            var cur = get();
            for (var k in cur) {
                if (Object.prototype.hasOwnProperty.call(cur, k)) next[k] = cur[k];
            }
            for (var p in partial) {
                if (Object.prototype.hasOwnProperty.call(partial, p)) next[p] = partial[p];
            }
            state = next;
            notify();
            return flush();
        }

        return {
            ENDPOINT: ENDPOINT,
            get: get,
            section: function (name, fallback) {
                var v = get()[name];
                return (v === undefined || v === null) ? fallback : v;
            },
            load: load,
            patch: patch,
            flush: flush,
            subscribe: function (fn) {
                listeners.push(fn);
                return function unsubscribe() {
                    var i = listeners.indexOf(fn);
                    if (i >= 0) listeners.splice(i, 1);
                };
            }
        };
    }

    // 从 #app-config 数据岛读取初始配置
    function readInitial() {
        var node = document.getElementById('app-config');
        if (!node) return {};
        try {
            return JSON.parse(node.textContent) || {};
        } catch (e) {
            console.warn('app-config 数据岛解析失败，回退为空配置', e);
            return {};
        }
    }

    var store = createStore({
        endpoint: '/api/config',
        initial: readInitial()
    });

    // 通知配置：接口多包一层 {success, notify}
    var notifyStore = createStore({
        endpoint: '/api/notify/config',
        initial: {
            enable: false,
            hitokoto: true,
            channels: {}
        },
        unwrap: function (raw) {
            return (raw && raw.success && raw.notify) ? raw.notify : {};
        },
        wrap: function (state) {
            return { notify: state };
        }
    });

    // 数组内单条更新（trackers / hosts_sources）
    store.patchArray = function (name, matchKey, matchValue, changes) {
        var list = (store.section(name, []) || []).slice();
        var hit = false;

        for (var i = 0; i < list.length; i++) {
            if (list[i] && list[i][matchKey] === matchValue) {
                list[i] = Object.assign({}, list[i], changes);
                hit = true;
                break;
            }
        }

        if (!hit) {
            return Promise.reject(new Error('配置中未找到指定条目：' + matchKey + '=' + matchValue));
        }

        var partial = {};
        partial[name] = list;
        return store.patch(partial);
    };

    global.store = store;
    global.notifyStore = notifyStore;
})(window);
