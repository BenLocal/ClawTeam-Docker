#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$HOME/.claude/skills" "$HOME/.clawteam"
ln -sfn /opt/clawteam/skills/clawteam "$HOME/.claude/skills/clawteam"
# Keep credentials and CLI state in the persistent home volume.
if [[ ${1:-} != start ]]; then
    exec "$@"
fi
shift
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
    echo '错误：/workspace 必须是 Git 仓库；请先在宿主机 git init 并创建一次提交。' >&2
    exit 1
fi
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
    echo '错误：Git 仓库还没有提交，Worker 的 git worktree 需要初始提交。' >&2
    exit 1
fi
# Keep the browser sign-in stable on the same home volume.
key_file="$HOME/.config/magpie/web.key"
mkdir -p "$(dirname "$key_file")"
if [[ ! -s $key_file ]]; then
    (umask 077; python3 -c 'import secrets; print(secrets.token_hex(32))' > "$key_file")
fi
export MAGPIE_WEB_KEY
MAGPIE_WEB_KEY=$(cat "$key_file")
export MAGPIE_WEB_URL="${CLAWTEAM_WEB_URL:-http://localhost:${CLAWTEAM_WEB_PORT:-8080}}/magpie"
pids=()
cleanup() {
    trap - EXIT
    kill "${pids[@]}" 2>/dev/null || true
    tmux kill-server 2>/dev/null || true
    wait || true
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
magpie web --addr 127.0.0.1:3430 --no-open &
pids+=($!)
ready=false
for ((i=0; i<150; i++)); do
    if magpie healthcheck >/dev/null 2>&1; then ready=true; break; fi
    kill -0 "${pids[0]}" 2>/dev/null || break
    sleep 0.2
done
if [[ $ready != true ]]; then echo 'Magpie 启动失败。' >&2; exit 1; fi
if [[ -n ${CLAWTEAM_MODEL:-} ]]; then
    magpie claude "$CLAWTEAM_MODEL"
    # Route this Leader and the Workers it spawns using Magpie's settings.
    unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_MODEL
fi
clawteam board serve --host 127.0.0.1 --port 8081 &
pids+=($!)
nginx -c /etc/nginx/clawteam.conf -g 'daemon off;' &
pids+=($!)
ready=false
for ((i=0; i<50; i++)); do
    if curl -fsS --max-time 1 http://127.0.0.1:8080/clawteam/ >/dev/null 2>&1; then
        ready=true; break
    fi
    sleep 0.2
done
if [[ $ready != true ]]; then echo 'Web 面板启动失败。' >&2; exit 1; fi
prompt="你是本容器中的 Leader。请使用 clawteam skill 完成用户任务。通过 clawteam team spawn-team 创建团队，使用 clawteam spawn tmux claude 创建 Worker；Leader 和所有 Worker 都必须在本容器运行。按需拆分任务、分配、检查收件箱并汇总结果。用户任务：${1:-请先询问用户要完成什么任务。}"
leader_args=(claude --append-system-prompt "$prompt")
if [[ -n ${1:-} ]]; then leader_args+=("$1"); fi
printf -v leader_command '%q ' "${leader_args[@]}"
tmux new-session -d -s clawteam -n leader -c /workspace "$leader_command"
# Detaching tmux keeps agents alive; a failed Web service stops the container.
set +e
wait -n "${pids[@]}"
status=$?
set -e
if [[ $status == 0 ]]; then status=1; fi
exit "$status"
