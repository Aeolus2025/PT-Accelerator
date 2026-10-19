# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# 多阶段构建：只把当前架构的 cfst 带进最终镜像
#
# 旧写法 `COPY . .` 会把 amd64 与 arm64 两个 cfst（各约 7.5MB）全部塞进镜像层，
# 事后再 rm -rf 也减不掉体积（镜像层是只读的，删除只是新增一个 whiteout 层）。
# 现在改为：先整体拷贝到 builder，按架构删掉另一份，再 COPY --from 进最终镜像。
# ---------------------------------------------------------------------------

# ---------- builder：准备应用目录 ----------
FROM python:3.11-slim AS builder

ARG TARGETARCH

WORKDIR /build

# 整体拷贝源码（.dockerignore 已排除 .git / logs / tests / __pycache__ 等）
COPY . .

# 只保留当前架构的 cfst 目录，另一份直接删掉，不进入最终镜像
# 注意：不能删除当前架构目录，hosts_manager.py 需要调用其中的 cfst_hosts.sh
RUN set -eu; \
    case "${TARGETARCH}" in \
        amd64) DROP="arm64" ;; \
        arm64) DROP="amd64" ;; \
        *) echo "不支持的架构: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    rm -rf "/build/cfst_linux_${DROP}"; \
    test -f "/build/cfst_linux_${TARGETARCH}/cfst"; \
    test -f "/build/cfst_linux_${TARGETARCH}/cfst_hosts.sh"; \
    chmod 755 "/build/cfst_linux_${TARGETARCH}/cfst" "/build/cfst_linux_${TARGETARCH}/cfst_hosts.sh"


# ---------- 最终镜像 ----------
FROM python:3.11-slim

ARG TARGETARCH
ARG APP_PORT=23333

ENV APP_PORT=${APP_PORT} \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 安装依赖（独立层，源码改动不会导致重新安装）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝已裁剪好架构的源码
COPY --from=builder /build /app

# 把 cfst 放到 PATH 里，方便直接以 `cfst` 调用
RUN cp "/app/cfst_linux_${TARGETARCH}/cfst" /usr/local/bin/cfst && \
    chmod 755 /usr/local/bin/cfst

# 创建运行时目录
RUN mkdir -p /app/config /app/logs

EXPOSE ${APP_PORT}

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT}"]
