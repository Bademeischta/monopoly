"""License check of the runtime dependencies (§9.6, §14): GPL/AGPL forbidden, LGPL/MPL allowed."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from importlib import metadata as importlib_metadata
from typing import Any

from propertyrl.infra.config import CONFIG_DIR, load_yaml

#: Exact license identifiers that are not allowed (no substring matching, so LGPL is not caught).
FORBIDDEN = frozenset(
    {
        "GPL", "GPLv2", "GPLv2+", "GPLv3", "GPLv3+", "GPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0",
        "GPL-3.0-only", "GPL-3.0-or-later", "AGPL", "AGPLv3", "AGPLv3+", "AGPL-3.0", "AGPL-3.0-only",
        "AGPL-3.0-or-later", "GNU General Public License (GPL)", "GNU General Public License v2 (GPLv2)",
        "GNU General Public License v2 or later (GPLv2+)", "GNU General Public License v3 (GPLv3)",
        "GNU General Public License v3 or later (GPLv3+)", "GNU Affero General Public License v3",
        "GNU Affero General Public License v3 or later (AGPLv3+)",
    }
)  # fmt: skip
UNKNOWN = frozenset({"UNKNOWN", "", "None"})


def _name(req: str) -> str:
    return re.split(r"[\s;<>=!\[~(]", req.strip(), maxsplit=1)[0].lower().replace("_", "-")


def runtime_packages(root: str = "propertyrl") -> list[str]:
    """Transitive runtime dependencies of ``root`` (extras excluded)."""
    seen: set[str] = set()
    stack = [root]
    while stack:
        pkg = stack.pop()
        try:
            reqs = importlib_metadata.requires(pkg) or []
        except importlib_metadata.PackageNotFoundError:
            continue
        for req in reqs:
            if "extra ==" in req:
                continue
            name = _name(req)
            if name and name not in seen:
                seen.add(name)
                stack.append(name)
    return sorted(seen)


def split_licenses(text: str) -> list[str]:
    """Split a pip-licenses license field into exact identifiers."""
    parts = re.split(r";|\bOR\b|\bAND\b", text)
    return [p.strip() for p in parts if p.strip()]


def check_licenses() -> dict[str, Any]:
    """Run pip-licenses over the runtime dependencies; violations: GPL/AGPL or unknown and not allow-listed."""
    pkgs = runtime_packages()
    exe = shutil.which("pip-licenses")
    cmd = [exe] if exe else [sys.executable, "-m", "piplicenses"]
    proc = subprocess.run(
        [*cmd, "--format=json", "--from=mixed", "--packages", *pkgs], capture_output=True, text=True, timeout=300
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pip-licenses failed: {proc.stderr.strip()}")
    rows = json.loads(proc.stdout)
    allow = (load_yaml(CONFIG_DIR / "license_allowlist.yaml") or {}).get("packages") or {}
    allow_lower = {k.lower(): v for k, v in allow.items()}
    violations = []
    unknown = []
    report = []
    for row in rows:
        name = row["Name"]
        licenses = split_licenses(row["License"])
        forbidden = [lic for lic in licenses if lic in FORBIDDEN]
        is_unknown = not licenses or all(lic in UNKNOWN for lic in licenses)
        status = "ok"
        if forbidden:
            status = "forbidden"
            violations.append({"package": name, "licenses": licenses})
        elif is_unknown:
            if name.lower() in allow_lower:
                status = "allow-listed"
            else:
                status = "unknown"
                unknown.append(name)
        report.append({"package": name, "version": row["Version"], "license": row["License"], "status": status})
    return {
        "packages": len(report),
        "report": report,
        "violations": violations,
        "unknown_not_allowlisted": unknown,
        "passed": not violations and not unknown,
    }
