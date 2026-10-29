/**
 * 主标签页与地址栏同步：每个板块有独立路径。
 *
 * 路径是唯一依据——刷新、书签、前进后退都按地址还原，
 * 不再需要 sessionStorage 记上次位置。
 */
(function (global) {
    'use strict';

    var DEFAULT = 'dashboard-tab';

    var TAB_PATHS = {
        'dashboard-tab': '/dashboard',
        'trackers-tab': '/trackers',
        'hosts-tab': '/hosts',
        'clients-tab': '/clients',
        'notify-tab': '/notify',
        'logs-tab': '/logs',
        'auth-settings-tab': '/auth'
    };

    function valid(id) {
        var btn = id && document.getElementById(id);
        return !!(btn && btn.classList.contains('nav-link'));
    }

    function pathOf(id) {
        return TAB_PATHS[id] || TAB_PATHS[DEFAULT];
    }

    function tabOf(path) {
        var normalized = String(path || '').replace(/\/+$/, '') || '/';
        for (var id in TAB_PATHS) {
            if (Object.prototype.hasOwnProperty.call(TAB_PATHS, id) && TAB_PATHS[id] === normalized) {
                return id;
            }
        }
        return null;
    }

    function show(id) {
        if (!valid(id)) return;
        // Bootstrap 的 Tab 实例负责显示面板并派发 shown.bs.tab
        var instance = global.bootstrap && global.bootstrap.Tab.getOrCreateInstance(
            document.getElementById(id)
        );
        if (instance) instance.show();
    }

    // 必须在各页面模块 init 之前调用，否则切页的 shown 事件没人接
    function init() {
        var fromPath = tabOf(location.pathname);
        var target = fromPath || DEFAULT;

        // 地址栏没有对应板块（/ 已由后端跳到 /dashboard，这里是兜底）时先修正，
        // 免得随后的 shown 事件再压一条历史
        if (!fromPath) {
            history.replaceState({ tab: target }, '', pathOf(target));
        }

        show(target);

        document.addEventListener('shown.bs.tab', function (event) {
            var id = event.target && event.target.id;
            if (!id || !event.target.classList.contains('nav-link')) return;
            // 程序化切换（首屏、前进后退）时地址栏已经对了，这里只处理用户点击
            if (location.pathname !== pathOf(id)) {
                history.pushState({ tab: id }, '', pathOf(id));
            }
        });

        window.addEventListener('popstate', function () {
            show(tabOf(location.pathname) || DEFAULT);
        });
    }

    global.tabs = { init: init, pathOf: pathOf, tabOf: tabOf };
})(window);
