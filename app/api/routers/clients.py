"""下载器客户端接口：客户端增删改、连接测试、从下载器导入 Tracker。"""

import logging
import re
import time
from typing import Any, Dict, Optional

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.api.deps import CONFIG_PATH, DEFAULT_CLOUDFLARE_IP, get_file_config
from app.globals import get_hosts_manager, get_torrent_client_manager
from app.services.hosts_manager import HostsManager
from app.services.torrent_clients import TorrentClientManager
from app.utils import log_utils
from app.utils.file_utils import atomic_write_text

logger = logging.getLogger(__name__)

router = APIRouter()



# ===== 下载器相关API =====

# 获取下载器客户端列表
@router.get("/torrent-clients")
async def get_torrent_clients(config: Dict[str, Any] = Depends(get_file_config)):
    """获取所有下载器客户端配置"""
    try:
        clients_config = config.get("torrent_clients", [])
        # 兼容旧配置格式
        if isinstance(clients_config, dict):
            converted_clients = []
            for client_type, client_config in clients_config.items():
                converted_clients.append({
                    "id": f"{client_type}_migrated",
                    "name": f"{client_type.capitalize()} (迁移)",
                    "type": client_type,
                    **client_config
                })
            clients_config = converted_clients
        
        return {"success": True, "clients": clients_config}
    except Exception as e:
        logger.error(f"获取下载器客户端列表失败: {str(e)}")
        return {"success": False, "message": f"获取客户端列表失败: {str(e)}"}

# 保存下载器客户端配置
@router.post("/torrent-clients")
async def save_torrent_clients(
    clients_data: dict,
    config: Dict[str, Any] = Depends(get_file_config)
):
    """保存下载器客户端配置"""
    try:
        clients_config = clients_data.get("clients", [])
        
        # 验证每个客户端配置
        for client in clients_config:
            # 必填字段验证
            if not client.get("id"):
                return {"success": False, "message": "客户端ID不能为空"}
            if not client.get("name"):
                return {"success": False, "message": "客户端名称不能为空"}
            if not client.get("type") in ["qbittorrent", "transmission"]:
                return {"success": False, "message": "不支持的客户端类型"}
            if not client.get("host"):
                return {"success": False, "message": "主机地址不能为空"}
            
            # 主机地址验证
            host = client.get("host", "")
            if not re.match(r"^(?:[a-zA-Z0-9\-\.]+|\d{1,3}(?:\.\d{1,3}){3})$", host):
                return {"success": False, "message": f"客户端 {client.get('name')} 的主机地址无效"}
            
            # 端口验证
            try:
                port = int(client.get("port", 0))
                if not (1 <= port <= 65535):
                    return {"success": False, "message": f"客户端 {client.get('name')} 的端口范围无效(1-65535)"}
            except (ValueError, TypeError):
                return {"success": False, "message": f"客户端 {client.get('name')} 的端口必须为数字"}
        
        # 检查ID唯一性
        client_ids = [client.get("id") for client in clients_config]
        if len(client_ids) != len(set(client_ids)):
            return {"success": False, "message": "客户端ID不能重复"}
        
        # 更新配置
        config["torrent_clients"] = clients_config
        
        # 保存配置到文件
        atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))
        
        # 更新 TorrentClientManager
        torrent_client_manager = get_torrent_client_manager()
        torrent_client_manager.update_config(config)
        
        logger.info(f"下载器客户端配置已保存，共 {len(clients_config)} 个客户端")
        return {"success": True, "message": f"下载器配置已保存，共 {len(clients_config)} 个客户端"}
        
    except Exception as e:
        logger.error(f"保存下载器客户端配置失败: {str(e)}")
        return {"success": False, "message": f"保存配置失败: {str(e)}"}

# 测试下载器连接 - 支持通过ID或配置测试
@router.post("/test-client-connection")
async def test_client_connection(
    request: Request,
    torrent_client_manager: TorrentClientManager = Depends(get_torrent_client_manager)
):
    """测试下载器连接"""
    try:
        data = await request.json()
        client_id = data.get("client_id")
        client_config = data.get("client_config")
        
        if client_id:
            # 通过客户端ID测试已配置的客户端
            result = torrent_client_manager.test_client_connection(client_id)
        elif client_config:
            # 通过临时配置测试连接
            result = torrent_client_manager.test_client_connection_by_config(client_config)
        else:
            return {"success": False, "message": "请提供 client_id 或 client_config"}
        
        return result
        
    except Exception as e:
        logger.error(f"测试下载器连接失败: {str(e)}")
        return {"success": False, "message": f"测试连接失败: {str(e)}"}

