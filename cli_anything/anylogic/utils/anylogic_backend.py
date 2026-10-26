"""AnyLogic backend - locates the real AnyLogic install and talks to it.

Two channels into the real software:

1. The IDE executable (``AnyLogic.exe``) - used to open ``.alp`` models.
2. The Design-Time Python API - a py4j gateway that lives *inside* the
   running AnyLogic IDE. It is switched on from the IDE with the
   "Enable Python connection" toolbar action, which shows an auth token.
   Through it we can open models, run experiments, stop runs, read
   model-run errors, inspect model structure and query the built-in
   model database.

AnyLogic PLE cannot export standalone Java applications, so the running
IDE is the only engine that can execute a model. The CLI never
reimplements the simulation engine.
"""

import glob
import json
import os
import shutil
import subprocess
import sys

DEFAULT_PORT = 25333
API_VERSION = "8.9.10"

_INSTALL_GLOBS = [
    r"C:\Program Files\AnyLogic * Personal Learning Edition",
    r"C:\Program Files\AnyLogic *",
    r"C:\Program Files (x86)\AnyLogic *",
    "/Applications/AnyLogic*.app/Contents/Eclipse",
    "/opt/anylogic*",
    os.path.expanduser("~/anylogic*"),
]

INSTALL_HINT = (
    "AnyLogic was not found. Install AnyLogic 8.9+ (Personal Learning Edition is free: "
    "https://www.anylogic.com/downloads/) or set ANYLOGIC_HOME to the install folder "
    "(the folder that contains AnyLogic.exe)."
)

CONNECT_HINT = (
    "Could not reach the AnyLogic Python API. In the AnyLogic IDE click the toolbar "
    "button 'Enable Python connection' (API icon), copy the token it shows, then run: "
    "cli-anything-anylogic live connect --token <TOKEN>  (or set ANYLOGIC_API_TOKEN). "
    "Note: the button only exists for some license types - AnyLogic 8.9.10 Personal Learning "
    "Edition does not show it, so live commands are unavailable there; run models with the "
    "IDE's Run button instead."
)


class AnyLogicNotFound(RuntimeError):
    pass


class LiveApiError(RuntimeError):
    pass


# ── Install discovery ────────────────────────────────────────────────

def _exe_in(folder: str):
    for name in ("AnyLogic.exe", "AnyLogic", "anylogic"):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            return p
    return None


def _edition_rank(path: str) -> int:
    # Prefer PLE (this harness targets it) over other editions.
    return 0 if "Personal Learning" in path else 1


def find_installs() -> list:
    """Return every AnyLogic install found, best candidate first."""
    found = []
    env = os.environ.get("ANYLOGIC_HOME")
    if env and _exe_in(env):
        found.append(os.path.abspath(env))
    candidates = set()
    for pattern in _INSTALL_GLOBS:
        candidates.update(glob.glob(pattern))
    for c in sorted(candidates, key=lambda p: (_edition_rank(p), p)):
        if _exe_in(c) and os.path.abspath(c) not in found:
            found.append(os.path.abspath(c))
    on_path = shutil.which("AnyLogic") or shutil.which("anylogic")
    if on_path:
        d = os.path.dirname(os.path.abspath(on_path))
        if d not in found:
            found.append(d)
    return found


def find_anylogic() -> str:
    """Return the AnyLogic install folder or raise with install instructions."""
    installs = find_installs()
    if not installs:
        raise AnyLogicNotFound(INSTALL_HINT)
    return installs[0]


def install_info(home: str = None) -> dict:
    home = home or find_anylogic()
    info = {"home": home, "executable": _exe_in(home), "edition": None, "version": None,
            "design_time_api": os.path.isdir(os.path.join(home, "anylogic_design_time_api"))}
    product = os.path.join(home, ".eclipseproduct")
    if os.path.isfile(product):
        with open(product, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("name="):
                    info["edition"] = line.split("=", 1)[1].strip()
                elif line.startswith("version="):
                    info["version"] = line.split("=", 1)[1].strip()
    info["examples_dir"] = examples_dir(home)
    info["ide_running"] = is_ide_running()
    return info


def examples_dir(home: str = None):
    """Folder holding AnyLogic's bundled example models, if present."""
    home = home or find_anylogic()
    link = os.path.join(home, "links", "examples.link")
    if not os.path.isfile(link):
        return None
    with open(link, encoding="utf-8", errors="replace") as f:
        root = f.read().replace("path=", "").strip()
    if not root:
        return None
    hits = glob.glob(os.path.join(root, "eclipse", "plugins", "com.anylogic.examples_*"))
    return sorted(hits)[-1] if hits else None


def is_ide_running() -> bool:
    if sys.platform != "win32":
        r = subprocess.run(["pgrep", "-f", "AnyLogic"], capture_output=True, text=True)
        return r.returncode == 0
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AnyLogic.exe", "/NH"],
                       capture_output=True, text=True)
    return "AnyLogic.exe" in r.stdout


