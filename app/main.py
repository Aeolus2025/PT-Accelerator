from fastapi import FastAPI, Request, Depends, Form, status
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from pathlib import Path
import os
import copy
import logging
import platform
import time
import yaml
import uvicorn
import secrets
from contextlib import contextmanager
from typing import Optional

from starlette.middleware.sessions import SessionMiddleware

from app.services.cfst_service import CloudflareSpeedTestService
from app.services.hosts_manager import HostsManager
from app.services.scheduler import SchedulerService
from app.services.torrent_clients import TorrentClientManager
from app.models import User
from app.auth import init_session_serializer, verify_password, get_password_hash, get_current_user, create_user_session
from app.utils.file_utils import atomic_write_text
from version import get_version

# 优先确保目录存在
os.makedirs("logs", exist_ok=True)
os.makedirs("config", exist_ok=True)

# 配置日志（文件使用UTF-8编码，避免中文乱码）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/app.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# 创建必要的目录（已提前创建，保留以防未来调整调用顺序）
os.makedirs("logs", exist_ok=True)
os.makedirs("config", exist_ok=True)

# 初始化配置
CONFIG_PATH = "config/config.yaml"
DEFAULT_CLOUDFLARE_IP = "104.16.91.215"

# 预装的外部 hosts 源：全部默认关闭，用户可在 UI「Hosts源」页按需勾选启用。
HOSTS_SOURCE_PRESETS = [
    {
        "name": "GitHub（Gitlab源）",
        "url": "https://gitlab.com/ineo6/hosts/-/raw/master/next-hosts",
        "enable": False
    },
    {
        "name": "GitHub（Gitee源）",
        "url": "https://gitee.com/godfather1103/github-hosts/raw/master/hosts",
        "enable": False
    }
]

DEFAULT_CONFIG = {
    "cloudflare": {
        "enable": True,
        "cron": "0 0 * * *",  # 每天零点运行
        "ipv6": False,
        "additional_args": "",
        "notify": True
    },
    "trackers": [
        {
            "name": "示例Tracker",
            "domain": "tracker.example.com",
            "enable": True,
            "ip": DEFAULT_CLOUDFLARE_IP
        }
    ],
    # 外部 hosts 源预装但全部关闭：新部署不会生成 MergedHosts，用户需在 UI「Hosts源」页手动勾选启用。
    # 清单见下方 HOSTS_SOURCE_PRESETS（深拷贝，避免运行时改动污染常量）。
    "hosts_sources": [dict(s) for s in HOSTS_SOURCE_PRESETS],
    "torrent_clients": [
        {
            "id": "qb_default",
            "name": "qBittorrent 默认",
            "type": "qbittorrent",
            "host": "localhost",
            "port": 8080,
            "username": "",
            "password": "",
            "api_key": "",
            "use_https": False,
            "enable": False
        },
        {
            "id": "tr_default", 
            "name": "Transmission 默认",
            "type": "transmission",
            "host": "localhost",
            "port": 9091,
            "username": "",
            "password": "",
            "use_https": False,
            "path": "/transmission/rpc",
            "enable": False
        }
    ],
    "auth": {
        "enable": False,
        "username": "admin",
        "password_hash": "",
        "secret_key": ""
    }
}

# 创建nowip_hosts.txt文件，确保cfst_hosts.sh脚本能正常运行
def create_nowip_file():
    # 检查文件是否存在
    if not os.path.exists("nowip_hosts.txt"):
        try:
            with open("nowip_hosts.txt", "w") as f:
                f.write(DEFAULT_CLOUDFLARE_IP)
            logger.info(f"成功创建nowip_hosts.txt文件，内容为: {DEFAULT_CLOUDFLARE_IP}")
        except Exception as e:
            logger.error(f"创建nowip_hosts.txt文件失败: {str(e)}")

    # 同时在当前架构对应的 cfst 目录下创建一份（arm64 机器上没有 cfst_linux_amd64 目录，
    # 原先硬编码会静默跳过，导致 ARM 设备首次运行缺少该文件）
    arch_dir = "cfst_linux_arm64" if platform.machine().lower() in ("aarch64", "arm64") else "cfst_linux_amd64"
    if os.path.exists(arch_dir) and not os.path.exists(os.path.join(arch_dir, "nowip_hosts.txt")):
        try:
            with open(os.path.join(arch_dir, "nowip_hosts.txt"), "w") as f:
                f.write(DEFAULT_CLOUDFLARE_IP)
            logger.info(f"成功在{arch_dir}目录下创建nowip_hosts.txt文件")
        except Exception as e:
            logger.error(f"在{arch_dir}目录下创建nowip_hosts.txt文件失败: {str(e)}")

