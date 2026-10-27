#!/usr/bin/env bash
set -euo pipefail

as_agent() {
    if [[ $(id -u) == 0 ]]; then
        setpriv --reuid=node --regid=node --init-groups "$@"
    else
        "$@"
    fi
}
as_agent python3 /usr/local/lib/clawteam-docker/proxy_bootstrap.py

case ${CLAWTEAM_DIND:-0} in
    0) ;;
    1) ;;
    *) echo 'CLAWTEAM_DIND 只支持 0 或 1。' >&2; exit 1 ;;
esac
if [[ ${CLAWTEAM_DIND:-0} == 0 ]]; then
    if [[ $(id -u) == 0 ]]; then
        exec setpriv --reuid=node --regid=node --init-groups container-entrypoint "$@"
    fi
    exec container-entrypoint "$@"
fi
if [[ $(id -u) != 0 ]]; then
    echo 'DinD 需要 --user root --privileged，或 Compose 的 user: root 与 privileged: true。' >&2
    exit 1
fi
if [[ ! -w /sys/fs/cgroup ]]; then
    echo 'DinD 需要 --privileged 或 Compose 的 privileged: true。' >&2
    exit 1
fi
if [[ $$ != 1 ]]; then
    echo 'DinD 使用 systemd 作为 PID 1，请移除 --init 或设置 Compose init: false。' >&2
    exit 1
fi

export DOCKER_HOST=unix:///var/run/docker.sock
export container=docker
mkdir -p /var/lib/docker
rm -f /run/clawteam-dockerd.pid
python3 /usr/local/lib/clawteam-docker/systemd_runtime.py prepare "$@"
exec /sbin/init --system --unit=multi-user.target --log-level=warning
