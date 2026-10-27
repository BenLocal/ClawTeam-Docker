#!/usr/bin/env python3
"""Run a nested build/container and verify runtime proxy configuration."""

import json
import os
import subprocess
import time

NAME = f"clawteam-dind-{os.getpid()}"
VOLUME = NAME + "-docker"
IMAGE = os.environ.get("CLAWTEAM_IMAGE", "clawteam-local:latest")
PROXY = "http://proxy.invalid:3128"
ENVIRONMENT_SAMPLE = 'quoted "value" \\ dollar$ backtick`\nsecond line'


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT)


def inside(*args, user="node"):
    return run("docker", "exec", "--user", user, NAME, *args)


def container_command(detached=True):
    return [
        "docker",
        "run",
        *(["-d"] if detached else []),
        "--init=false",
        "--privileged",
        "--user",
        "root",
        "--cgroupns=private",
        "--stop-signal",
        "SIGRTMIN+3",
        "--tmpfs",
        "/run",
        "--tmpfs",
        "/tmp:mode=1777",
        "--name",
        NAME,
        "--stop-timeout",
        "20",
        "-e",
        "CLAWTEAM_DIND=1",
        "-e",
        f"HTTP_PROXY={PROXY}",
        "-e",
        f"HTTPS_PROXY={PROXY}",
        "-e",
        "NO_PROXY=registry.internal",
        "-e",
        f"CLAWTEAM_SYSTEMD_TEST={ENVIRONMENT_SAMPLE}",
        "--mount",
        f"type=volume,source={VOLUME},target=/var/lib/docker",
        IMAGE,
    ]


def start():
    run(*container_command(), "sleep", "300")
    for _ in range(120):
        try:
            inside("docker", "info")
            inside("systemctl", "is-active", "--quiet", "clawteam.service", user="root")
            return
        except subprocess.CalledProcessError:
            if (
                run("docker", "inspect", "-f", "{{.State.Running}}", NAME).strip()
                != "true"
            ):
                break
        time.sleep(0.5)
    raise AssertionError("DinD did not become ready")


try:
    start()
    assert inside("id", "-u").strip() == "1000"
    assert inside("readlink", "/proc/1/exe", user="root").strip().endswith("/systemd")
    inside("systemctl", "is-active", "--quiet", "docker.service", user="root")
    app_pid = inside(
        "systemctl", "show", "clawteam.service", "-p", "MainPID", "--value", user="root"
    ).strip()
    environment = inside(
        "python3",
        "-c",
        f"import json; from pathlib import Path; data=Path('/proc/{app_pid}/environ').read_bytes().split(b'\\0'); print(json.dumps(next(x.split(b'=',1)[1].decode() for x in data if x.startswith(b'CLAWTEAM_SYSTEMD_TEST='))))",
        user="root",
    )
    assert json.loads(environment) == ENVIRONMENT_SAMPLE
    host_id = run("docker", "info", "-f", "{{.ID}}").strip()
    inner_id = inside("docker", "info", "-f", "{{.ID}}").strip()
    assert inner_id != host_id, "Agent is connected to the host daemon"
    assert inside("docker", "info", "-f", "{{.HTTPProxy}}").strip() == PROXY
    inside("docker", "compose", "version")
    inside("docker", "buildx", "version")
    config = json.loads(inside("cat", "/home/node/.docker/config.json"))
    default = config["proxies"]["default"]
    assert default["httpProxy"] == PROXY and default["httpsProxy"] == PROXY
    assert (
        "127.0.0.1" in default["noProxy"] and "registry.internal" in default["noProxy"]
    )
    inside(
        "python3",
        "-c",
        """
from pathlib import Path
import shutil
p = Path('/tmp/dind-context')
p.mkdir()
shutil.copy('/usr/local/bin/docker-init', p / 'init')
(p / 'Dockerfile').write_text('FROM scratch\\nCOPY init /init\\nENTRYPOINT ["/init", "--version"]\\n')
""",
    )
    inside(
        "docker",
        "build",
        "--network=none",
        "-t",
        "dind-smoke:local",
        "/tmp/dind-context",
    )
    inside(
        "docker",
        "create",
        "--name",
        "nested-smoke",
        "--network=none",
        "dind-smoke:local",
    )
    environment = json.loads(
        inside("docker", "inspect", "-f", "{{json .Config.Env}}", "nested-smoke")
    )
    assert f"HTTP_PROXY={PROXY}" in environment
    result = inside("docker", "start", "-a", "nested-smoke")
    assert "tini version" in result, result
    inside("docker", "rm", "nested-smoke")
    print(
        "PASS: node can build and run an inner container; daemon and nested containers use the configured proxy"
    )
    daemon_pid = inside(
        "systemctl", "show", "docker.service", "-p", "MainPID", "--value", user="root"
    ).strip()
    inside("kill", "-KILL", daemon_pid, user="root")
    recovered = False
    for _ in range(80):
        try:
            new_pid = inside(
                "systemctl",
                "show",
                "docker.service",
                "-p",
                "MainPID",
                "--value",
                user="root",
            ).strip()
            if new_pid not in ("0", daemon_pid):
                inside("docker", "info")
                recovered = True
                break
        except subprocess.CalledProcessError:
            pass
        time.sleep(0.5)
    assert recovered, "systemd did not restart dockerd after a process failure"
    inside("systemctl", "is-active", "--quiet", "clawteam.service", user="root")
    print(
        "PASS: systemd is PID 1, owns docker.service and restarts dockerd after a process failure"
    )
    run("docker", "stop", NAME)
    run("docker", "rm", NAME)
    start()
    assert inside("docker", "info", "-f", "{{.ID}}").strip() == inner_id
    assert "tini version" in inside(
        "docker", "run", "--rm", "--network=none", "dind-smoke:local"
    )
    print(
        "PASS: the independent Docker data volume preserves built images across container recreation"
    )
    run("docker", "stop", NAME)
    run("docker", "rm", NAME)
    result = subprocess.run(
        [*container_command(detached=False), "sh", "-c", "exit 7"],
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 7, result.stdout + result.stderr
    print(
        "PASS: systemd shuts down cleanly and returns the application exit status to Docker"
    )
except Exception as error:
    if isinstance(error, subprocess.CalledProcessError):
        print(error.output)
    print(run("docker", "logs", NAME))
    diagnostic = subprocess.run(
        [
            "docker",
            "exec",
            "--user",
            "root",
            NAME,
            "journalctl",
            "-u",
            "docker",
            "-u",
            "clawteam",
            "--no-pager",
            "-n",
            "50",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    print(diagnostic.stdout)
    raise
finally:
    subprocess.run(
        ["docker", "rm", "-f", NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    subprocess.run(
        ["docker", "volume", "rm", VOLUME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
