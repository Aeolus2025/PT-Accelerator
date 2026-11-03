/**
 * 主题切换：浅色 / 深色 / 跟随系统
 *
 * 首屏主题由 index.html、login.html 的 <head> 内联脚本设置（必须在样式表之前，
 * 否则会先按浅色渲染再变深，出现闪白）。本文件负责后续的切换、持久化与系统偏好监听。
 */
(function (global) {
    'use strict';

    var STORAGE_KEY = 'pta-theme';
    var MODES = ['light', 'dark', 'auto'];
    var LABELS = { light: '浅色', dark: '深色', auto: '跟随系统' };
    var ICONS = { light: 'bi-sun', dark: 'bi-moon-stars', auto: 'bi-circle-half' };

    var media = global.matchMedia ? global.matchMedia('(prefers-color-scheme: dark)') : null;

    function readMode() {
        try {
            var saved = global.localStorage.getItem(STORAGE_KEY);
            return MODES.indexOf(saved) >= 0 ? saved : 'auto';
        } catch (e) {
            // 隐私模式或禁用存储时 localStorage 会抛异常，退回跟随系统
            return 'auto';
        }
    }

    function writeMode(mode) {
        try {
            global.localStorage.setItem(STORAGE_KEY, mode);
        } catch (e) {
            // 存不下就只在本次会话生效，不影响切换本身
        }
    }

    function resolve(mode) {
        if (mode === 'auto') {
            return media && media.matches ? 'dark' : 'light';
        }
        return mode;
    }

    function paintPicker(mode) {
        var icon = document.getElementById('theme-picker-icon');
        var label = document.getElementById('theme-picker-label');
        if (icon) icon.className = 'bi ' + ICONS[mode];
        if (label) label.textContent = LABELS[mode];
    }

    function markActive(mode) {
        var items = document.querySelectorAll('.theme-option[data-theme-mode]');
        for (var i = 0; i < items.length; i++) {
            items[i].classList.toggle('active', items[i].getAttribute('data-theme-mode') === mode);
        }
    }

    function apply(mode, persist) {
        if (MODES.indexOf(mode) < 0) mode = 'auto';
        var root = document.documentElement;
        root.setAttribute('data-bs-theme', resolve(mode));
        root.setAttribute('data-theme-mode', mode);
        if (persist) writeMode(mode);
        paintPicker(mode);
        markActive(mode);
    }

    function init() {
        apply(readMode(), false);

        document.addEventListener('click', function (event) {
            var item = event.target.closest('.theme-option[data-theme-mode]');
            if (!item) return;
            apply(item.getAttribute('data-theme-mode'), true);
        });

        if (media) {
            var onChange = function () {
                // 只有「跟随系统」需要在系统明暗切换时实时重绘
                if (readMode() === 'auto') apply('auto', false);
            };
            if (media.addEventListener) media.addEventListener('change', onChange);
            else if (media.addListener) media.addListener(onChange);
        }
    }

    global.theme = {
        init: init,
        apply: apply,
        current: readMode,
        resolved: function () { return resolve(readMode()); }
    };
})(window);
