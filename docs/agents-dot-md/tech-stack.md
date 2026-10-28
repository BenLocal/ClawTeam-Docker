# 技术栈与验证
> 本仓库的运行依赖和验证入口；构建与修改代码前阅读。

基础镜像为 Node.js 22，提供 npm；dsh 用 npm 安装，dsh-tui 由 dsh 调用 pnpm 装进 TUI profile；Python 在 `/opt/venv`，YAML 解析使用 PyYAML。Bash 负责进程入口，Python 负责配置校验与运行状态，Nginx 提供子路径访问。版本参数以 Dockerfile 和 `clawteam.sh` 为准。

## 验证命令

- Shell：`bash -n clawteam.sh container-entrypoint.sh docker-entrypoint.sh leader-session.sh`。
- Python：对改动文件运行 `ruff format`、`ruff check`；运行 `python3 -m compileall -q` 检查语法。
- 镜像构建：`./clawteam.sh build`，或指定 `CLAWTEAM_IMAGE` 和版本参数。
- 单元测试：`docker run --rm -v "$PWD:/source:ro" clawteam-local:latest python3 -B -m unittest discover -s /source/tests -p 'test_*.py' -v`。
- 集成测试：`CLAWTEAM_IMAGE=clawteam-local:latest python3 tests/smoke.py`；设置 `CLAWTEAM_DIND=1` 再验证 systemd 路径。
- 内层 Docker：`CLAWTEAM_IMAGE=clawteam-local:latest python3 tests/dind_smoke.py`，需要允许 privileged 容器。
- 原生插件：`CLAWTEAM_IMAGE=clawteam-local:latest python3 tests/plugin_smoke.py`，使用镜像预装的 Bun 离线安装本地插件，并验证安装失败的条目被跳过且不记录成功。

CI 定义在 `.github/workflows/docker-release.yml`。只跑与改动相关的检查；服务边界、启动顺序或代理改动需要相应运行时验证，不能只用语法检查代替。

测试模型请求使用模拟供应商，避免消耗真实模型凭据。运行依赖在测试镜像中，不假定宿主 Python 已安装 PyYAML。