# 兼容旧版API
@router.post("/save-clients-config")
async def save_clients_config_legacy(
    clients_config: dict,
    config: Dict[str, Any] = Depends(get_file_config)
):
    """保存下载器配置（兼容旧版API）"""
    logger.info("收到旧版本下载器配置保存请求，正在转换...")
    try:
        # 将旧格式转换为新格式
        converted_clients = []
        
        for client_type, client_config in clients_config.items():
            if client_type in ["qbittorrent", "transmission"]:
                # 生成唯一ID
                client_id = f"{client_type}_{int(time.time())}"
                converted_clients.append({
                    "id": client_id,
                    "name": f"{client_type.capitalize()} 默认",
                    "type": client_type,
                    **client_config
                })
        
        # 调用新版API
        return await save_torrent_clients(
            {"clients": converted_clients},
            config
        )
        
    except Exception as e:
        logger.error(f"保存下载器配置失败: {str(e)}")
        return {"success": False, "message": f"保存配置失败: {str(e)}"}

# 删除下载器客户端
@router.delete("/torrent-clients/{client_id}")
async def delete_torrent_client(
    client_id: str,
    config: Dict[str, Any] = Depends(get_file_config)
):
    """删除指定的下载器客户端"""
    try:
        clients_config = config.get("torrent_clients", [])
        
        # 查找并删除指定客户端
        updated_clients = [client for client in clients_config if client.get("id") != client_id]
        
        if len(updated_clients) == len(clients_config):
            return {"success": False, "message": f"未找到客户端: {client_id}"}
        
        # 更新配置
        config["torrent_clients"] = updated_clients
        
        # 保存配置到文件
        atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))
        
        # 更新 TorrentClientManager
        torrent_client_manager = get_torrent_client_manager()
        torrent_client_manager.update_config(config)
        
        logger.info(f"已删除下载器客户端: {client_id}")
        return {"success": True, "message": "客户端已删除"}
        
    except Exception as e:
        logger.error(f"删除下载器客户端失败: {str(e)}")
        return {"success": False, "message": f"删除客户端失败: {str(e)}"}

# 获取支持的客户端类型
@router.get("/torrent-client-types")
async def get_torrent_client_types():
    """获取支持的下载器客户端类型"""
    return {
        "success": True,
        "types": [
            {
                "type": "qbittorrent",
                "name": "qBittorrent",
                "default_port": 8080,
                "fields": ["host", "port", "username", "password", "api_key", "use_https"]
            },
            {
                "type": "transmission",
                "name": "Transmission",
                "default_port": 9091,
                "fields": ["host", "port", "username", "password", "use_https", "path"]
            }
        ]
    }

