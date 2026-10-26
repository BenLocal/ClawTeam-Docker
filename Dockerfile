ARG MAGPIE_VERSION=latest
FROM ghcr.io/yetone/magpie:${MAGPIE_VERSION} AS magpie
FROM node:22-bookworm-slim
ARG CLAWTEAM_REF=main
ARG CLAUDE_VERSION=latest
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git tmux python3 python3-venv ripgrep nginx \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/HKUDS/ClawTeam.git /opt/clawteam \
    && cd /opt/clawteam && git checkout "$CLAWTEAM_REF" \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir /opt/clawteam \
    && npm install -g "@anthropic-ai/claude-code@${CLAUDE_VERSION}"
ENV PATH="/opt/venv/bin:${PATH}" HOME=/home/node TERM=xterm-256color \
    CLAWTEAM_DEFAULT_BACKEND=tmux CLAWTEAM_TRANSPORT=file MAGPIE_ADDR=127.0.0.1:3425
COPY --from=magpie /magpie /usr/local/bin/magpie
COPY nginx.conf /etc/nginx/clawteam.conf
COPY subpath.js /etc/nginx/subpath.js
COPY --chmod=755 container-entrypoint.sh /usr/local/bin/container-entrypoint
USER node
WORKDIR /workspace
EXPOSE 8080
ENTRYPOINT ["container-entrypoint"]
