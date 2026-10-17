# coder 的沙箱镜像：沙箱模式下 agent 的命令在这个容器里执行。
# 一次装齐常见项目要用的东西（Python、Node.js、git、编译工具），避免遇到新项目就换镜像。
# 构建：python -m coder.sandbox build    （等价于 docker build -t coder-sandbox:1 coder/sandbox_image）
# 某个项目需要别的语言时，在项目里放 .coder/sandbox.Dockerfile，写 FROM coder-sandbox:1 再加上需要的东西。

FROM node:22-bookworm-slim AS node

FROM python:3.12-slim-bookworm

# 国内网络慢时可以换软件源，例如 --build-arg APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG APT_MIRROR=""
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN if [ -n "$APT_MIRROR" ]; then sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources; fi \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      git curl ca-certificates build-essential procps ripgrep jq unzip less \
 && rm -rf /var/lib/apt/lists/*

# 只从官方 Node 镜像里拿 node 和 npm，不要它的整个系统
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && node --version && npm --version

RUN pip install --no-cache-dir pytest

# 非 root 用户。家目录在运行时挂持久卷：pip --user、npm 全局安装和缓存都在里面，重建容器不丢
RUN useradd -m -u 1000 -s /bin/bash coder && mkdir /workspace && chown coder:coder /workspace
USER coder
ENV HOME=/home/coder \
    NPM_CONFIG_PREFIX=/home/coder/.npm-global \
    PATH=/home/coder/.local/bin:/home/coder/.npm-global/bin:$PATH
WORKDIR /workspace

LABEL org.opencontainers.image.title="coder-sandbox" \
      org.opencontainers.image.description="coder 沙箱：Python 3.12、Node.js 22、git、编译工具" \
      coder.sandbox.version="1"