# 从下载器导入Tracker
@router.post("/import-trackers-from-clients")
async def import_trackers_from_clients(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager),
    config: Dict[str, Any] = Depends(get_file_config),
    client_id: Optional[str] = None
):
    """从下载器客户端导入Tracker

    client_id 为空时导入所有已启用的下载器；指定时只导入该下载器。

    整个导入过程（拉取 tracker + 逐域名 Cloudflare 检测 + 写配置）都是同步阻塞调用，
    其中每个域名的 Cloudflare 检测含 HTTP/DNS 多重超时重试，25 个域名就可能耗时 30 秒以上。
    必须整体放到线程池执行，否则会阻塞事件循环，导致前端轮询进度的 /api/config 也排队超时，
    表现为"导入完成后页面不会自动刷新"。
    """
    if client_id:
        logger.info(f"开始从下载器客户端导入Tracker（指定 client_id={client_id}）")
    else:
        logger.info("开始从下载器客户端导入Tracker（全部已启用）")

    def _do_import() -> Dict[str, Any]:
        """同步执行完整导入流程（在线程池中运行）"""
        try:
            torrent_client_manager = get_torrent_client_manager()
            result = torrent_client_manager.import_trackers_from_clients(client_id)
            logger.info(f"导入结果: {result}")

            if result.get("status") == "success" and result.get("all_domains"):
                existing_domains = {tracker['domain'] for tracker in config.get('trackers', [])}
                new_trackers_added = False
                cf_domains = []
                non_cf_domains = []

                # 临时调整日志级别为DEBUG，以便查看详细的Cloudflare检测日志
                with log_utils.temporary_log_level('app.services.hosts_manager', logging.DEBUG):
                    # 域名清洗和Cloudflare检测
                    for domain in result["all_domains"]:
                        # 清洗tracker域名，移除http前缀和路径
                        d = re.sub(r"^https?://", "", domain, flags=re.IGNORECASE)
                        d = d.split("/")[0]
                        domain = d

                        # 提取纯域名（移除端口号）用于Cloudflare检测
                        clean_domain = domain.split(':')[0] if ':' in domain else domain

                        logger.info(f"[Cloudflare检测] 正在检测下载器导入的域名: {clean_domain}")
                        # 检测Cloudflare
                        if hosts_manager.is_cloudflare_domain(clean_domain):
                            cf_domains.append(domain)
                            if domain not in existing_domains:
                                default_ip = DEFAULT_CLOUDFLARE_IP
                                new_tracker = {
                                    "name": domain,
                                    "domain": domain,
                                    "enable": True,
                                    "ip": default_ip
                                }
                                config.setdefault('trackers', []).append(new_tracker)
                                existing_domains.add(domain)
                                new_trackers_added = True
                        else:
                            logger.info(f"[Cloudflare检测] 域名 {clean_domain} 不是Cloudflare域名，已跳过")
                            non_cf_domains.append(domain)

                # 统一输出检测结果
                if cf_domains:
                    logger.info("=== Cloudflare站点检测结果 ===")
                    logger.info(f"成功检测到 {len(cf_domains)} 个Cloudflare站点:")
                    for domain in cf_domains:
                        logger.info(f"- {domain}")

                if non_cf_domains:
                    logger.info(f"检测到 {len(non_cf_domains)} 个非Cloudflare站点:")
                    for domain in non_cf_domains:
                        logger.info(f"- {domain}")

                # 只有有新的Cloudflare站点时才更新配置文件
                if new_trackers_added:
                    atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))
                    logger.info("已更新配置文件，添加了新的Tracker")
                    hosts_manager.update_config(config)
                    try:
                        import app.main
                        app.main.config = config
                        logger.info("同步刷新全局config对象，确保前端获取到最新tracker列表")
                    except Exception as e:
                        logger.error(f"刷新全局config对象失败: {str(e)}")

                    # 更新结果消息，区分加速和过滤站点
                    cf_only_message = f"成功导入 {len(cf_domains)} 个Cloudflare站点"
                    if non_cf_domains:
                        cf_only_message += f"，已过滤 {len(non_cf_domains)} 个非Cloudflare站点"
                    result["message"] = cf_only_message + "，Hosts更新任务已在后台启动"
                    result["hosts_update_needed"] = True
                else:
                    # 无新Cloudflare站点时的消息
                    if cf_domains:
                        result["message"] = f"未发现新的Cloudflare站点，已有站点 {len(cf_domains)} 个，过滤非Cloudflare站点 {len(non_cf_domains)} 个"
                    else:
                        result["message"] = f"未找到任何Cloudflare站点，已过滤非Cloudflare站点 {len(non_cf_domains)} 个"

                # 添加详细的客户端结果信息
                client_summary = []
                for _, client_result in result.get("client_results", {}).items():
                    if client_result.get("success"):
                        client_summary.append(f"{client_result['name']}: {client_result['count']}个")
                    else:
                        client_summary.append(f"{client_result['name']}: 失败({client_result.get('error', '未知错误')})")

                if client_summary:
                    result["client_summary"] = "；".join(client_summary)

            return result

        except Exception as e:
            logger.error(f"从下载器客户端导入Tracker失败: {str(e)}", exc_info=True)
            return {"status": "error", "message": f"导入过程中发生错误: {str(e)}"}

    result = await run_in_threadpool(_do_import)

    # 线程池执行完毕后，在这里触发后台 hosts 更新（BackgroundTasks 必须在事件循环内挂载）
    if result.pop("hosts_update_needed", False):
        background_tasks.add_task(hosts_manager.update_hosts)

    return result
