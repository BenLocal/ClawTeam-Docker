"""Write a Git credential-store file from GIT_CREDENTIAL_* before agents start.

A file keeps HTTPS credentials available to every agent, including runtimes such
as dsh that drop credential-shaped variables from their child processes.
"""

import os
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

FIELDS = ("GIT_CREDENTIAL_URL", "GIT_CREDENTIAL_USERNAME", "GIT_CREDENTIAL_PASSWORD")


def read_settings(environ):
    """Return (scheme, host, username, password), or None when unconfigured."""
    values = {name: environ.get(name, "").strip() for name in FIELDS}
    if not any(values.values()):
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError("Git 凭据配置不完整，缺少 " + "、".join(missing) + "。")
    url = urlsplit(values["GIT_CREDENTIAL_URL"])
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username is not None
        or url.path not in {"", "/"}
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "GIT_CREDENTIAL_URL 必须是不含账号和路径的 http(s)://主机[:端口]。"
        )
    return (
        url.scheme,
        url.netloc,
        values["GIT_CREDENTIAL_USERNAME"],
        values["GIT_CREDENTIAL_PASSWORD"],
    )


def credential_path(environ):
    config = Path(environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config / "clawteam-docker/git-credentials"


def configure(environ=os.environ):
    settings = read_settings(environ)
    if settings is None:
        return
    scheme, host, username, password = settings
    path = credential_path(environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    line = f"{scheme}://{quote(username, safe='')}:{quote(password, safe='')}@{host}\n"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(line)
    temporary.replace(path)
    print("git: 已写入凭据文件。", flush=True)


if __name__ == "__main__":
    try:
        configure()
    except (OSError, ValueError) as error:
        print(f"Git 凭据配置失败：{error}", file=sys.stderr)
        sys.exit(1)
