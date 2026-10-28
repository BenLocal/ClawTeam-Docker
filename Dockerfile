ARG MAGPIE_VERSION=latest
ARG DOCKER_VERSION=29.9.2
FROM ghcr.io/yetone/magpie:${MAGPIE_VERSION} AS magpie
FROM docker:${DOCKER_VERSION}-dind AS docker
FROM node:22-bookworm-slim
ARG CLAWTEAM_REF=self
ARG CLAUDE_VERSION=latest
ARG CODEX_VERSION=latest
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl git tmux python3 python3-venv ripgrep nginx \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/BenLocal/ClawTeam.git /opt/clawteam \
    && cd /opt/clawteam && git checkout "$CLAWTEAM_REF" \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir /opt/clawteam \
    && npm install -g "@anthropic-ai/claude-code@${CLAUDE_VERSION}" \
        "@openai/codex@${CODEX_VERSION}"
RUN /opt/venv/bin/pip install --no-cache-dir 'PyYAML>=6,<7'
# dsh-tui accepts only the dsh releases it names, so both stay pinned. Its
# profile is built here and seeded into the home volume on first start.
ARG DSH_VERSION=0.2.1-rc.2
ARG DSH_TUI_VERSION=0.17.0
ARG PNPM_VERSION=12.15.0
RUN npm install -g "@deepseek-ai/dsh@${DSH_VERSION}" "pnpm@${PNPM_VERSION}" \
    && DSH_HOME=/opt/dsh dsh plugin --profile tui add \
        "@deepseek-harness-tui/dsh-tui@${DSH_TUI_VERSION}" \
    && rm -rf /opt/dsh/profiles/tui/.plugin-manager /root/.local/share/pnpm /root/.cache \
    && chmod -R a+rX /opt/dsh
ARG BUN_VERSION=1.4.2
ARG TARGETARCH
# Magpie runs plugins on Bun and otherwise downloads it from GitHub at runtime.
RUN case "${TARGETARCH:-amd64}" in \
        amd64) bun_target=linux-x64-baseline ;; \
        arm64) bun_target=linux-aarch64 ;; \
        *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
    && bun_base="https://github.com/oven-sh/bun/releases/download/bun-v${BUN_VERSION}" \
    && curl -fsSL -o /tmp/bun.zip "$bun_base/bun-$bun_target.zip" \
    && curl -fsSL "$bun_base/SHASUMS256.txt" \
        | awk -v f="bun-$bun_target.zip" '$2 == f { print $1 "  /tmp/bun.zip" }' \
        | grep . | sha256sum -c - \
    && python3 -c 'import sys, zipfile; sys.stdout.buffer.write(zipfile.ZipFile("/tmp/bun.zip").read(sys.argv[1]))' \
        "bun-$bun_target/bun" > /usr/local/bin/bun \
    && chmod 755 /usr/local/bin/bun \
    && rm /tmp/bun.zip \
    && bun --version
RUN apt-get update && apt-get install -y --no-install-recommends \
    iptables iproute2 util-linux xz-utils systemd systemd-sysv dbus procps \
    && rm -rf /var/lib/apt/lists/*
# NARB_DISABLE_NATIVE_CACHE: dsh loads native addons from node_modules instead of
# copying them into /tmp, which the systemd mode mounts as a noexec tmpfs.
ENV PATH="/opt/venv/bin:${PATH}" HOME=/home/node TERM=xterm-256color \
    CLAWTEAM_DEFAULT_BACKEND=tmux CLAWTEAM_TRANSPORT=file MAGPIE_ADDR=127.0.0.1:3425 \
    CLAWTEAM_PROVIDERS_FILE=/etc/clawteam/providers.yaml \
    DISABLE_AUTOUPDATER=1 MAGPIE_BUN=/usr/local/bin/bun \
    NARB_DISABLE_NATIVE_CACHE=1
COPY --from=magpie /magpie /usr/local/bin/magpie
COPY --from=docker /usr/local/bin/docker /usr/local/bin/dockerd \
    /usr/local/bin/docker-init /usr/local/bin/docker-proxy \
    /usr/local/bin/containerd-shim-runc-v2 \
    /usr/local/bin/ctr /usr/local/bin/runc /usr/local/bin/
COPY --from=docker /usr/local/libexec/docker/cli-plugins/ /usr/local/libexec/docker/cli-plugins/
COPY nginx.conf /etc/nginx/clawteam.conf
COPY subpath.js /etc/nginx/subpath.js
COPY leader_runtime.py /usr/local/lib/clawteam-docker/leader_runtime.py
COPY magpie_bootstrap.py /usr/local/lib/clawteam-docker/magpie_bootstrap.py
COPY skills_bootstrap.py /usr/local/lib/clawteam-docker/skills_bootstrap.py
COPY prompt_bootstrap.py /usr/local/lib/clawteam-docker/prompt_bootstrap.py
COPY mcp_bootstrap.py plugin_bootstrap.py /usr/local/lib/clawteam-docker/
COPY proxy_bootstrap.py /usr/local/lib/clawteam-docker/proxy_bootstrap.py
COPY systemd_runtime.py /usr/local/lib/clawteam-docker/systemd_runtime.py
COPY systemd/ /etc/systemd/system/
RUN systemctl enable docker.service magpie.service clawteam.service clawteam-skills-update.timer \
    && systemctl mask getty.target console-getty.service systemd-udevd.service \
       systemd-udevd-control.socket systemd-udevd-kernel.socket systemd-logind.service \
    && truncate -s 0 /etc/machine-id \
    && rm -f /var/lib/dbus/machine-id \
    && ln -s /etc/machine-id /var/lib/dbus/machine-id
COPY magpie-config/ /etc/clawteam/
COPY --chmod=755 leader-session.sh /usr/local/bin/leader-session
COPY --chmod=755 container-entrypoint.sh /usr/local/bin/container-entrypoint
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/clawteam-docker-entrypoint
USER node
WORKDIR /workspace
EXPOSE 8080
ENTRYPOINT ["clawteam-docker-entrypoint"]
CMD ["start"]