# 加载或创建配置文件
def load_config():
    if not os.path.exists(CONFIG_PATH):
        if not DEFAULT_CONFIG["auth"].get("secret_key"):
            DEFAULT_CONFIG["auth"]["secret_key"] = secrets.token_hex(32)
        atomic_write_text(CONFIG_PATH, yaml.dump(DEFAULT_CONFIG, default_flow_style=False, allow_unicode=True))
        # 深拷贝：运行时对 config 的修改（增删 tracker / hosts_sources 等）不能污染 DEFAULT_CONFIG
        current_config = copy.deepcopy(DEFAULT_CONFIG)
    else:
        # 读取配置：UTF-8优先，回退GBK/GB18030
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                current_config = yaml.safe_load(f)
        except UnicodeDecodeError:
            try:
                with open(CONFIG_PATH, 'r', encoding='gbk') as f:
                    current_config = yaml.safe_load(f)
            except UnicodeDecodeError:
                with open(CONFIG_PATH, 'r', encoding='gb18030') as f:
                    current_config = yaml.safe_load(f)
        
        if not current_config:
            current_config = DEFAULT_CONFIG.copy()

        need_save_after_load = False
        if "auth" not in current_config:
            current_config["auth"] = DEFAULT_CONFIG["auth"].copy()
            if not current_config["auth"].get("secret_key"):
                current_config["auth"]["secret_key"] = secrets.token_hex(32)
            need_save_after_load = True
        elif not current_config["auth"].get("secret_key"):
            current_config["auth"]["secret_key"] = secrets.token_hex(32)
            need_save_after_load = True

        for key, value in DEFAULT_CONFIG.items():
            if key not in current_config:
                current_config[key] = value
        
        if "cloudflare" in current_config:
            if "ipv4" in current_config["cloudflare"]:
                logger.info("从配置中移除废弃的ipv4字段")
                del current_config["cloudflare"]["ipv4"]
                need_save_after_load = True
        
        if need_save_after_load:
            atomic_write_text(CONFIG_PATH, yaml.dump(current_config, default_flow_style=False, allow_unicode=True))

    # 初始化认证模块的 session_serializer
    if current_config.get("auth", {}).get("secret_key"):
        init_session_serializer(current_config["auth"]["secret_key"])
    else:
        # 这是一个后备，理论上 secret_key 应该总是存在
        fallback_secret = secrets.token_hex(32)
        current_config["auth"]["secret_key"] = fallback_secret # 更新到当前配置中，以便后续保存
        init_session_serializer(fallback_secret)
        logger.warning("配置文件中未找到 secret_key，已生成临时的 secret_key。请检查配置文件。")
        # 尝试保存回文件
        try:
            atomic_write_text(CONFIG_PATH, yaml.dump(current_config, default_flow_style=False, allow_unicode=True))
            logger.info("已将生成的临时 secret_key 保存回配置文件。")
        except Exception as e:
            logger.error(f"保存临时 secret_key 到配置文件失败: {e}")
            
    return current_config

# 创建nowip_hosts.txt文件
create_nowip_file()


@contextmanager
def _config_write_lock(timeout: float = 10.0):
    """
    跨进程的配置写锁。

    用途：把「读取配置 → 判断是否需要生成 → 写回配置」这段临界区变原子。
    多 worker 下每个进程都会执行 startup_event，若无此锁：
      worker A 读到 password_hash 为空 → 生成密码 P1
      worker B 也读到为空 → 生成密码 P2
      A 写文件(P1) → B 写文件(P2)
    最终生效的是 P2，但 A 的控制台/日志里打印的是 P1，用户拿着 P1 永远登不上。

    实现：POSIX 文件锁（fcntl.flock，独占）。锁文件放在 config/ 下，
    不随 CONFIG_PATH 的原子替换而消失（替换的是目标文件，不是锁文件）。
    非 POSIX 平台（Windows 开发环境）自动降级为无锁，不影响单 worker 使用。
    """
    lock_path = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)), ".config.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)

    try:
        import fcntl
    except ImportError:  # 非 POSIX，直接放行
        yield
        return

    lock_file = open(lock_path, "a+")
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    # 超时后退化为无锁继续执行，避免整个进程卡死在启动阶段
                    logger.warning(f"获取配置写锁超时({timeout}s)，继续执行（可能存在并发写风险）")
                    break
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        lock_file.close()


