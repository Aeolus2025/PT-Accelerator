import logging
from typing import Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.tasks import registry as task_registry
from app.services.cfst import CloudflareSpeedTestService
from app.services.hosts_manager import HostsManager

logger = logging.getLogger(__name__)

# 定时任务在 registry 中的登记名
TASK_NAME = "scheduler"

class SchedulerService:
    """调度器服务，用于定时执行任务"""
    
    def __init__(self, config: Dict[str, Any], cloudflare_service: CloudflareSpeedTestService, hosts_manager: HostsManager):
        self.config = config
        self.cloudflare_service = cloudflare_service
        self.hosts_manager = hosts_manager
        self.scheduler = None  # 初始化为None，在start时创建
        self._create_scheduler()  # 创建新的调度器
        # 任务状态统一记在 core.tasks 的 registry 里
    
    def _create_scheduler(self):
        """创建一个新的调度器实例"""
        # 防止残留
        if self.scheduler is not None:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                pass
            self.scheduler = None
        # 配置调度器，设置作业执行器选项
        self.scheduler = BackgroundScheduler(
            job_defaults={
                'max_instances': 1,  # 默认最大实例数为1
                'coalesce': True,  # 合并延迟的任务
                'misfire_grace_time': 300  # 错过执行时间后5分钟内仍可执行
            }
        )
        self._setup_jobs()
        logger.debug("[TASK] 已创建新的调度器实例")
    
    def update_config(self, config: Dict[str, Any]):
        """更新配置；定时任务未变化时不碰调度器。

        就地重建任务而不是 shutdown 重建调度器，避免打断正在执行的任务。
        """
        old_cf = (self.config or {}).get("cloudflare", {})
        new_cf = (config or {}).get("cloudflare", {})
        self.config = config

        # 只关心影响任务的字段：执行时间与是否启用
        if old_cf.get("cron") == new_cf.get("cron") and old_cf.get("enable") == new_cf.get("enable"):
            return

        if not self.scheduler:
            logger.info("[TASK] 调度器尚未创建，新配置将在启动时生效 结果=失败")
            return

        logger.info("[TASK] 定时任务配置已变更，重建任务")
        self._setup_jobs()
    
    def _setup_jobs(self):
        """设置定时任务"""
        if not self.scheduler:
            logger.error("[TASK] 调度器实例不存在，无法设置任务")
            return
            
        # 清除现有的所有任务
        if self.scheduler.running:
            logger.debug("[TASK] 清除现有的所有定时任务")
            self.scheduler.remove_all_jobs()
        else:
            logger.debug("[TASK] 调度器未运行，不需要清除任务")
        
        # 添加合并后的定时任务（IP优选+更新hosts）
        cloudflare_config = self.config.get("cloudflare", {})
        if cloudflare_config.get("enable", True):
            cron_expr = cloudflare_config.get("cron", "0 0 * * *")  # 默认每天0点执行
            logger.debug("[TASK] 准备添加定时任务 定时=%s", cron_expr)
            
            try:
                # 创建一个组合任务函数
                def combined_task():
                    import time
                    task_start_time = time.time()
                    # 更新任务状态
                    task_registry.start(TASK_NAME, "正在执行定时IP优选任务")
                    try:
                        ok = self.hosts_manager.run_cfst_and_update_hosts()
                        status = self.hosts_manager.get_task_status()
                        msg = status.get('message') if isinstance(status, dict) else ("定时IP优选任务完成" if ok else "定时IP优选任务失败")
                        task_registry.finish(TASK_NAME, msg)
                        task_duration = time.time() - task_start_time
                        logger.info("[TASK] 定时任务完成 任务=IP优选与Hosts更新 结果=成功 耗时=%sms", int(task_duration * 1000))
                        
                        # 发送定时任务完成通知
                        try:
                            from app.services.task_notify import send_task_notify
                            logger.debug("[TASK] 定时任务通知 说明=%s", msg)
                            send_task_notify("IP优选与Hosts更新", msg)
                        except Exception as notify_e:
                            logger.exception("[TASK] 发送定时任务通知失败: %s", str(notify_e))
                    except Exception as e:
                        error_msg = f"定时任务失败: {str(e)}"
                        task_registry.finish(TASK_NAME, error_msg)
                        task_duration = time.time() - task_start_time
                        logger.error("[TASK] 定时任务完成 任务=IP优选与Hosts更新 结果=失败 耗时=%sms 错误=%s", int(task_duration * 1000), error_msg, exc_info=True)
                        
                        # 发送定时任务失败通知
                        try:
                            from app.services.task_notify import send_task_notify
                            logger.warning("[TASK] 定时任务通知 结果=失败 说明=%s", error_msg)
                            send_task_notify("IP优选与Hosts更新", error_msg)
                        except Exception as notify_e:
                            logger.exception("[TASK] 发送定时任务失败通知失败: %s", str(notify_e))
                
                self.scheduler.add_job(
                    combined_task,
                    CronTrigger.from_crontab(cron_expr),
                    id="combined_cloudflare_and_hosts_task",
                    name="IP优选与Hosts更新定时任务",
                    max_instances=1,  # 确保同一时间只有一个实例运行
                    coalesce=True,  # 如果任务被延迟，合并执行
                    misfire_grace_time=300  # 如果错过执行时间，5分钟内仍可执行
                )
                logger.info('[TASK] 已添加定时任务 定时="%s" 任务=IP优选与Hosts更新', cron_expr)
            except Exception as e:
                logger.exception("[TASK] 添加组合定时任务失败: %s", str(e))
        else:
            logger.info("[TASK] 定时任务未添加 原因=定时任务已关闭")
    
    def start(self):
        """启动调度器"""
        if self.scheduler is None:
            self._create_scheduler()
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("[TASK] 调度器已启动")
    
    def stop(self):
        """停止调度器"""
        if self.scheduler:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            self.scheduler = None
            logger.info("[TASK] 调度器已停止并清除")
    
    def is_running(self) -> bool:
        """检查调度器是否运行中"""
        return self.scheduler is not None and self.scheduler.running
    
    def get_jobs(self) -> list:
        """获取所有定时任务"""
        jobs = []
        if self.scheduler:
            for job in self.scheduler.get_jobs():
                next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "未安排"
                jobs.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run": next_run
                })
        return jobs
        
    def get_task_status(self):
        """获取当前任务状态（读统一的 task registry）"""
        return task_registry.get(TASK_NAME)