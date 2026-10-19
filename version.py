"""
PT-Accelerator 版本信息
"""

__version__ = "2.1.0"
__version_info__ = (2, 1, 0)
__author__ = "PT-Accelerator Team"
__description__ = "一个面向PT站点用户的全自动加速与管理平台"

# 版本历史
# 注意：自 2.1.0 起本 fork 独立演进，版本号不再与上游对齐。
VERSION_HISTORY = {
    "2.1.0": "2026-10-19 - 修复关闭Hosts源后仍生成/残留MergedHosts段；Hosts源改为精简预装并默认关闭；恢复/安全加固配置默认值隔离；新增qBittorrent 5.2+ API Key认证支持；cfst升级至v2.3.5",
    "2.0.5": "2025-11-17 - 修复企业微信App加载渠道配置编辑失败问题，新增转发代理配置",
    "2.0.4": "2025-11-16 - 修复定时任务跳过执行问题、修复多通知渠道重复发送问题",
    "2.0.3": "2025-10-12 - 修复通知渠道关闭状态问题",
    "2.0.2": "2025-10-11 - 添加Media Saber通知渠道",
    "2.0.1": "2025-10-11 - 修复自定义通知配置问题",
    "2.0.0": "2025-09-25 - 架构自适应支持、多通知渠道、移动端适配、Hosts结构保护",
    "1.0.0": "2025-04-29 - 初始版本发布"
}

def get_version():
    """获取当前版本号"""
    return __version__

def get_version_info():
    """获取版本信息元组"""
    return __version_info__

def get_version_history():
    """获取版本历史"""
    return VERSION_HISTORY
