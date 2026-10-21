/**
 * 应用入口：按顺序初始化各页面模块并挂配置订阅
 */
(function (global) {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        // 各页面模块初始化（内部完成首屏加载与事件委托绑定）
        global.dashboardPage.init();
        global.trackersPage.init();
        global.hostsPage.init();
        global.clientsPage.init();
        global.notifyPage.initNotifySettings();
        global.authPage.initAuthSettings();

        // 配置变更后重绘依赖它的两张表
        store.subscribe(function (config) {
            global.trackersPage.renderTrackerTable(config.trackers || []);
            global.hostsPage.renderHostsSourceTable(config.hosts_sources || []);
        });
    });
})(window);
