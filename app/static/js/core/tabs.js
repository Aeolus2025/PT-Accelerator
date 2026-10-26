/**
 * 主标签页位置记忆：刷新后回到原来那页。
 *
 * 用 sessionStorage 而不是 localStorage：新开一个标签页仍从控制面板开始，
 * 只有同一标签页内的刷新、跳转才延续上次位置。
 */
(function (global) {
    'use strict';

    var KEY = 'pta.activeTab';
    var DEFAULT = 'dashboard-tab';

    function valid(id) {
        var btn = id && document.getElementById(id);
        return !!(btn && btn.classList.contains('nav-link'));
    }

    function save(id) {
        if (!valid(id)) return;
        try {
            sessionStorage.setItem(KEY, id);
        } catch (e) {
            // 隐私模式下 sessionStorage 可能不可写，静默跳过
        }
    }

    function restore() {
        var id = null;
        try {
            id = sessionStorage.getItem(KEY);
        } catch (e) {
            return;
        }
        if (!id || !valid(id) || id === DEFAULT) return;

        // Bootstrap 的 Tab 实例负责显示面板并派发 shown.bs.tab
        var instance = global.bootstrap && global.bootstrap.Tab.getOrCreateInstance(
            document.getElementById(id)
        );
        if (instance) instance.show();
    }

    // 必须在各页面模块 init 之前调用，否则切页的 shown 事件没人接
    function init() {
        restore();
        document.addEventListener('shown.bs.tab', function (event) {
            if (event.target && event.target.classList.contains('nav-link')) {
                save(event.target.id);
            }
        });
    }

    global.tabs = { init: init };
})(window);
