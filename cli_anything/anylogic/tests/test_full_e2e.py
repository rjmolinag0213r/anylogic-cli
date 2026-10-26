"""End-to-end tests against the real AnyLogic installation.

* Real model files shipped with AnyLogic are round-tripped and edited.
* The installed ``cli-anything-anylogic`` command is driven via subprocess.
* ``TestLiveEngine`` drives the running AnyLogic IDE through its Design-Time
  Python API: it needs AnyLogic open with "Enable Python connection" switched
  on and the token in ANYLOGIC_API_TOKEN. Without it those tests FAIL (the
  real engine is a hard dependency); deselect them explicitly with
  ``-m "not live"`` when the IDE is not available.
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import time

import pytest

from cli_anything.anylogic.core import elements as el
from cli_anything.anylogic.core import experiments as ex
from cli_anything.anylogic.core import project as pr
from cli_anything.anylogic.utils import anylogic_backend as backend


def _resolve_cli(name):
    """Resolve installed CLI command; falls back to python -m for dev.

    Set env CLI_ANYTHING_FORCE_INSTALLED=1 to require the installed command.
    """
    force = os.environ.get("CLI_ANYTHING_FORCE_INSTALLED", "").strip() == "1"
    path = shutil.which(name)
    if path:
        print(f"[_resolve_cli] Using installed command: {path}")
        return [path]
    if force:
        raise RuntimeError(f"{name} not found in PATH. Install with: pip install -e .")
    module = "cli_anything.anylogic.anylogic_cli"
    print(f"[_resolve_cli] Falling back to: {sys.executable} -m {module}")
    return [sys.executable, "-m", module]


def _example(name):
    root = backend.examples_dir()
    assert root, "AnyLogic example models folder not found - is AnyLogic installed?"
    hits = glob.glob(os.path.join(root, "**", f"{name}.alp"), recursive=True)
    assert hits, f"Example model '{name}' not found under {root}"
    return hits[0]


def _copy_example(name, tmp_path):
    src = _example(name)
    dst = tmp_path / name
    shutil.copytree(os.path.dirname(src), dst)
    return str(dst / f"{name}.alp")


@pytest.fixture
def bass(tmp_path):
    """A private copy of AnyLogic's 'Bass Diffusion' system-dynamics example."""
    return _copy_example("Bass Diffusion", tmp_path)


@pytest.fixture
def callcenter(tmp_path):
    return _copy_example("Call Center", tmp_path)