# 服务初始化
config = load_config()
# 创建应用
app = FastAPI(title="PT-Accelerator")

# 添加 SessionMiddleware, secret_key 从配置中读取
# 确保在所有路由之前添加中间件
if config.get("auth", {}).get("secret_key"):
    app.add_middleware(SessionMiddleware, secret_key=config["auth"]["secret_key"])
else:
    # 如果到这里 secret_key 仍然没有，这是个严重问题，但为了应用能启动，用一个固定值（不推荐生产环境）
    logger.error("CRITICAL: Secret key for session middleware is not set. Using a temporary insecure key.")
    app.add_middleware(SessionMiddleware, secret_key="temporary_insecure_secret_key_please_change")

# 挂载静态文件
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

# 模板
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
# 将版本号注入 Jinja2 全局，供静态资源版本查询串（?v={{ app_version }}）使用，
# 避免每次都靠 TemplateResponse 的 context 传递（login.html 有多处渲染点）。
templates.env.globals["app_version"] = get_version()
hosts_manager = HostsManager(config)
cloudflare_service = CloudflareSpeedTestService(config, hosts_manager)
scheduler_service = SchedulerService(config, cloudflare_service, hosts_manager)
torrent_client_manager = TorrentClientManager(config)

# 初始化全局服务实例
from app.globals import init_services
init_services(hosts_manager, cloudflare_service, scheduler_service, torrent_client_manager, config)

# 注册路由 - 在服务初始化之后导入
from app.api.routers import config as config_router
from app.api.routers import auth as auth_router
from app.api.routers import tasks as tasks_router
from app.api.routers import sites as sites_router
from app.api.routers import clients as clients_router
from app.api.routers import notify as notify_router
from app.api.routers import logs as logs_router

app.include_router(config_router.router, prefix="/api", tags=["config"])
app.include_router(auth_router.router, prefix="/api", tags=["auth"])
app.include_router(tasks_router.router, prefix="/api", tags=["tasks"])
app.include_router(sites_router.router, prefix="/api", tags=["sites"])
app.include_router(clients_router.router, prefix="/api", tags=["clients"])
app.include_router(notify_router.router, prefix="/api", tags=["notify"])
app.include_router(logs_router.router, prefix="/api", tags=["logs"])

# 提供 favicon.ico 文件
@app.get("/favicon.ico")
async def favicon():
    favicon_path = Path(__file__).parent / "templates" / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/x-icon")
    else:
        from fastapi.responses import Response
        return Response(status_code=204)  # 如果文件不存在，返回 204 No Content

# 认证相关函数已移动到 app.auth 模块

# 登录页面
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error_message: Optional[str] = None):
    csrf_token = secrets.token_hex(32)
    request.session["csrf_token"] = csrf_token
    return templates.TemplateResponse("login.html", {"request": request, "error_message": error_message, "csrf_token": csrf_token})


# 登录处理
@app.post("/login")
async def login_for_access_token(
    request: Request,
    username: str = Form(...), 
    password: str = Form(...),
    csrf_token: str = Form(...) # 从表单接收 CSRF token
):
    # 实时读取最新配置，确保使用最新的认证信息
    from app.auth import load_current_config
    current_config = load_current_config()

    # CSRF Token 验证
    session_csrf_token = request.session.pop("csrf_token", None) # 从 session 中获取并移除
    if not session_csrf_token or session_csrf_token != csrf_token:
        # 生成新的 CSRF token
        new_csrf_token = secrets.token_hex(32)
        request.session["csrf_token"] = new_csrf_token
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "error_message": "无效的请求，请刷新页面重试。",
            "csrf_token": new_csrf_token
        })

    auth_config = current_config.get("auth", {})
    stored_username = auth_config.get("username")
    stored_password_hash = auth_config.get("password_hash")

    if not stored_password_hash: # 初始密码未设置
        # 生成新的 CSRF token
        new_csrf_token = secrets.token_hex(32)
        request.session["csrf_token"] = new_csrf_token
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "error_message": "管理员密码尚未设置。请查看应用日志（logs/app.log）中的初始密码；若日志中也没有，重启容器后会重新生成。",
            "csrf_token": new_csrf_token
        })

    if username == stored_username and verify_password(password, stored_password_hash):
        request.session.clear() # 登录成功，先清除当前会话数据
        user_session_data = create_user_session(username)
        request.session["user"] = user_session_data
        # 登录成功后重定向到主页
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        return response
    
    # 登录失败时生成新的 CSRF token
    new_csrf_token = secrets.token_hex(32)
    request.session["csrf_token"] = new_csrf_token
    return templates.TemplateResponse("login.html", {
        "request": request, 
        "error_message": "用户名或密码错误",
        "csrf_token": new_csrf_token
    })

