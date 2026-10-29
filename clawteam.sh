#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
IMAGE=${CLAWTEAM_IMAGE:-clawteam-local:latest}
NAME=${CLAWTEAM_CONTAINER:-clawteam}
usage() {
    cat <<'HELP'
用法：
  ./clawteam.sh build                     构建镜像
  ./clawteam.sh start [项目目录] [任务]    启动容器并连接 Leader
  ./clawteam.sh attach                    重新连接 tmux
  ./clawteam.sh shell                     进入容器 Bash（可运行 claude 登录）
  ./clawteam.sh web                       显示两个 Web 界面地址
  ./clawteam.sh magpie [参数...]           运行 Magpie CLI（无参数进入 TUI）
  ./clawteam.sh stop                      停止并删除容器，保留 home 卷和项目
可选环境变量：CLAWTEAM_IMAGE、CLAWTEAM_CONTAINER、CLAWTEAM_ENV_FILE
Web 端口：CLAWTEAM_WEB_PORT（默认 8080）；CLAWTEAM_WEB_BIND（默认 127.0.0.1）
访问地址：CLAWTEAM_WEB_URL（例如 http://192.168.1.10:8080，无末尾斜线）
模型路由：CLAWTEAM_MODEL（例如 group/coding；留空沿用 Claude 配置）
启动配置：CLAWTEAM_PROVIDERS_FILE（宿主机 providers.yaml 路径）
技能来源：CLAWTEAM_SKILLS_FILE（宿主机 skills.yaml 路径）
Instructions 配置：CLAWTEAM_PROMPT_FILE（宿主机 prompt.yaml 路径）
MCP 配置：CLAWTEAM_MCP_FILE；插件列表：CLAWTEAM_PLUGIN_FILE（宿主机 YAML 路径）
容器内 Docker：CLAWTEAM_DIND=1（需要 privileged，使用独立数据卷）
代理：通过 CLAWTEAM_ENV_FILE 传入 MIRROR_HTTP_PROXY 或 HTTP_PROXY、HTTPS_PROXY、NO_PROXY
构建版本：CLAWTEAM_REF、CLAUDE_VERSION、MAGPIE_VERSION、DSH_VERSION、DSH_TUI_VERSION、PLAYWRIGHT_VERSION、OPENBAO_VERSION
HELP
}
command -v docker >/dev/null || { echo '请先安装 Docker。' >&2; exit 1; }
action=${1:-help}
shift || true
case "$action" in
    build)
        docker build --build-arg "CLAWTEAM_REF=${CLAWTEAM_REF:-self}" \
            --build-arg "CLAUDE_VERSION=${CLAUDE_VERSION:-latest}" \
            --build-arg "CODEX_VERSION=${CODEX_VERSION:-latest}" \
            --build-arg "BUN_VERSION=${BUN_VERSION:-1.4.2}" \
            --build-arg "PLAYWRIGHT_VERSION=${PLAYWRIGHT_VERSION:-1.64.1}" \
            --build-arg "OPENBAO_VERSION=${OPENBAO_VERSION:-2.7.2}" \
            --build-arg "DSH_VERSION=${DSH_VERSION:-0.2.1-rc.2}" \
            --build-arg "DSH_TUI_VERSION=${DSH_TUI_VERSION:-0.17.0}" \
            --build-arg "MAGPIE_VERSION=${MAGPIE_VERSION:-latest}" -t "$IMAGE" "$ROOT"
        ;;
    start)
        project=$(cd -- "${1:-.}" && pwd)
        task=${2:-}
        if docker container inspect "$NAME" >/dev/null 2>&1; then
            echo "容器 $NAME 已存在。请用 attach/shell，或 stop 后重新 start。" >&2
            exit 1
        fi
        docker image inspect "$IMAGE" >/dev/null 2>&1 || "$ROOT/clawteam.sh" build
        options=()
        if [[ -n ${CLAWTEAM_ENV_FILE:-} ]]; then
            options+=(--env-file "$CLAWTEAM_ENV_FILE")
        fi
        providers_file=$(realpath -- "${CLAWTEAM_PROVIDERS_FILE:-$ROOT/magpie-config/providers.yaml}")
        [[ -f $providers_file ]] || { echo 'providers.yaml 文件不存在。' >&2; exit 1; }
        options+=(--mount "type=bind,source=$providers_file,target=/etc/clawteam/providers.yaml,readonly")
        skills_file=$(realpath -- "${CLAWTEAM_SKILLS_FILE:-$ROOT/magpie-config/skills.yaml}")
        [[ -f $skills_file ]] || { echo 'skills.yaml 文件不存在。' >&2; exit 1; }
        options+=(--mount "type=bind,source=$skills_file,target=/etc/clawteam/skills.yaml,readonly")
        prompt_file=$(realpath -- "${CLAWTEAM_PROMPT_FILE:-$ROOT/magpie-config/prompt.yaml}")
        [[ -f $prompt_file ]] || { echo 'prompt.yaml 文件不存在。' >&2; exit 1; }
        options+=(--mount "type=bind,source=$prompt_file,target=/etc/clawteam/prompt.yaml,readonly")
        for config in mcp plugin; do
            case "$config" in
                mcp) variable=CLAWTEAM_MCP_FILE ;;
                plugin) variable=CLAWTEAM_PLUGIN_FILE ;;
            esac
            config_file=$(realpath -- "${!variable:-$ROOT/magpie-config/$config.yaml}")
            [[ -f $config_file ]] || { echo "$config.yaml 文件不存在。" >&2; exit 1; }
            options+=(--mount "type=bind,source=$config_file,target=/etc/clawteam/$config.yaml,readonly")
        done
        init_options=(--init)
        if [[ ${CLAWTEAM_DIND:-0} == 1 ]]; then
            init_options=(--init=false)
            options+=(--privileged --user root -e CLAWTEAM_DIND=1 \
                --cgroupns=private --stop-signal SIGRTMIN+3 --stop-timeout 60 \
                --tmpfs /run --tmpfs /tmp:mode=1777 \
                --mount "type=volume,source=${NAME}-docker,target=/var/lib/docker")
        fi
        for var in ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL CLAWTEAM_MODEL CLAWTEAM_WEB_URL \
            MIRROR_HTTP_PROXY HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy ALL_PROXY all_proxy; do
            if [[ -n ${!var:-} ]]; then options+=(-e "$var"); fi
        done
        docker run -d "${init_options[@]}" --name "$NAME" \
            --restart unless-stopped \
            -p "${CLAWTEAM_WEB_BIND:-127.0.0.1}:${CLAWTEAM_WEB_PORT:-8080}:8080" \
            -e "CLAWTEAM_WEB_PORT=${CLAWTEAM_WEB_PORT:-8080}" \
            --mount "type=bind,source=$project,target=/workspace" \
            --mount "type=volume,source=${NAME}-home,target=/home/node" \
            ${options[@]+"${options[@]}"} "$IMAGE" start "$task" >/dev/null
        # Wait until the entrypoint has created the tmux session, or report its error.
        ready=false
        for ((i=0; i<250; i++)); do
            if docker exec --user node "$NAME" tmux has-session -t clawteam 2>/dev/null; then
                ready=true; break
            fi
            if [[ $(docker inspect -f '{{.State.Running}}' "$NAME") != true ]]; then break; fi
            sleep 0.2
        done
        if [[ $ready != true ]]; then docker logs "$NAME"; exit 1; fi
        if [[ -t 0 && -t 1 ]]; then
            exec docker exec --user node -it "$NAME" tmux attach-session -t clawteam
        fi
        echo "已启动 ${NAME}；运行 ./clawteam.sh attach 连接 Leader。"
        ;;
    attach) exec docker exec --user node -it "$NAME" tmux attach-session -t clawteam ;;
    shell) exec docker exec --user node -it "$NAME" bash ;;
    web)
        docker exec --user node "$NAME" bash -c 'base=${CLAWTEAM_WEB_URL:-http://localhost:$CLAWTEAM_WEB_PORT}; printf "ClawTeam: %s/clawteam/\nMagpie:   %s/magpie/?k=%s\n" "$base" "$base" "$(cat "$HOME/.config/magpie/web.key")"'
        ;;
    magpie)
        if [[ $# == 0 ]]; then set -- tui; fi
        if [[ -t 0 && -t 1 ]]; then exec docker exec --user node -it "$NAME" magpie "$@"; fi
        exec docker exec --user node -i "$NAME" magpie "$@"
        ;;
    stop) docker rm -f "$NAME" ;;
    help|-h|--help) usage ;;
    *) usage >&2; exit 1 ;;
esac
