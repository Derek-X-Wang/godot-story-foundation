"""Optional, read-only Git impact planning. A selection is never test evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from decimal import Decimal, InvalidOperation


class ContractError(ValueError):
    """Invalid configuration, unavailable provenance, or unsafe checkout."""


class _Manifest(dict):
    pass


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
_DECLARATION = re.compile(
    r"(?m)^[ \t]*const[ \t]+(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:[ \t]*:[ \t]*(?:float|int))?[ \t]*(?::=|=)[ \t]*"
    r"(?P<number>" + _NUMBER + r")[ \t]*(?:\#[^\r\n]*)?\r?$"
)
_CONST_NAME = re.compile(r"(?m)^[ \t]*const[ \t]+([A-Za-z_][A-Za-z0-9_]*)\b")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _fail_constant(value):
    raise ContractError("non-finite JSON number: " + value)


def _fields(value, required, optional, where):
    if not isinstance(value, dict):
        raise ContractError(where + " must be an object")
    if not required <= value.keys() or value.keys() - required - optional:
        raise ContractError(where + " has missing or unknown fields")


def _strings(value, where, *, nonempty=False, identifiers=False):
    if not isinstance(value, list) or (nonempty and not value):
        raise ContractError(where + " must be " + ("a nonempty" if nonempty else "an") + " array")
    if any(not isinstance(x, str) or not x or "\0" in x for x in value):
        raise ContractError(where + " must contain nonempty strings")
    if len(value) != len(set(value)):
        raise ContractError(where + " contains duplicates")
    if identifiers and any(not _ID.fullmatch(x) for x in value):
        raise ContractError(where + " contains an invalid identifier")
    return value


def _path(value, *, pattern=False):
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ContractError("paths must be nonempty relative POSIX paths")
    path = value[:-3] if pattern and value.endswith("/**") else value
    if (path.startswith("/") or "\\" in path or any(c in path for c in "*?[]")
            or any(part in ("", ".", "..") for part in path.split("/"))):
        raise ContractError("invalid path or unsupported glob: " + value)


def _patterns(value, where):
    for pattern in _strings(value, where):
        _path(pattern, pattern=True)


def _acyclic(entries, where):
    by_id = {entry["id"]: entry for entry in entries}
    visiting, visited = set(), set()

    def visit(name):
        if name in visiting:
            raise ContractError(where + " dependency cycle at " + name)
        if name in visited:
            return
        visiting.add(name)
        for dependency in by_id[name].get("depends_on", []):
            if dependency not in by_id:
                raise ContractError(where + " missing dependency: " + dependency)
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for name in by_id:
        visit(name)


def validate_manifest(value):
    """Validate strictly without changing the supplied mapping."""
    _fields(value, {"schema_version", "components", "suites"},
            {"content_rules", "generated_paths", "guard_paths"}, "manifest")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ContractError("schema_version must be integer 1")
    for kind in ("components", "suites"):
        entries = value[kind]
        if not isinstance(entries, list) or not entries:
            raise ContractError(kind + " must be a nonempty array")
        names = []
        for entry in entries:
            if kind == "components":
                _fields(entry, {"id", "paths"}, {"depends_on"}, "component")
                _patterns(entry["paths"], "component paths")
            else:
                _fields(entry, {"id", "components"}, {"depends_on", "always", "command"}, "suite")
                _strings(entry["components"], "suite components", identifiers=True)
                if "always" in entry and type(entry["always"]) is not bool:
                    raise ContractError("suite always must be boolean")
                if "command" in entry:
                    command = entry["command"]
                    # Repeated argv tokens are legitimate; this is not a set.
                    if (not isinstance(command, list) or not command
                            or any(not isinstance(x, str) or not x or "\0" in x for x in command)):
                        raise ContractError("suite command must be nonempty string argv")
            _strings([entry["id"]], kind + " id", identifiers=True)
            names.append(entry["id"])
            _strings(entry.get("depends_on", []), kind + " dependencies", identifiers=True)
        _strings(names, kind + " ids", identifiers=True)
        _acyclic(entries, kind)
    component_names = {c["id"] for c in value["components"]}
    for suite in value["suites"]:
        if set(suite["components"]) - component_names:
            raise ContractError("suite refers to unknown component: " + suite["id"])
    # Every component must lead to at least one suite, possibly through a
    # reverse-dependent component. Otherwise a mapped edit could disappear.
    covered = {name for suite in value["suites"] for name in suite["components"]}
    previous = None
    while previous != covered:
        previous = set(covered)
        for component in value["components"]:
            if component["id"] in covered:
                covered.update(component.get("depends_on", []))
    if component_names - covered:
        raise ContractError("components have no reachable suite: " + ", ".join(sorted(component_names - covered)))
    rules = value.get("content_rules", [])
    if not isinstance(rules, list):
        raise ContractError("content_rules must be an array")
    rule_paths = []
    for rule in rules:
        _fields(rule, {"path", "constants", "components"}, set(), "content rule")
        _path(rule["path"])
        rule_paths.append(rule["path"])
        _strings(rule["components"], "rule components", nonempty=True, identifiers=True)
        if set(rule["components"]) - component_names:
            raise ContractError("content rule refers to unknown component")
        if not isinstance(rule["constants"], dict) or not rule["constants"]:
            raise ContractError("rule constants must be a nonempty object")
        for name, limits in rule["constants"].items():
            if not isinstance(name, str) or not _NAME.fullmatch(name):
                raise ContractError("constant name must be an exact identifier")
            _fields(limits, {"min", "max"}, set(), "constant bounds")
            for bound in limits.values():
                if type(bound) not in (int, float) or (isinstance(bound, float) and not math.isfinite(bound)):
                    raise ContractError("constant bounds must be finite numbers")
            if limits["min"] > limits["max"]:
                raise ContractError("constant min exceeds max")
    _strings(rule_paths, "content rule paths")
    for field in ("generated_paths", "guard_paths"):
        _patterns(value.get(field, []), field)
    return value


def load_manifest(path):
    """Read strict JSON, retaining the SHA256 of its exact input bytes."""
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                           parse_constant=_fail_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("cannot load manifest: " + str(exc)) from exc
    validate_manifest(value)
    result = _Manifest(value)
    result.source_path = str(path)
    result.source_sha256 = _sha(raw)
    result.canonical_sha256 = _sha(_canonical(value))
    return result


def _git(root, *args):
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_REPLACE_OBJECTS": "1", "LC_ALL": "C"}
    try:
        result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                                 "-c", "core.untrackedCache=false", "-C", str(root), *args],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                check=False)
    except OSError as exc:
        raise ContractError("cannot read Git repository: " + str(exc)) from exc
    if result.returncode:
        raise ContractError("Git read failed: " + result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def _resolve(root, ref):
    if not isinstance(ref, str) or not ref or "\0" in ref or ref.startswith("-"):
        raise ContractError("base and head must be explicit Git commit references")
    commit = _git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    tree = _git(root, "rev-parse", "--verify", "--end-of-options", commit + "^{tree}").decode().strip()
    return {"commit": commit, "tree": tree}


def _clean(root, head, verify_bytes=False):
    if _resolve(root, "HEAD")["commit"] != head["commit"]:
        raise ContractError("current HEAD must equal the requested head commit")
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=none")
    if status:
        raise ContractError("checkout has tracked changes or nonignored untracked files; commit or remove them before selecting")
    if verify_bytes:
        # Do not trust stat-cache, assume-unchanged, or skip-worktree flags to
        # certify source bytes. Compare the actual checkout with the commit.
        objects = {}
        for record in _git(root, "ls-tree", "-r", "-z", head["commit"]).split(b"\0"):
            if not record:
                continue
            metadata, raw_path = record.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split()
            path = root / os.fsdecode(raw_path)
            try:
                for parent in path.parents:
                    if parent == root:
                        break
                    if parent.is_symlink():
                        raise OSError("symlinked parent directory")
                if kind != "blob":
                    if path.is_symlink():
                        raise OSError("symlinked submodule directory")
                    continue  # Submodule dirt is checked by status above.
                entry = path.lstat()
                if mode == "120000":
                    if not stat.S_ISLNK(entry.st_mode):
                        raise OSError("expected symlink")
                    data = os.fsencode(os.readlink(path))
                else:
                    if not stat.S_ISREG(entry.st_mode):
                        raise OSError("expected regular file")
                    if os.name == "posix" and bool(entry.st_mode & 0o111) != (mode == "100755"):
                        raise OSError("executable mode differs")
                    data = path.read_bytes()
                if oid not in objects:
                    objects[oid] = _git(root, "cat-file", "blob", oid)
                if data != objects[oid]:
                    raise OSError("content differs")
            except OSError as exc:
                raise ContractError("tracked checkout bytes do not match head: " + os.fsdecode(raw_path)) from exc


def _matches(path, pattern):
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(prefix + "/")
    return path == pattern


def _code_mask(text):
    """Hide comments and quoted strings while preserving offsets and line breaks."""
    output = list(text)
    quote, comment, i = None, False, 0
    while i < len(text):
        char = text[i]
        if comment:
            if char in "\r\n":
                comment = False
            else:
                output[i] = " "
            i += 1
        elif quote:
            if text.startswith(quote, i):
                output[i:i + len(quote)] = " " * len(quote)
                i += len(quote)
                quote = None
            elif char == "\\":
                output[i] = " "
                i += 1
                if i < len(text):
                    if text[i] not in "\r\n":
                        output[i] = " "
                    i += 1
            else:
                if char not in "\r\n":
                    output[i] = " "
                i += 1
        elif char == "#":
            comment = True
            output[i] = " "
            i += 1
        elif char in "\"'":
            quote = char * 3 if text.startswith(char * 3, i) else char
            output[i:i + len(quote)] = " " * len(quote)
            i += len(quote)
        else:
            i += 1
    return None if quote else "".join(output)


def _normalize_constants(raw, constants):
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return None
    if "\0" in text:
        return None
    mask = _code_mask(text)
    if mask is None:
        return None
    declared = [m.group(1) for m in _CONST_NAME.finditer(mask)]
    if any(declared.count(name) != 1 for name in constants):
        return None
    spans, values = [], {}
    for match in _DECLARATION.finditer(text):
        name = match.group("name")
        start, end = match.span("number")
        if name not in constants or mask[start:end] != text[start:end]:
            continue
        # A declaration-looking line inside a string/comment is not code.
        if not _CONST_NAME.match(mask, match.start()):
            continue
        try:
            value = Decimal(match.group("number"))
        except InvalidOperation:
            return None
        bounds = constants[name]
        if not value.is_finite() or not Decimal(str(bounds["min"])) <= value <= Decimal(str(bounds["max"])):
            return None
        values[name] = match.group("number")
        spans.append((start, end))
    if set(values) != set(constants):
        return None
    normalized = text
    for start, end in reversed(spans):
        normalized = normalized[:start] + "<NUMERIC_CONSTANT>" + normalized[end:]
    return normalized.encode("utf-8"), values


def _numeric_change(old, new, rule):
    left = _normalize_constants(old, rule["constants"])
    right = _normalize_constants(new, rule["constants"])
    if left is None or right is None or left[0] != right[0] or old == new:
        return None
    return {name: {"old": left[1][name], "new": right[1][name]}
            for name in rule["constants"] if left[1][name] != right[1][name]}


def _diff(root, base, head):
    raw = _git(root, "diff", "--raw", "-z", "--no-abbrev", "--no-ext-diff", "--no-textconv",
               "--ignore-submodules=none", "--find-renames", base["commit"], head["commit"], "--")
    fields, index, changes, blobs = raw.split(b"\0"), 0, [], {}
    while index < len(fields) and fields[index]:
        metadata = fields[index].decode("ascii").split()
        index += 1
        if len(metadata) != 5 or not metadata[0].startswith(":"):
            raise ContractError("unexpected Git raw diff format")
        old_mode, new_mode, old_oid, new_oid, code = metadata
        old_mode = old_mode[1:]
        path = os.fsdecode(fields[index])
        index += 1
        old_path = None if code.startswith("A") else path
        new_path = None if code.startswith("D") else path
        if code.startswith(("R", "C")):
            new_path = os.fsdecode(fields[index])
            index += 1
        entry = {"status": code, "old_path": old_path, "new_path": new_path,
                 "old_mode": old_mode, "new_mode": new_mode,
                 "old_blob": old_oid if old_path is not None else None,
                 "new_blob": new_oid if new_path is not None else None}
        for side, oid, mode, side_path in (("old", old_oid, old_mode, old_path),
                                            ("new", new_oid, new_mode, new_path)):
            # Gitlinks name commits, not blobs. They are always conservative.
            data = None
            if side_path is not None and mode != "160000":
                if oid not in blobs:
                    blobs[oid] = _git(root, "cat-file", "blob", oid)
                data = blobs[oid]
            entry[side + "_sha256"] = _sha(data) if data is not None else None
        changes.append(entry)
    return changes, blobs, _sha(raw)


def select(root, base, head, manifest, full=False, evidence=None):
    """Plan required suites for an exact clean checkout; never execute or pass tests.

    Evidence reuse is deliberately unsupported. Skipped suites are unclaimed.
    """
    if evidence is not None:
        raise ContractError("evidence reuse is unsupported; skipped suites are not claimed as passing")
    if type(full) is not bool:
        raise ContractError("full must be boolean")
    validate_manifest(manifest)
    canonical_hash = _sha(_canonical(manifest))
    if isinstance(manifest, _Manifest) and manifest.canonical_sha256 != canonical_hash:
        raise ContractError("loaded manifest was modified; reload its exact input bytes")
    root = Path(root).resolve()
    top = Path(os.fsdecode(_git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    if root != top:
        raise ContractError("root must be the Git repository top-level directory")
    base_ref, head_ref = _resolve(root, base), _resolve(root, head)
    _clean(root, head_ref, verify_bytes=True)
    manifest_path = None
    if isinstance(manifest, _Manifest):
        try:
            manifest_path = Path(manifest.source_path).relative_to(root).as_posix()
        except ValueError as exc:
            raise ContractError("loaded manifest must be a committed file inside root") from exc
        committed = _git(root, "cat-file", "blob", head_ref["commit"] + ":" + manifest_path)
        if _sha(committed) != manifest.source_sha256:
            raise ContractError("loaded manifest bytes do not match the committed head manifest")
    changes, blobs, raw_diff_hash = _diff(root, base_ref, head_ref)
    components = {entry["id"]: entry for entry in manifest["components"]}
    rules = {rule["path"]: rule for rule in manifest.get("content_rules", [])}
    guards = list(manifest.get("guard_paths", [])) + [".gitignore", ".gitattributes", ".gitmodules"]
    direct, conservative = set(), []
    for change in changes:
        paths = sorted({p for p in (change["old_path"], change["new_path"]) if p is not None})
        reasons = []
        path_components = set()
        for path in paths:
            mapped = {name for name, component in components.items()
                      if any(_matches(path, pattern) for pattern in component["paths"])}
            path_components.update(mapped)
            if not mapped:
                reasons.append("unmapped path: " + path)
            if any(_matches(path, pattern) for pattern in guards):
                reasons.append("guard path: " + path)
            if any(_matches(path, pattern) for pattern in manifest.get("generated_paths", [])):
                reasons.append("generated path: " + path)
        modes = {change[side + "_mode"] for side in ("old", "new") if change[side + "_path"] is not None}
        if not modes <= {"100644", "100755"}:
            reasons.append("nonregular Git entry")
        if change["status"][0] not in "AMDR":
            reasons.append("unsupported change status: " + change["status"])
        narrowed = None
        same_path = change["old_path"] == change["new_path"]
        rule = rules.get(change["new_path"])
        if (not reasons and change["status"] == "M" and same_path and rule
                and change["old_mode"] == change["new_mode"]):
            narrowed = _numeric_change(blobs[change["old_blob"]], blobs[change["new_blob"]], rule)
        if narrowed:
            affected = set(rule["components"])
            change["classification"] = "bounded_numeric_constants"
            change["constants"] = narrowed
            change["reasons"] = ["entire old/new content differs only in allowlisted bounded numeric tokens"]
        else:
            affected = path_components
            change["classification"] = "conservative" if reasons else "path"
            change["reasons"] = reasons or ["broad path mapping (no qualifying whole-file numeric-only edit)"]
        change["components"] = sorted(affected)
        direct.update(affected)
        conservative.extend(reasons)
    closure = set(direct)
    changed = True
    while changed:
        changed = False
        for name, component in components.items():
            if name not in closure and set(component.get("depends_on", [])) & closure:
                closure.add(name)
                changed = True
    suites = {suite["id"]: suite for suite in manifest["suites"]}
    chosen = {}
    for name, suite in suites.items():
        why = []
        if full:
            why.append("full mode")
        if conservative:
            why.append("conservative fallback: " + "; ".join(conservative))
        if suite.get("always", False):
            why.append("always required")
        affected = set(suite["components"]) & closure
        if affected:
            why.append("affected components: " + ", ".join(sorted(affected)))
        if why:
            chosen[name] = why
    pending = list(chosen)
    while pending:
        name = pending.pop()
        for prerequisite in suites[name].get("depends_on", []):
            reason = "prerequisite of selected suite: " + name
            if prerequisite not in chosen:
                chosen[prerequisite] = []
                pending.append(prerequisite)
            if reason not in chosen[prerequisite]:
                chosen[prerequisite].append(reason)
    # Prerequisites precede dependants, with manifest order as the stable tie-break.
    order, seen = [], set()

    def order_suite(name):
        if name in seen:
            return
        for dependency in suites[name].get("depends_on", []):
            if dependency in chosen:
                order_suite(dependency)
        seen.add(name)
        order.append(name)

    for name in suites:
        if name in chosen:
            order_suite(name)
    selected, skipped = [], []
    for name in order:
        suite = suites[name]
        row = {"id": name, "status": "required" if "command" in suite else "blocked",
               "reasons": chosen[name], "identity_sha256": _sha(_canonical(suite))}
        if "command" in suite:
            row["command"] = list(suite["command"])
        else:
            row["reasons"] = row["reasons"] + ["no command supplied; cannot execute or pass"]
        selected.append(row)
    for name, suite in suites.items():
        if name not in chosen:
            skipped.append({"id": name, "status": "not_claimed",
                            "reasons": ["outside selected impact scope; no test result or reused evidence claimed"],
                            "identity_sha256": _sha(_canonical(suite))})
    _clean(root, head_ref, verify_bytes=True)
    return {"schema_version": 1, "status": "planned", "passed": False, "complete": False,
            "base": base_ref, "head": head_ref,
            "manifest_sha256": getattr(manifest, "source_sha256", canonical_hash),
            "manifest_hash_encoding": "exact_file_bytes" if isinstance(manifest, _Manifest) else "canonical_json",
            "manifest_source_path": manifest_path,
            "canonical_manifest_sha256": canonical_hash, "raw_diff_sha256": raw_diff_hash,
            "content_diff_sha256": _sha(_canonical(changes)), "changes": changes,
            "direct_components": sorted(direct), "component_closure": sorted(closure),
            "full": full, "conservative_reasons": conservative,
            "selected_suite_ids": order, "selected": selected, "skipped": skipped,
            "evidence_reuse": "unsupported; skipped suites are not claimed as passing"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = select(args.root, args.base, args.head, load_manifest(args.manifest), args.full)
    except (ContractError, OSError) as exc:
        print("impact selection error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
