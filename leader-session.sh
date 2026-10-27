#!/usr/bin/env bash
set -uo pipefail
delay=${CLAWTEAM_LEADER_RESTART_DELAY:-10}
if [[ ! $delay =~ ^[1-9][0-9]*$ ]]; then
    echo 'CLAWTEAM_LEADER_RESTART_DELAY 必须是正整数秒数。' >&2
    exit 1
fi
trap 'exit 0' TERM INT HUP
while true; do
    if [[ -f /tmp/clawteam-provider-pending ]]; then
        echo '等待填写 providers.yaml 中的 API Key；填写后请重启容器。' >&2
        sleep "$delay"
        continue
    fi
    "$@"
    status=$?
    echo "Leader 进程已退出（状态 $status），${delay} 秒后重启；请检查模型凭据或 tmux 中的提示。" >&2
    sleep "$delay"
done
