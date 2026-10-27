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
    echo "错误：$PWD 必须是 Git 仓库；请先在宿主机 git init 并创建一次提交。" >&2
    exit 1
fi
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
    echo '错误：Git 仓库还没有提交，Worker 的 git worktree 需要初始提交。' >&2
    exit 1
fi
workspace=$(git rev-parse --show-toplevel)
cd "$workspace"
if [[ ! ${CLAWTEAM_LEADER_RESTART_DELAY:-10} =~ ^[1-9][0-9]*$ ]]; then
    echo 'CLAWTEAM_LEADER_RESTART_DELAY 必须是正整数秒数。' >&2
    exit 1
fi
# Apply the file on every start, including docker start on an existing container.
CLAWTEAM_MODEL=$(python3 /usr/local/lib/clawteam-docker/magpie_bootstrap.py \
    "${CLAWTEAM_PROVIDERS_FILE:-/etc/clawteam/providers.yaml}")
export CLAWTEAM_MODEL
if [[ -n $CLAWTEAM_MODEL ]]; then
    unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_MODEL
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
export CLAWTEAM_TEAM_NAME="${CLAWTEAM_TEAM_NAME:-clawteam-docker}"
runtime=/usr/local/lib/clawteam-docker/leader_runtime.py
identity=$(python3 "$runtime" prepare "$CLAWTEAM_TEAM_NAME")
read -r CLAWTEAM_AGENT_NAME CLAWTEAM_AGENT_ID <<< "$identity"
export CLAWTEAM_AGENT_NAME CLAWTEAM_AGENT_ID
export CLAWTEAM_AGENT_TYPE=leader CLAWTEAM_AGENT_LEADER=1 CLAWTEAM_WORKSPACE_DIR="$workspace"
prompt="你是团队 $CLAWTEAM_TEAM_NAME 的 Leader，名字是 $CLAWTEAM_AGENT_NAME。团队已注册，直接使用它。请使用 clawteam skill 完成用户任务。使用 clawteam spawn tmux claude 创建 Worker；Leader 和所有 Worker 都必须在本容器运行。收到任务监听通知时，检查任务列表，主动接手未分配的 pending 任务，按需拆分、分配并汇总结果到任务描述。用户任务：${1:-等待面板中的任务。}"
leader_args=(leader-session claude \
    "${1:-检查团队任务列表，认领并执行 pending 任务；没有任务时等待任务通知。}" \
    --append-system-prompt "$prompt" --allowedTools 'Bash(clawteam *)')
printf -v leader_command '%q ' "${leader_args[@]}"
team_session="clawteam-$CLAWTEAM_TEAM_NAME"
tmux new-session -d -s "$team_session" -n "$CLAWTEAM_AGENT_NAME" -c "$workspace" "$leader_command"
# The canonical session is required by ClawTeam's runtime-message injector.
tmux new-session -d -s clawteam -t "$team_session"
python3 "$runtime" watch "$CLAWTEAM_TEAM_NAME" "$CLAWTEAM_AGENT_NAME" &
pids+=($!)
# Detaching tmux keeps agents alive; a failed Web service stops the container.
set +e
wait -n "${pids[@]}"
status=$?
set -e
if [[ $status == 0 ]]; then status=1; fi
exit "$status"
