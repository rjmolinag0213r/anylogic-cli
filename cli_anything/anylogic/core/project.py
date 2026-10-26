"""AnyLogic project (.alp) data layer.

An ``.alp`` file is XML rooted at ``<AnyLogicWorkspace>`` holding one
``<Model>``. We parse it with lxml keeping CDATA sections and comments so
a load/save cycle preserves the file (the original prolog and line endings
are kept as they were).
"""

import os
import re

from lxml import etree

_PARSER_KW = dict(strip_cdata=False, resolve_entities=False, huge_tree=True, no_network=True)

# Library packages that hold process-modeling style "blocks".
LIBRARY_PREFIX = "com.anylogic.libraries."


class AlpError(ValueError):
    pass


class AlpProject:
    """In-memory view of one .alp file."""

    def __init__(self, path: str, raw: bytes):
        self.path = os.path.abspath(path)
        self._prolog, self._newline = _split_prolog(raw)
        self._trailer = raw[raw.rstrip().rfind(b">") + 1:]  # whatever followed the root tag
        self._reserved = 0
        try:
            self.root = etree.fromstring(raw, etree.XMLParser(**_PARSER_KW))
        except etree.XMLSyntaxError as e:
            raise AlpError(f"{path} is not valid XML: {e}") from e
        if self.root.tag != "AnyLogicWorkspace":
            raise AlpError(f"{path} is not an AnyLogic project (root <{self.root.tag}>)")
        self.model = self.root.find("Model")
        if self.model is None:
            raise AlpError(f"{path} has no <Model> element")
        _keep_empty_pairs(self.root, raw)

    # ── I/O ───────────────────────────────────────────────────────────
    def to_bytes(self) -> bytes:
        body = etree.tostring(self.root, encoding="UTF-8", xml_declaration=False, with_tail=False)
        if self._newline == b"\r\n":
            body = body.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return self._prolog + body + self._trailer

    def save(self, path: str = None) -> str:
        path = os.path.abspath(path or self.path)
        data = self.to_bytes()
        # Validate before touching disk: what we write must parse again.
        etree.fromstring(data, etree.XMLParser(**_PARSER_KW))
        tmp = path + ".cli-tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        self.path = path
        return path

    # ── Basic accessors ───────────────────────────────────────────────
    @property
    def name(self) -> str:
        return text(self.model, "Name")

    @property
    def package(self) -> str:
        return text(self.model, "JavaPackageName")

    @property
    def time_unit(self) -> str:
        return text(self.model, "ModelTimeUnit")

    def agent_classes(self):
        return self.model.findall("ActiveObjectClasses/ActiveObjectClass")

    def agent_class(self, name: str):
        for aoc in self.agent_classes():
            if text(aoc, "Name") == name:
                return aoc
        raise AlpError(f"Agent type '{name}' not found. Available: "
                       f"{[text(a, 'Name') for a in self.agent_classes()]}")

    def agent_class_by_id(self, ident: str):
        for aoc in self.agent_classes():
            if text(aoc, "Id") == str(ident):
                return aoc
        return None

    def experiments(self):
        exps = self.model.find("Experiments")
        # Skip XML comments, which lxml yields as children too.
        return [e for e in exps if isinstance(e.tag, str)] if exps is not None else []

    def all_ids(self):
        ids = []
        for el in self.root.iter("Id"):
            t = (el.text or "").strip()
            if t.isdigit():
                ids.append(int(t))
        return ids

    def new_id(self) -> int:
        """A fresh element id (AnyLogic ids are unique integers per file)."""
        ids = self.all_ids()
        base = max(ids) if ids else 1_700_000_000_000
        self._reserved += 1
        return base + self._reserved

    # ── Summary ───────────────────────────────────────────────────────
    def info(self) -> dict:
        libs = [text(r, "LibraryName") for r in self.model.findall("RequiredLibraryReference")]
        return {
            "path": self.path,
            "name": self.name,
            "package": self.package,
            "time_unit": self.time_unit,
            "anylogic_version": self.root.get("AnyLogicVersion"),
            "alp_version": self.root.get("AlpVersion"),
            "agent_types": [text(a, "Name") for a in self.agent_classes()],
            "experiments": [{"name": text(e, "Name"), "type": e.tag} for e in self.experiments()],
            "required_libraries": libs,
            "has_database": self.model.find("Database") is not None,
            "file_size": os.path.getsize(self.path) if os.path.exists(self.path) else None,
        }


