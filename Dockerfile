ARG MAGPIE_VERSION=latest
ARG DOCKER_VERSION=29.9.2
FROM ghcr.io/yetone/magpie:${MAGPIE_VERSION} AS magpie
FROM docker:${DOCKER_VERSION}-dind AS docker
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
RUN /opt/venv/bin/pip install --no-cache-dir 'PyYAML>=6,<7'
RUN apt-get update && apt-get install -y --no-install-recommends \
    iptables iproute2 util-linux xz-utils systemd systemd-sysv dbus procps \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/venv/bin:${PATH}" HOME=/home/node TERM=xterm-256color \
    CLAWTEAM_DEFAULT_BACKEND=tmux CLAWTEAM_TRANSPORT=file MAGPIE_ADDR=127.0.0.1:3425 \
    CLAWTEAM_PROVIDERS_FILE=/etc/clawteam/providers.yaml
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
COPY proxy_bootstrap.py /usr/local/lib/clawteam-docker/proxy_bootstrap.py
COPY systemd_runtime.py /usr/local/lib/clawteam-docker/systemd_runtime.py
COPY systemd/ /etc/systemd/system/
RUN systemctl enable docker.service clawteam.service \
    && systemctl mask getty.target console-getty.service systemd-udevd.service \
       systemd-udevd-control.socket systemd-udevd-kernel.socket systemd-logind.service \
    && truncate -s 0 /etc/machine-id \
    && rm -f /var/lib/dbus/machine-id \
    && ln -s /etc/machine-id /var/lib/dbus/machine-id
COPY providers.yaml /etc/clawteam/providers.yaml
COPY skills.yaml /etc/clawteam/skills.yaml
COPY --chmod=755 leader-session.sh /usr/local/bin/leader-session
COPY --chmod=755 container-entrypoint.sh /usr/local/bin/container-entrypoint
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/clawteam-docker-entrypoint
USER node
WORKDIR /workspace
EXPOSE 8080
ENTRYPOINT ["clawteam-docker-entrypoint"]
CMD ["start"]
