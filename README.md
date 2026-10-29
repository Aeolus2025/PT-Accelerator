# PT-Accelerator v2.1.0

一个面向PT站点用户的全自动加速与管理平台，集成Cloudflare IP优选、PT Tracker批量管理、GitHub/TMDB等站点加速、下载器一键导入、Web可视化配置等多种功能，支持Docker一键部署，适合所有对网络加速和PT站点体验有高要求的用户。

---

## 功能亮点

- **Cloudflare IP优选**：集成CloudflareSpeedTest，自动定时优选全球最快Cloudflare IP，极大提升PT站点和GitHub等访问速度。
- **架构自适应支持**：完美支持AMD64和ARM64架构，自动检测并选择对应的CloudflareSpeedTest可执行文件和配置文件。
- **PT Tracker批量管理**：支持批量添加、批量清空、批量导入、单个删除、状态切换等操作，Tracker管理极致高效。
- **下载器一键导入**：支持qBittorrent、Transmission等主流下载器，自动导入Tracker列表并智能筛选Cloudflare站点。
- **Hosts源多路合并**：内置多条GitHub/TMDB等Hosts源，自动合并、去重、优选，提升全局访问体验。
- **Web可视化配置**：所有操作均可在现代化Web界面完成，支持定时任务、白名单、日志、配置等全方位管理。
- **用户登录认证**：内置用户登录与鉴权机制，保障平台访问安全。
- **多下载器实例支持**：支持同时连接和管理多个qBittorrent及Transmission下载器实例，集中控制更便捷。
- **一键清空/重建**：支持一键清空所有Tracker、清空并重建hosts文件，彻底解决历史污染和遗留问题。
- **日志与状态监控**：内置系统日志、任务进度、调度器状态等实时监控，方便排查和优化。
- **多架构Docker镜像**：提供AMD64和ARM64架构的Docker镜像，支持树莓派、ARM服务器等设备。
- **CI/CD自动化**：集成GitHub Actions，支持自动构建和手动自定义版本发布。
- **多通知渠道**：支持多种通知方式，及时获取系统状态和任务完成通知。
- **Hosts文件编辑**：支持在线编辑Hosts文件，实时预览和保存修改。
- **日志管理**：支持清空日志功能，保持系统日志整洁。
- **移动端适配**：完美适配移动端显示，支持手机和平板设备访问。
- **Hosts结构保护**：修复清空Hosts功能，保护系统原有Hosts文件头结构。
- **极致兼容性**：支持Docker、原生Python环境，支持Linux/Windows/Mac，适配多种部署场景。

---

## 关于本项目（fork 说明）