# ── Module-level helpers ─────────────────────────────────────────────

def open_project(path: str) -> AlpProject:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Model file not found: {path}")
    if not path.lower().endswith(".alp"):
        raise AlpError(f"Expected an .alp file, got: {path}")
    with open(path, "rb") as f:
        return AlpProject(path, f.read())


def save_as(proj: AlpProject, dest: str, new_name: str = None) -> dict:
    """Copy a model to a new .alp file, optionally renaming the model.

    Renaming also changes the Java package (lower-cased name, as AnyLogic
    does) and every reference to the old package, so the copy can be open
    side by side with the original in the IDE.
    """
    dest = os.path.abspath(dest)
    if os.path.exists(dest):
        raise AlpError(f"Destination already exists: {dest}")
    renamed = None
    if new_name:
        old_pkg = proj.package
        new_pkg = java_package(new_name)
        set_text(proj.model, "Name", new_name)
        set_text(proj.model, "JavaPackageName", new_pkg)
        count = 0
        for el in proj.root.iter("PackageName"):
            if (el.text or "").strip() == old_pkg:
                set_el_text(el, new_pkg)
                count += 1
        renamed = {"name": new_name, "package": new_pkg, "package_refs_updated": count}
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    proj.save(dest)
    return {"output": dest, "renamed": renamed, "file_size": os.path.getsize(dest)}


def java_package(name: str) -> str:
    pkg = re.sub(r"[^0-9a-zA-Z_]", "", name).lower()
    if not pkg or pkg[0].isdigit():
        pkg = "model" + pkg
    return pkg


_EMPTY_TAG = re.compile(rb"<([A-Za-z_][\w.-]*)(?:\s[^<>]*?)?(/>|></\1>)")


def _keep_empty_pairs(root, raw: bytes):
    """Mark elements written as ``<x></x>`` so lxml does not re-emit them as ``<x/>``."""
    forms = {}
    for m in _EMPTY_TAG.finditer(raw):
        forms.setdefault(m.group(1).decode(), []).append(m.group(2) != b"/>")
    for tag, pairs in forms.items():
        if not any(pairs):
            continue
        empties = [e for e in root.iter(tag) if len(e) == 0 and e.text is None]
        if len(empties) == len(pairs):  # only when the mapping is unambiguous
            for e, is_pair in zip(empties, pairs):
                if is_pair:
                    e.text = ""


def _split_prolog(raw: bytes):
    i = raw.find(b"<AnyLogicWorkspace")
    prolog = raw[:i] if i > 0 else b'<?xml version="1.0" encoding="UTF-8"?>\n'
    newline = b"\r\n" if b"\r\n" in raw[:4096] else b"\n"
    return prolog, newline


def text(el, path: str, default=None):
    if el is None:
        return default
    found = el.find(path)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def set_el_text(el, value):
    """Set element text, keeping CDATA wrapping if the original used it."""
    value = "" if value is None else str(value)
    el.text = etree.CDATA(value) if (_is_cdata(el) and value) else value


def set_text(parent, path: str, value):
    el = parent.find(path)
    if el is None:
        raise AlpError(f"<{path}> not found under <{parent.tag}>")
    set_el_text(el, value)
    return el


def _is_cdata(el) -> bool:
    if el.text is None or len(el):
        return False
    # lxml does not expose CDATA-ness directly; re-serialise this node only.
    return b"<![CDATA[" in etree.tostring(el, with_tail=False)
