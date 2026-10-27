#!/usr/bin/env bash
set -euo pipefail

# Keep tools, the gateway and dockerd on the same runtime proxy settings.
export HTTP_PROXY="${HTTP_PROXY:-${http_proxy:-}}" http_proxy="${HTTP_PROXY:-${http_proxy:-}}"
export HTTPS_PROXY="${HTTPS_PROXY:-${https_proxy:-}}" https_proxy="${HTTPS_PROXY:-${https_proxy:-}}"
export ALL_PROXY="${ALL_PROXY:-${all_proxy:-}}" all_proxy="${ALL_PROXY:-${all_proxy:-}}"
NO_PROXY="${NO_PROXY:-${no_proxy:-}}"
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}localhost,127.0.0.1,::1"
export no_proxy="$NO_PROXY"

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

export DOCKER_HOST=unix:///var/run/docker.sock
mkdir -p /var/lib/docker /run
rm -f /run/clawteam-dockerd.pid
touch /var/log/clawteam-dockerd.log
chmod 600 /var/log/clawteam-dockerd.log
docker_pid=
agent_pid=
cleanup() {
    trap - EXIT TERM INT
    if [[ -n $agent_pid ]]; then kill "$agent_pid" 2>/dev/null || true; fi
    if [[ -n $docker_pid ]]; then kill "$docker_pid" 2>/dev/null || true; fi
    wait || true
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
dind dockerd --host="$DOCKER_HOST" --group=node --data-root=/var/lib/docker \
    --pidfile=/run/clawteam-dockerd.pid > /var/log/clawteam-dockerd.log 2>&1 &
docker_pid=$!
ready=false
for ((i=0; i<120; i++)); do
    if timeout 2 docker info >/dev/null 2>&1; then ready=true; break; fi
    kill -0 "$docker_pid" 2>/dev/null || break
    sleep 0.5
done
if [[ $ready != true ]]; then
    echo 'DinD 启动失败，日志位于容器内 /var/log/clawteam-dockerd.log。' >&2
    exit 1
fi
echo 'DinD 已启动，Agent 可通过容器内的 Unix socket 使用 Docker。'
setpriv --reuid=node --regid=node --init-groups container-entrypoint "$@" <&0 &
agent_pid=$!
set +e
wait -n -p finished "$docker_pid" "$agent_pid"
status=$?
set -e
if [[ ${finished:-} == "$docker_pid" && $status == 0 ]]; then status=1; fi
exit "$status"