def open_in_ide(alp_path: str, home: str = None) -> dict:
    """Open a model in the real AnyLogic IDE (starts the IDE if needed)."""
    alp_path = os.path.abspath(alp_path)
    if not os.path.isfile(alp_path):
        raise FileNotFoundError(alp_path)
    home = home or find_anylogic()
    exe = _exe_in(home)
    was_running = is_ide_running()
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen([exe, alp_path], **kwargs)
    return {"opened": alp_path, "executable": exe, "pid": proc.pid,
            "ide_was_running": was_running, "method": "anylogic-ide"}


# ── Live Design-Time API (py4j) ──────────────────────────────────────

def _import_py4j():
    try:
        from py4j.java_gateway import JavaGateway, GatewayParameters
        from py4j.protocol import Py4JError
    except ImportError as e:
        raise LiveApiError("py4j is required for the live API: pip install py4j") from e
    return JavaGateway, GatewayParameters, Py4JError


class LiveConnection:
    """Thin wrapper around AnyLogic's py4j ``PythonWorkspace`` entry point.

    Mirrors the managers exposed by the IDE:
    ModelManager / ElementManager / PropertyManager.
    """

    def __init__(self, token: str, port: int = DEFAULT_PORT):
        if not token:
            raise LiveApiError(CONNECT_HINT)
        JavaGateway, GatewayParameters, Py4JError = _import_py4j()
        self._Py4JError = Py4JError
        self.port = int(port)
        try:
            self.gateway = JavaGateway(gateway_parameters=GatewayParameters(
                auth_token=token, port=self.port, auto_convert=True))
            self.ws = self.gateway.entry_point
            self.ws.init(API_VERSION)
            self.models = self.ws.getModelManager()
            self.elements = self.ws.getElementManager()
            self.props = self.ws.getPropertyManager()
        except Exception as e:  # connection refused, bad token, ...
            raise LiveApiError(f"{CONNECT_HINT}\nDetails: {e}") from e

    def close(self):
        try:
            self.gateway.close(keep_callback_server=False)
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- helpers --
    def _call(self, fn, *args):
        try:
            return fn(*args)
        except self._Py4JError as e:
            msg = str(e).strip()
            raise LiveApiError(msg.splitlines()[0] if msg else repr(e)) from e

    @staticmethod
    def describe(w) -> dict:
        if w is None:
            return None
        return {"id": w.id(), "name": w.name(), "type": w.typeName()}

    def _model(self, name: str):
        m = self._call(self.models.getModel, name)
        if m is None:
            open_names = [x["name"] for x in self.list_models()]
            raise LiveApiError(f"Model '{name}' is not open in the IDE. Open models: {open_names}")
        return m

    def _agent(self, model: str, agent: str):
        a = self._call(self.models.getAgent, self._model(model), agent)
        if a is None:
            raise LiveApiError(f"Agent type '{agent}' not found in model '{model}'")
        return a

    def _element(self, model, agent, element):
        el = self._call(self.elements.getElement, self._agent(model, agent), element)
        if el is None:
            raise LiveApiError(f"Element '{element}' not found in {model}/{agent}")
        return el

    # -- models --
    def list_models(self) -> list:
        return [self.describe(m) for m in self._call(self.models.getModels) or []]

    def open_model(self, alp_path: str) -> dict:
        return self.describe(self._call(self.models.openModel, os.path.abspath(alp_path)))

    def list_agents(self, model: str) -> list:
        return [self.describe(a) for a in self._call(self.models.getAgents, self._model(model)) or []]

    def list_experiments(self, model: str) -> list:
        return [self.describe(e) for e in self._call(self.models.getExperiments, self._model(model)) or []]

    def run(self, model: str, experiment: str) -> dict:
        self._model(model)
        self._call(self.models.runModel, model, experiment)
        return {"model": model, "experiment": experiment, "status": "launched"}

    def stop(self) -> dict:
        self._call(self.models.stopModel)
        return {"status": "stopped"}

    def run_errors(self, model: str):
        return _maybe_json(self._call(self.elements.getModelRunErrors, self._model(model)))

    # -- structure / elements --
    def structure(self, model: str, agent: str):
        return _maybe_json(self._call(self.elements.getModelStructure, self._agent(model, agent)))

    def blocks(self, model: str, agent: str) -> list:
        a = self._agent(model, agent)
        return [self.describe(b) for b in self._call(self.elements.getBlocks, a) or []]

    def get_property(self, model: str, agent: str, element: str, prop: str):
        return _plain(self._call(self.props.getPropertyValue, self._element(model, agent, element), prop))

    def set_property(self, model: str, agent: str, element: str, prop: str, value: str) -> dict:
        el = self._element(model, agent, element)
        self._call(self.props.setProperty, el, prop, self.props.getCodeValue(value))
        return {"element": element, "property": prop, "value": value}

    # -- database --
    def db_structure(self, model: str):
        return _maybe_json(self._call(self.models.getDbStructure, model))

    def db_query(self, model: str, sql: str):
        return _maybe_json(self._call(self.models.executeDbQuery, model, sql))


def _maybe_json(raw):
    if raw is None:
        return None
    raw = str(raw)
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _plain(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


def resolve_token(explicit: str = None, session_token: str = None) -> str:
    return explicit or os.environ.get("ANYLOGIC_API_TOKEN") or session_token


def resolve_port(explicit=None, session_port=None) -> int:
    return int(explicit or os.environ.get("ANYLOGIC_API_PORT") or session_port or DEFAULT_PORT)
