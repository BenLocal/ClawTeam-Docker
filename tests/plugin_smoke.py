"""Verify native plugin installs, download retries and preserved manual settings."""

import os
import subprocess

CHECK = r"""
import json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/usr/local/lib/clawteam-docker")
from plugin_bootstrap import configure, read_plugins

assert os.environ["HTTP_PROXY"] == os.environ["MIRROR_HTTP_PROXY"]
assert os.environ["HTTPS_PROXY"] == os.environ["MIRROR_HTTP_PROXY"]
assert os.environ["http_proxy"] == os.environ["MIRROR_HTTP_PROXY"]
assert "repo.internal" in os.environ["NO_PROXY"]
assert "127.0.0.1" in os.environ["NO_PROXY"]
with tempfile.TemporaryDirectory() as directory:
    source = Path(directory, "fixture-plugin.js")
    source.write_text("export default async () => ({});\n")
    config = Path(directory, "plugin.yaml")
    config.write_text(json.dumps({"plugins": [str(source)]}))
    try:
        configure(config)
    except RuntimeError:
        pass
    else:
        raise AssertionError("offline Bun download unexpectedly succeeded")
    assert not Path.home().joinpath(".config/clawteam-docker/plugin-sources.json").exists()
    profile = Path.home() / ".config/magpie/plugins.json"
    saved = json.loads(profile.read_text())
    assert len(saved["plugins"]) == 1, saved
    assert saved["plugins"][0]["spec"] == str(source)
    saved["plugins"][0]["off"] = True
    saved["plugins"][0]["options"] = {"keep": "manual"}
    saved["plugins"].append({"spec": "/manual-plugin.js", "off": True})
    profile.write_text(json.dumps(saved))
    # Retry with working networking after the deliberately failed proxy.
    proxy = os.environ.get("PLUGIN_TEST_PROXY", "")
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(key, None)
    if proxy:
        os.environ.update(HTTP_PROXY=proxy, HTTPS_PROXY=proxy, http_proxy=proxy, https_proxy=proxy)
    configure(config)
    assert json.loads(profile.read_text()) == saved
    configure(config)
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
print("PASS: failed installation is retried rather than marked successful")
print("PASS: MIRROR_HTTP_PROXY takes precedence; NO_PROXY is retained")
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
        "-e",
        "PLUGIN_TEST_PROXY=" + os.environ.get("MIRROR_HTTP_PROXY", ""),
        os.environ.get("CLAWTEAM_IMAGE", "clawteam-local:latest"),
        "python3",
        "-B",
        "-",
    ],
    input=CHECK,
    text=True,
    check=True,
)
