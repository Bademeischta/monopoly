"""Central version registry for all schemas and components.

Every artifact (logs, checkpoints, evaluation records, run metadata) carries
these versions so that incompatible combinations are detected on load.
Only the standard library may be imported here (the engine depends on it).
"""

from __future__ import annotations

__version__ = "0.1.0"

#: Version of the rule engine. Bump on any deliberate rule change; archived
#: replays must then be regenerated (``propertyrl replay --regenerate``).
ENGINE_VERSION = "0.1.0"
#: Version of the environment semantics (decision core, auto-skip, rewards).
ENV_VERSION = "env1.0"
#: Base version of the observation schema; the full version appends a hash of
#: the schema and all normalisation constants (see env.observation).
OBS_VERSION_BASE = "o1.0"
#: Version of the flat action space.
ACTION_VERSION = "a1.0"
#: Version of the event schema.
EVENT_SCHEMA_VERSION = "e1.0"
#: Version of the JSONL game log format.
LOG_SCHEMA_VERSION = "l1.0"
#: Version of the checkpoint metadata format.
CHECKPOINT_SCHEMA_VERSION = "c1.0"

#: Heuristic versions per policy name. Each policy implementation also exposes
#: its version; a test asserts that both agree.
HEURISTIC_VERSIONS: dict[str, str] = {
    "random_legal": "h1.0",
    "greedy_v1": "h1.0",
    "roi_markov_v1": "h1.0",
    "strong_a_v1": "h1.0",
    "strong_b_v1": "h1.0",
    "delegation_v1": "h1.0",
}


def static_versions() -> dict[str, str]:
    """Return all versions that do not require importing optional packages."""
    return {
        "package_version": __version__,
        "engine_version": ENGINE_VERSION,
        "env_version": ENV_VERSION,
        "obs_version_base": OBS_VERSION_BASE,
        "action_version": ACTION_VERSION,
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "log_schema_version": LOG_SCHEMA_VERSION,
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
    }


def all_versions() -> dict[str, str]:
    """Return all versions including the hashed observation version.

    Imports the environment lazily (needs numpy/gymnasium).
    """
    from propertyrl.env.observation import OBS_VERSION

    versions = static_versions()
    versions["obs_version"] = OBS_VERSION
    for name, ver in sorted(HEURISTIC_VERSIONS.items()):
        versions[f"heuristic_{name}"] = ver
    return versions