本仓库是 [`eternalcurse/PT-Accelerator`](https://github.com/eternalcurse/PT-Accelerator) 的维护分支，已合并 [`KoWming/PT-Accelerator`](https://github.com/KoWming/PT-Accelerator) 的改进，并由本仓库继续维护、构建和发布镜像。

**镜像**：`ghcr.io/aeolus2025/pt-accelerator`

| 标签 | 说明 |
| --- | --- |
| `latest` | 最新正式版，**只在推送 `vX.Y.Z` tag 时更新**，`main` 分支上的提交不会改变它 |
| `vX.Y.Z` | 对应 `version.py` 的版本号，推送同名 tag 时自动生成 |

每个镜像都是 `linux/amd64` 与 `linux/arm64` 的多架构清单，Docker 会自动选择对应架构，不需要单独的架构标签。

**与上游的差异**：

- **前端依赖本地化**：bootstrap / bootstrap-icons / jquery 全部内置在 `app/static/`，不再依赖 `cdn.jsdelivr.net`（内网或 CDN 不可达时页面样式与交互仍正常）
- **多架构支持**：`cfst_linux_amd64/` 与 `cfst_linux_arm64/` 双架构二进制，`Dockerfile` 按 `TARGETARCH` 自动选取
- **CI 推送到 GHCR**：使用 `GITHUB_TOKEN`，无需自建 secret；`main` 分支 push 只做构建检查不推送，`tag` 推送更新版本号标签与 `latest`，手动触发只推送指定的标签
- **qBittorrent 5.2+ 支持**：新增 WebUI API 密钥认证（`Authorization: Bearer`），优先于用户名/密码；5.2 以下版本账号密码登录行为不变
- **外部 hosts 源默认关闭**：自 `2.1.0` 起预装 2 条源且默认不启用，新部署不再自动生成 `MergedHosts`；**已有配置不受影响**，如需相同行为请在「Hosts源」页取消勾选或删除
- **登录认证首次启用即生效**：开启后当场生成初始密码并打印到日志，无需重启容器

> 从上游镜像迁移到本镜像时，`./config`、`./logs` 目录可直接复用，无需重建数据。

### 镜像发布流程

工作流 [`.github/workflows/Releases.yml`](.github/workflows/Releases.yml) 按触发方式决定构建什么、推送什么：

| 触发方式 | 构建架构 | 推送的镜像 | 影响 `latest` |
| --- | --- | --- | --- |
| 推送到 `main` | `amd64` + `arm64` | 无（只做构建检查） | ❌ |
| 推送 `vX.Y.Z` tag | `amd64` + `arm64` | `vX.Y.Z` 与 `latest` | ✅ |
| 手动触发，填写 `version` | `amd64` + `arm64` | 仅填写的标签 | ❌ |
| 手动触发，`version` 留空 | `amd64` + `arm64` | 无（只做构建检查） | ❌ |

发版步骤：

1. 修改 `version.py` 中的 `__version__`，提交到 `main`
2. 打同名 tag 并推送：`git tag v2.2.0 && git push origin v2.2.0`
3. 工作流会先校验 tag 名与 `version.py` 是否一致，不一致直接失败，避免把错误的版本号推到 GHCR
4. 构建成功后 `ghcr.io/aeolus2025/pt-accelerator` 下会同时出现 `v2.2.0` 与 `latest`

> `latest` 的更新路径只有 tag 推送这一条，因此发版前的任何提交都不会影响已发布镜像。

---

## 快速开始

### 1. Docker一键部署

推荐使用Docker，简单高效，支持多架构：

```bash
# 自动选择架构（推荐）
docker run -d \
  --name pt-accelerator \
  --network host \
  -v /etc/hosts:/etc/hosts \
  -v /path/to/config:/app/config \
  -v /path/to/logs:/app/logs \
  -e TZ=Asia/Shanghai \
  -e APP_PORT=23333 \
  ghcr.io/aeolus2025/pt-accelerator:latest

# 锁定到具体版本（升级时不跟随 latest，便于排查与回滚）
docker run -d \
  --name pt-accelerator \
  --network host \
  -v /etc/hosts:/etc/hosts \
  -v /path/to/config:/app/config \
  -v /path/to/logs:/app/logs \
  -e TZ=Asia/Shanghai \
  -e APP_PORT=23333 \
  ghcr.io/aeolus2025/pt-accelerator:v2.2.0
```

或使用`docker-compose.yml`：

```yaml
services:
  pt-accelerator:
    image: ghcr.io/aeolus2025/pt-accelerator:latest
    container_name: pt-accelerator
    restart: unless-stopped
    network_mode: host
    environment:
      TZ: "${TZ:-Asia/Shanghai}"
      APP_PORT: "${APP_PORT:-23333}"
    volumes:
      - /etc/hosts:/etc/hosts
      - ./config:/app/config
      - ./logs:/app/logs
```

如需自定义时区或端口，可复制 `.env.example` 为 `.env` 后修改对应变量。

创建上述`docker-compose.yml`文件后，在同一目录下运行：

```bash
docker-compose up -d
```

### 2. 本地运行（开发/调试）

```bash
# 克隆仓库
git clone https://github.com/Aeolus2025/PT-Accelerator.git
cd PT-Accelerator

# 安装依赖
pip install -r requirements.txt

# 启动服务
bash start.sh
# 自定义端口启动
APP_PORT=8080 bash start.sh
# 或
python -m uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-23333}
```
---

## Web界面入口

- 访问：http://your-ip:<端口号>
- 首次访问或根据配置，可能需要进行用户登录。
- 默认端口：`23333`。可以通过以下方式修改：
  - **Docker/Docker Compose**:
    - 在 `docker-compose.yml` 文件中，为 `pt-accelerator` 服务的 `environment` 部分添加或修改 `APP_PORT` 的值。例如:
      ```yaml
      services:
        pt-accelerator:
          # ... other settings ...
          environment:
            - TZ=Asia/Shanghai
            - APP_PORT=8080 # 设置自定义端口
      ```
    - 或者，在 `docker-compose.yml` 同级目录下创建 `.env` 文件并写入 `APP_PORT=8080`，这会覆盖 `docker-compose.yml` 中的默认设置（如果存在）。
  - **本地运行**: 启动前设置 `APP_PORT` 环境变量 (例如 `export APP_PORT=8080 && bash start.sh`)，或者直接修改 `start.sh` 脚本中的默认端口。
- 支持多用户同时操作，所有配置实时生效

---

## 主要功能模块

### 1. 控制面板
- 查看调度器状态、定时任务、快速运行IP优选与Hosts更新
- 一键仅更新Hosts
- 一键清空Hosts并重建（彻底清理历史污染，保护系统原有结构）
- 监控IP优选和Hosts更新任务进度
- 支持移动端响应式显示，完美适配手机和平板设备

### 2. Tracker管理
- 批量添加、批量清空、单个删除、状态切换
- 一键导入下载器Tracker（自动筛选Cloudflare站点）
- 支持Cloudflare白名单管理
- Tracker IP一键批量更新
- 支持大量PT站点Tracker自动配置

### 3. Hosts源管理
- 支持多条外部Hosts源，自动合并、去重、优选
- 支持添加、删除、启用/禁用Hosts源
- 内置多个优质Hosts源（GitHub和TMDB加速）
- 自动定时更新所有Hosts源

### 4. 下载器管理
- 支持添加和管理**多个**qBittorrent、Transmission等主流下载器实例，每个实例均可独立配置。
- 一键测试连接、保存配置、导入Tracker
- 支持端口、用户名密码、HTTPS等完整配置
- 自动验证连接有效性

### 5. 日志与监控
- 面板显示与 `logs/app.log` 完全一致的原文，格式统一为 `[时间] - [级别] - 消息`
- 记录级别下拉框（DEBUG/INFO/WARNING/ERROR，默认 INFO），改完立即生效并写入配置
- 级别筛选（全部/DEBUG/INFO/WARNING/ERROR）与关键词搜索
- 支持刷新、自动滚动、一键清空

### 6. Hosts文件管理
- 支持在线编辑Hosts文件，实时预览修改效果
- 保护系统原有Hosts文件头结构，避免破坏系统配置
- 智能合并多个Hosts源，自动去重和优化

### 7. 通知系统
- 支持多种通知渠道，及时获取系统状态
- 任务完成通知、错误告警通知
- 可选配置通知方式

---

## 配置文件说明（config/config.yaml）

- `auth`：用户认证配置 (新增)
  - `enable`：是否启用用户认证 (例如 `true` 或 `false`)
  - `username`：登录用户名
  - `password`：登录密码 (建议存储哈希后的密码，具体请参照您的实现方式)

- `cloudflare`：Cloudflare优选相关配置
  - `enable`：是否启用Cloudflare IP优选
  - `cron`：定时任务Cron表达式（默认每天0点）
  - `ipv6`：是否启用IPv6测速
  - `additional_args`：CloudflareST额外参数
  - `notify`：是否开启通知
  
- `cloudflare_domains`：Cloudflare白名单域名列表（需要优化的域名）

- `hosts_sources`：外部Hosts源列表
  - `name`：源名称
  - `url`：源URL地址
  - `enable`：是否启用

- `torrent_clients`：下载器配置列表 (支持多个实例)
  - 每个下载器实例为一个列表项，包含以下字段：
    - `name`: (必填) 用户为此下载器实例设定的唯一名称 (例如 `qb-main`, `tr-backup`)
    - `type`: (必填) 下载器类型，可选值为 `qbittorrent` 或 `transmission`
    - `host`：下载器主机地址
    - `port`：下载器端口
    - `username`/`password`：登录凭据
    - `use_https`：是否使用HTTPS (例如 `true` 或 `false`)
    - `enable`：是否启用此下载器实例 (例如 `true` 或 `false`)
  - 示例:
    ```yaml
    torrent_clients:
      - name: qBittorrent主服务器
        type: qbittorrent
        host: localhost
        port: 8080
        username: admin
        password: adminadmin
        use_https: false
        enable: true
      - name: Transmission备用
        type: transmission
        host: 192.168.1.100
        port: 9091
        username: 
        password: 
        use_https: false
        enable: true
    ```

- `trackers`：PT站点Tracker列表
  - `name`：Tracker名称
  - `domain`：Tracker域名
  - `ip`：优选的IP地址
  - `enable`：是否启用

**所有配置均可通过Web界面实时修改，无需手动编辑。**

---

## CloudflareSpeedTest说明

- 已内置CloudflareST二进制和测速脚本，自动调用，无需手动操作
- **架构自适应**：自动检测系统架构（AMD64/ARM64），选择对应的可执行文件和配置文件
- 相关参数和测速数据文件（ip.txt/ipv6.txt）可在对应架构目录下自定义：
  - AMD64架构：`cfst_linux_amd64/` 目录
  - ARM64架构：`cfst_linux_arm64/` 目录
- 自动筛选延迟低、速度快的优质CF节点IP
- 支持IPv4/IPv6双协议测速
- Docker构建时自动排除不需要的架构文件，优化镜像大小
- 参考：https://github.com/XIU2/CloudflareSpeedTest

---

## 常见问题

- **Q: 为什么要挂载/etc/hosts？**  
  A: 程序会自动优化和重写系统hosts文件，提升全局访问速度，必须有写入权限。

- **Q: 如何彻底清空tracker或hosts？**  
  A: Web界面提供"一键清空所有tracker""清空hosts并重建"按钮，安全高效。

- **Q: 支持哪些PT站点？**  
  A: 支持所有基于Cloudflare的PT站点，非Cloudflare站点会自动过滤。

- **Q: 日志和配置如何持久化？**  
  A: 建议挂载`/app/config`和`/app/logs`到本地目录，防止容器重启丢失数据。

- **Q: 如果系统使用了代理，会影响IP测速吗？**  
  A: 会影响。建议在测速时临时关闭系统代理，确保获得准确的测速结果。

- **Q: 项目如何更新？**  
  A: 使用Docker部署的用户可以通过`docker pull ghcr.io/aeolus2025/pt-accelerator:latest`拉取最新镜像，再重新创建容器。

- **Q: 支持哪些架构？**  
  A: 支持AMD64和ARM64架构，包括x86_64服务器、树莓派、ARM服务器等。Docker会自动选择对应架构的镜像。

- **Q: 如何在树莓派上运行？**  
  A: 树莓派使用ARM64架构，直接使用`docker pull ghcr.io/aeolus2025/pt-accelerator:latest`即可，Docker会自动选择ARM64版本。

- **Q: 如何手动构建特定版本的镜像？**  
  A: 在GitHub Actions页面选择「Build and Publish Docker Image (GHCR)」手动触发，在 `version` 输入框填写要推送的标签（如 `main`、`v2.2.1-hotfix`），构建后只推送该标签，**不会更新 `latest`**。留空则只做 amd64 + arm64 双平台构建检查，不推送任何镜像。  
  > 注意：`Use workflow from` 默认选中的是 `main`，其代码是当前 HEAD。若要重建某个已发布版本，请先把该下拉框切换为对应的 tag 再运行，否则会用新代码覆盖该版本镜像（工作流会给出警告）。

- **Q: 支持哪些通知方式？**  
  A: 支持多种通知渠道，包括系统内置通知、邮件通知等，可在配置中设置通知方式和频率。

- **Q: 如何在线编辑Hosts文件？**  
  A: 在Web界面的Hosts管理模块中，可以直接编辑Hosts文件内容，支持实时预览和保存修改。

- **Q: 清空Hosts会破坏系统配置吗？**  
  A: 不会。系统会保护原有的Hosts文件头结构，只清理PT-Accelerator添加的内容，确保系统配置完整。

- **Q: 支持手机访问吗？**  
  A: 完全支持。Web界面已完美适配移动端，支持手机和平板设备访问，提供良好的移动端体验。

- **Q: 如何让Docker容器化的下载器（如qBittorrent）使用优化后的hosts？**  
  A: 在下载器的Docker配置中，添加挂载`/etc/hosts:/etc/hosts:ro`（只读模式），示例：
  ```yaml
  services:
    qbittorrent:
      image: linuxserver/qbittorrent
      # ... 其他配置 ...
      volumes:
        - /etc/hosts:/etc/hosts:ro  # 挂载hosts文件为只读
        - ./config:/config
        - ./downloads:/downloads
  ```
  注意：无论使用什么网络模式（host、bridge等），都需要显式挂载hosts文件，容器不会自动使用宿主机的hosts文件。当PT-Accelerator更新宿主机hosts文件时，容器内的hosts文件也会自动同步更新。

---

## 依赖与环境

- Python 3.9+
- FastAPI、Uvicorn、APScheduler、requests、jinja2
- python-hosts、transmission-rpc、dnspython等（详见requirements.txt）
- cfst（已内置二进制，支持Linux AMD64/ARM64平台）
- Docker（支持多架构构建和部署）

---

## 参考项目

- [CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest) - 优质Cloudflare IP测速工具
- [GitHub Hosts](https://gitlab.com/ineo6/hosts) - 优质GitHub加速hosts源

---

---

## 许可证

本项目主体遵循 **MIT License**，完整文本见 [LICENSE](LICENSE)。

- 原始版权：Copyright (c) 2025 [eternalcurse](https://github.com/eternalcurse/PT-Accelerator)
- 本 fork 修改：Copyright (c) 2026 [Aeolus2025](https://github.com/Aeolus2025/PT-Accelerator)

**第三方组件**：本项目随镜像分发 [`XIU2/CloudflareSpeedTest`](https://github.com/XIU2/CloudflareSpeedTest) 的二进制文件（`cfst_linux_amd64/cfst`、`cfst_linux_arm64/cfst`），该组件遵循 **GPL-3.0**。本项目未修改其源代码，仅以独立可执行文件形式随镜像分发，完整源码可从上述地址获取。前端依赖 Bootstrap / Bootstrap Icons / jQuery 均为 MIT 或 Apache-2.0。

---

如有问题、建议或需求，欢迎在GitHub Issue区反馈！ 
