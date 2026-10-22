"""路由汇总入口。

各业务路由按职责拆分在 app/api/routers/ 下：
  config.py   配置读写
  auth.py     认证配置
  logs.py     日志查看与清空
  tasks.py    任务触发、调度器与任务状态
  sites.py    Cloudflare 白名单、Tracker、hosts 源、hosts 更新与清空重建
  clients.py  下载器客户端、从下载器导入 Tracker
  notify.py   通知渠道配置、测试发送、模板预览

本文件只保留一个空 router，供 app/main.py 统一注册。
"""

from fastapi import APIRouter

router = APIRouter()