# 登出
@app.get("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return response

# 主页
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, current_user: Optional[User] = Depends(get_current_user)):
    # 实时读取最新配置，而不是使用全局变量
    from app.auth import load_current_config
    current_config = load_current_config()
    
    if current_config.get("auth", {}).get("enable") and not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    # 如果认证未启用，或者用户已登录，则显示主页
    # 确保传递最新的 config 到模板
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "config": current_config, "current_user": current_user, "version": get_version()}
    )

# 运行时更新配置
@app.on_event("startup")
async def startup_event():
    global config # 确保访问的是最新的 config
    # 启动调度器
    scheduler_service.start()
    logger.info("应用已启动，调度器已开始运行")

    # 生成 secret_key / 初始密码这类「读-判断-写」操作必须跨进程互斥。
    # 单 worker 时不会有问题，但 `uvicorn --workers N` 下每个 worker 都会跑一次
    # startup_event，各自生成不同的密码并写文件 -> 互相覆盖，用户从日志里拿到的
    # 可能是一个已经被覆盖掉的密码。这里用文件锁保证同一时刻只有一个 worker 在做。
    with _config_write_lock():
        current_config = load_config()  # 重新加载最新配置
        auth_config = current_config.get("auth", {})
        config_updated = False

        # 确保有secret_key
        if not auth_config.get("secret_key"):
            auth_config["secret_key"] = secrets.token_hex(32)
            current_config["auth"] = auth_config
            config_updated = True
            logger.info("已生成新的认证密钥")

        # 检查管理员密码是否设置 - 改进逻辑
        if auth_config.get("enable") and (not auth_config.get("password_hash") or auth_config.get("password_hash") == ""):
            new_password = secrets.token_urlsafe(12) # 生成一个随机密码
            hashed_password = get_password_hash(new_password)

            # 更新配置
            auth_config["password_hash"] = hashed_password
            current_config["auth"] = auth_config
            config_updated = True

            # 多次输出确保能看到
            print("=" * 60)
            print(f"重要：管理员密码已自动生成")
            print(f"用户名: {auth_config['username']}")
            print(f"密码: {new_password}")
            print("请妥善保存此密码，登录后请立即修改")
            print("=" * 60)

            logger.warning("=" * 60)
            logger.warning(f"管理员密码尚未设置。已自动生成初始密码: {new_password}")
            logger.warning("请使用此密码登录后，在控制面板中修改密码。")
            logger.warning(f"用户名: {auth_config['username']}")
            logger.warning("=" * 60)

        # 如果配置有更新，保存到文件并更新全局配置
        if config_updated:
            try:
                atomic_write_text(CONFIG_PATH, yaml.dump(current_config, default_flow_style=False, allow_unicode=True))
                # 更新全局配置
                config.update(current_config)
                logger.info("认证配置已更新并保存")
            except Exception as e:
                logger.error(f"保存认证配置失败: {e}")



# 关闭时停止调度器
@app.on_event("shutdown")
async def shutdown_event():
    scheduler_service.stop()
    logger.info("应用已关闭，调度器已停止")

if __name__ == "__main__":
    # 从环境变量中获取端口，如果未设置，则默认为23333
    # 注意：os.environ.get 返回字符串，需要转换为整数
    app_port = int(os.environ.get("APP_PORT", "23333"))
    uvicorn.run("main:app", host="0.0.0.0", port=app_port, reload=True)