@pytest.fixture
def state(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("CLI_ANYTHING_ANYLOGIC_HOME", str(d))
    return str(d)


class TestInstallation:
    def test_anylogic_found(self):
        info = backend.install_info()
        print(f"\n  AnyLogic: {info['home']} ({info['edition']} {info['version']})")
        assert os.path.isfile(info["executable"])
        assert info["version"].startswith("8.")

    def test_design_time_api_shipped(self):
        assert backend.install_info()["design_time_api"], \
            "This AnyLogic build has no anylogic_design_time_api folder (needs 8.9+)"


class TestRealModelFiles:
    def test_all_examples_roundtrip(self):
        files = glob.glob(os.path.join(backend.examples_dir(), "**", "*.alp"), recursive=True)
        assert len(files) > 50
        identical = 0
        for f in files:
            proj = pr.open_project(f)  # every real model must parse
            with open(f, "rb") as fh:
                identical += proj.to_bytes() == fh.read()
        print(f"\n  {identical}/{len(files)} example models re-serialise byte-identically")
        assert identical / len(files) > 0.99

    def test_edit_system_dynamics_model(self, bass):
        proj = pr.open_project(bass)
        agent = next(a["name"] for a in el.list_agents(proj)
                     if el.list_variables(proj, a["name"], "stock"))
        assert el.list_variables(proj, agent, "flow")
        stock = el.list_variables(proj, agent, "stock")[0]["name"]
        param = el.list_variables(proj, agent, "parameter")[0]["name"]
        el.set_variable(proj, agent, param, "123")
        el.set_variable(proj, agent, stock, "42")
        ex.set_stop(proj, stop_time=12)
        proj.save()
        again = pr.open_project(bass)
        vals = {v["name"]: v["value"] for v in el.list_variables(again, agent)}
        assert vals[param] == "123" and vals[stock] == "42"
        assert ex.show(again)["stop_time"] == "12.0"
        print(f"\n  Edited model: {bass} ({os.path.getsize(bass):,} bytes)")

    def test_edit_process_model_blocks(self, callcenter):
        proj = pr.open_project(callcenter)
        agent = next(a["name"] for a in el.list_agents(proj) if a["blocks"])
        blocks = el.list_embedded(proj, agent, "block")
        assert blocks and all(b["library"] for b in blocks)
        source = next(b["name"] for b in blocks if b["type"] == "Source")
        assert "rate" in [p["name"] for p in el.block_parameters(proj, agent, source)]
        el.set_block_parameter(proj, agent, source, "rate", "3", unit="PER_HOUR")
        proj.save()
        p = {x["name"]: x for x in el.block_parameters(pr.open_project(callcenter), agent, source)}
        assert (p["rate"]["value"], p["rate"]["unit"]) == ("3", "PER_HOUR")
        assert el.list_connectors(proj, agent)


class TestCLISubprocess:
    CLI_BASE = _resolve_cli("cli-anything-anylogic")

    def _run(self, args, check=True):
        return subprocess.run(self.CLI_BASE + args, capture_output=True, text=True, check=check)

    def _json(self, args):
        return json.loads(self._run(["--json"] + args).stdout)

    def test_help(self):
        r = self._run(["--help"])
        assert r.returncode == 0 and "experiment" in r.stdout

    def test_system_info(self, state):
        assert os.path.isfile(self._json(["system", "info"])["executable"])

    def test_full_workflow(self, bass, state):
        assert self._json(["project", "open", bass])["name"] == "Bass Diffusion"
        name = self._json(["var", "list", "--kind", "parameter"])[0]["name"]
        self._run(["var", "set", name, "77"])
        self._run(["experiment", "stop", "--time", "20"])
        self._run(["experiment", "seed", "--seed", "7"])
        exp = self._json(["experiment", "show"])
        assert exp["stop_time"] == "20.0" and exp["seed"] == "7"
        assert self._json(["var", "get", name])["value"] == "77"
        assert len(self._json(["session", "history"])) == 3
        self._run(["session", "undo"])
        assert self._json(["experiment", "show"])["seed"] != "7"
        assert self._json(["project", "validate"])["valid"]

    def test_save_as_copy(self, bass, state, tmp_path):
        out = str(tmp_path / "copy" / "BassWhatIf.alp")
        res = self._json(["-p", bass, "project", "save-as", out, "--name", "BassWhatIf", "--no-switch"])
        assert os.path.getsize(res["output"]) > 1000
        assert self._json(["-p", out, "project", "info"])["package"] == "basswhatif"
        print(f"\n  Copy: {out}")

    def test_error_is_json_and_nonzero(self, bass, state):
        r = self._run(["--json", "-p", bass, "var", "set", "NoSuchThing", "1"], check=False)
        assert r.returncode == 1
        assert "NoSuchThing" in json.loads(r.stdout)["error"]

    def test_no_project_selected(self, state):
        r = self._run(["var", "list"], check=False)
        assert r.returncode == 1 and "No model selected" in r.stderr


@pytest.mark.live
class TestLiveEngine:
    @pytest.fixture
    def conn(self):
        token = os.environ.get("ANYLOGIC_API_TOKEN")
        assert token, ("Set ANYLOGIC_API_TOKEN: in AnyLogic click 'Enable Python connection' and copy "
                       "the token (or deselect with -m 'not live').")
        c = backend.LiveConnection(token, backend.resolve_port())
        yield c
        c.close()

    def test_open_edit_and_run(self, conn, bass):
        proj = pr.open_project(bass)
        param = el.list_variables(proj, "Main", "parameter")[0]["name"]
        el.set_variable(proj, "Main", param, "50")
        ex.set_stop(proj, stop_time=5)
        proj.save()

        opened = conn.open_model(bass)
        assert opened and opened["name"] == proj.name
        assert proj.name in [m["name"] for m in conn.list_models()]
        assert "Main" in [a["name"] for a in conn.list_agents(proj.name)]
        exps = [e["name"] for e in conn.list_experiments(proj.name)]
        assert exps

        conn.run(proj.name, exps[0])
        time.sleep(15)  # build + run in the IDE
        errors = conn.run_errors(proj.name)
        print(f"\n  run errors reported by AnyLogic: {errors!r}")
        assert errors in (None, "", "[]", [])
        conn.stop()
