"""Infrastructure: configuration, run metadata, storage, logging, benchmark, gates, diagnosis, licenses,
planning and pipelines (§9)."""

from propertyrl.infra.config import (
    ExperimentConfig,
    PPOConfig,
    config_hash,
    list_experiments,
    load_board,
    load_decks,
    load_experiment,
    load_ruleset,
    load_setup,
)
from propertyrl.infra.storage import artifacts_dir, reports_dir, runs_dir

#: Higher-level entry points that import the training and evaluation packages, resolved lazily to avoid
#: import cycles (those packages import the configuration and storage helpers above).
_LAZY = {
    "check_licenses": "propertyrl.infra.licenses",
    "diagnose": "propertyrl.infra.diagnose",
    "evaluate_gates": "propertyrl.infra.gates",
    "plan": "propertyrl.infra.plan",
    "repro": "propertyrl.infra.pipeline",
    "run_benchmark": "propertyrl.infra.benchmark",
    "run_experiment_pipeline": "propertyrl.infra.pipeline",
    "smoke_all": "propertyrl.infra.pipeline",
}


def __getattr__(name: str) -> object:
    """Lazy access to the pipeline, gate, benchmark, planning, diagnosis and license entry points."""
    if name in _LAZY:
        import importlib

        return getattr(importlib.import_module(_LAZY[name]), name)
    raise AttributeError(f"module 'propertyrl.infra' has no attribute {name!r}")


__all__ = [
    "ExperimentConfig",
    "PPOConfig",
    "artifacts_dir",
    "check_licenses",
    "config_hash",
    "diagnose",
    "evaluate_gates",
    "list_experiments",
    "load_board",
    "load_decks",
    "load_experiment",
    "load_ruleset",
    "load_setup",
    "plan",
    "reports_dir",
    "repro",
    "run_benchmark",
    "run_experiment_pipeline",
    "runs_dir",
    "smoke_all",
]
