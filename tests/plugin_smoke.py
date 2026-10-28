"""Verify native plugin installs, skipped failures and preserved manual settings."""

import os
import subprocess

CHECK = r"""
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/usr/local/lib/clawteam-docker")
from plugin_bootstrap import configure, read_plugins

assert os.environ["HTTP_PROXY"] == "http://old-proxy:3128"
assert "HTTPS_PROXY" not in os.environ
assert "http_proxy" not in os.environ
assert os.environ["NO_PROXY"] == "repo.internal"
docker_proxy=json.loads(Path.home().joinpath(".docker/config.json").read_text())["proxies"]["default"]
assert docker_proxy["httpProxy"] == os.environ["MIRROR_HTTP_PROXY"]
assert "127.0.0.1" in docker_proxy["noProxy"]
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory, "fixture-plugin.js")
    source.write_text("export default async () => ({});\n")
    missing = Path(directory, "missing-plugin.js")
    config = Path(directory, "plugin.yaml")
    config.write_text(json.dumps({"plugins": [str(missing), str(source)]}))
    # The preinstalled Bun runs a local plugin without network; a failed entry is skipped.
    assert configure(config) == [1]
    state_file = Path.home() / ".config/clawteam-docker/plugin-sources.json"
    assert json.loads(state_file.read_text()) == {str(source): str(source)}
    profile = Path.home() / ".config/magpie/plugins.json"
    saved = json.loads(profile.read_text())
    assert len(saved["plugins"]) == 1, saved
    assert saved["plugins"][0]["spec"] == str(source)
    saved["plugins"][0]["off"] = True
    saved["plugins"][0]["options"] = {"keep": "manual"}
    saved["plugins"].append({"spec": "/manual-plugin.js", "off": True})
    profile.write_text(json.dumps(saved))
    # The failed entry stays unrecorded and is retried; installed ones keep manual settings.
    assert configure(config) == [1]
    assert json.loads(profile.read_text()) == saved
    assert configure(config) == [1]
    assert json.loads(profile.read_text()) == saved
    config.write_text("plugins: []\n")
    configure(config)
    assert json.loads(profile.read_text()) == saved
    config.write_text("plugins: [valid, 123]\n")
    try:
        read_plugins(config)
    except TypeError:
        pass
    else:
        raise AssertionError("non-string plugin spec accepted")
print("PASS: native plugin registration is idempotent and preserves manual plugins/options/off state")
print("PASS: failed installation is skipped, retried and never marked successful")
print("PASS: Docker/download proxy scope preserves the application's proxy environment")
"""

subprocess.run(
    [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "host",
        "-e",
        "MIRROR_HTTP_PROXY=http://127.0.0.1:9",
        "-e",
        "HTTP_PROXY=http://old-proxy:3128",
        "-e",
        "NO_PROXY=repo.internal",
        os.environ.get("CLAWTEAM_IMAGE", "clawteam-local:latest"),
        "python3",
        "-B",
        "-",
    ],
    input=CHECK,
    text=True,
    check=True,
)
