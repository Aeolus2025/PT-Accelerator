/**
 * 应用入口：按顺序初始化各页面模块并挂配置订阅
 */
(function (global) {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        // 主题先落地：首屏已由 head 内联脚本设好，这里补上按钮状态与系统偏好监听
        global.theme.init();

        // 再恢复上次停留的标签页，各页面模块才能收到它触发的 shown 事件
        global.tabs.init();

        // 各页面模块初始化（内部完成首屏加载与事件委托绑定）
        global.dashboardPage.init();
        global.trackersPage.init();
        global.hostsPage.init();
        global.logsPage.init();
        global.clientsPage.init();
        global.cfstPage.init();
        global.notifyPage.initNotifySettings();
        global.authPage.initAuthSettings();

        // 后台任务（hosts 更新）结束后回源一次，自动禁用这类变化不用手动刷新
        store.watchTask();

        // 配置变更后重绘依赖它的两张表
        store.subscribe(function (config) {
            global.trackersPage.renderTrackerTable(config.trackers || []);
            global.hostsPage.renderHostsSourceTable(config.hosts_sources || []);
        });
    });
})(window);
