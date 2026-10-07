"""Markdown report with PNG figures (§8.11)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from propertyrl.evaluation.stats import holm, paired_bootstrap  # noqa: E402
from propertyrl.infra.config import frozen_dir, list_experiments, load_experiment  # noqa: E402
from propertyrl.infra.storage import query, read_json, reports_dir, runs_dir, sub_artifacts  # noqa: E402
from propertyrl.training.smoke import SMOKE_LABEL  # noqa: E402

log = logging.getLogger(__name__)
ABLATIONS = (
    "mcr_official_2p",
    "ablation_a0_terminal",
    "ablation_a2_purdue",
    "ablation_n4_buy_delegated",
    "ablation_no_trade",
    "ablation_shared_delegation",
    "ablation_no_smdp",
    "research_shortgame_2p",
    "fallback_research_2p",
)


def _runs(experiment: str, smoke: bool) -> list[dict[str, Any]]:
    rows = query("SELECT run_json FROM runs WHERE experiment = ? ORDER BY started", (experiment,))
    out = []
    for (raw,) in rows:
        meta = json.loads(raw)
        if bool(meta.get("smoke")) == smoke and not str(meta["run_id"]).startswith(f"{experiment}_g"):
            out.append(meta)
    return out


def _evals(experiment: str, smoke: bool) -> list[dict[str, Any]]:
    rows = query("SELECT summary_json FROM eval_summaries WHERE experiment = ? AND smoke = ? ORDER BY created",
                 (experiment, int(smoke)))  # fmt: skip
    return [json.loads(r[0]) for r in rows]


def _frozen(name: str, smoke: bool) -> dict[str, Any] | None:
    for candidate in ([f"{name}_smoke", name] if smoke else [name]):
        path = frozen_dir() / f"{candidate}.json"
        if path.exists():
            data: dict[str, Any] = read_json(path)
            return data
    return None


def _fmt(x: Any, digits: int = 3) -> str:
    if x is None:
        return "–"
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def _primary(summary: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    opps = summary.get("opponents", {})
    key = summary.get("strongest_baseline")
    if key in opps:
        return key, opps[key]
    if opps:
        first = next(iter(opps))
        return first, opps[first]
    return None


def learning_curves(runs: list[dict[str, Any]], path: Path) -> bool:
    """SELECT win rate over training steps for every run."""
    fig, ax = plt.subplots(figsize=(7, 4))
    plotted = False
    for meta in runs:
        state_path = runs_dir() / meta["run_id"] / "training_state.json"
        if not state_path.exists():
            continue
        hist = read_json(state_path).get("select_history", [])
        if hist:
            ax.plot([h["step"] for h in hist], [h["win_rate"] for h in hist], marker="o", label=meta["run_id"][-30:])
            plotted = True
    if plotted:
        ax.set_xlabel("Trainingsschritte")
        ax.set_ylabel("SELECT-Siegquote")
        ax.axhline(0.5, color="grey", lw=0.8, ls="--")
        ax.legend(fontsize=6)
        fig.tight_layout()
        fig.savefig(path, dpi=110)
    plt.close(fig)
    return plotted


def bar_plot(values: dict[str, float], path: Path, ylabel: str) -> None:
    """Simple bar chart."""
    fig, ax = plt.subplots(figsize=(7, 3.5))
    names = list(values)
    ax.bar(range(len(names)), [values[n] for n in names], color="#4a7ab5")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=30, ha="right", fontsize=7)
    ax.set_ylabel(ylabel)
    ax.axhline(0.5, color="grey", lw=0.8, ls="--")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def generate_report(experiment: str, smoke: bool = False) -> Path:
    """Write reports/<experiment>.md (+ figures in reports/<experiment>_files/)."""
    from propertyrl.infra.gates import evaluate_gates

    exp = load_experiment(experiment) if experiment in list_experiments() else None
    name = f"{experiment}_smoke" if smoke else experiment
    out = reports_dir() / f"{name}.md"
    fig_dir = reports_dir() / f"{name}_files"
    fig_dir.mkdir(parents=True, exist_ok=True)
    research = exp is not None and exp.label == "research"
    lines: list[str] = [f"# Bericht: {experiment}", ""]
    if smoke:
        lines += [f"> **{SMOKE_LABEL}** – Kleinformat-Durchlauf zum Funktionsnachweis.", ""]
    if research:
        lines += ["> **Research-Ergebnis** (RESEARCH-Ruleset, nicht OFFICIAL).", ""]
    lines += [f"Erzeugt: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    if exp is not None:
        lines += [f"Beschreibung: {exp.description}", ""]
    runs = _runs(experiment, smoke)
    # Versions and hashes.
    lines += ["## Versionen und Konfigurations-Hashes", ""]
    if runs:
        lines += ["| Run | Seed | engine | obs | action | config_hash | Status |", "|---|---|---|---|---|---|---|"]
        for m in runs:
            lines.append(
                f"| {m['run_id']} | {m['training_seed']} | {m.get('engine_version')} | {m.get('obs_version')} | "
                f"{m.get('action_version')} | {str(m.get('config_hash'))[:12]} | {m.get('status')} |"
            )
    else:
        lines.append("Keine Trainingsläufe für dieses Experiment gefunden.")
    lines.append("")
    # Compute vs budget.
    lines += ["## Rechenzeit gegen Budget", ""]
    train_h = sum(float(m.get("training_hours") or 0.0) for m in runs)
    budget_h = sum(float(m.get("budget_hours") or 0.0) for m in runs)
    eval_games = sum(int(m.get("eval_games") or 0) for m in runs)
    lines += [f"Training: {train_h:.3f} h von {budget_h:.1f} h Budget; Evaluationsspiele im Training: {eval_games}.", ""]
    # Round robin.
    lines += ["## Baseline-Round-Robin (G3)", ""]
    rr_path = sub_artifacts("roundrobin") / ("roundrobin_smoke.json" if smoke else "latest.json")
    if rr_path.exists():
        rr = read_json(rr_path)
        lines.append(f"Stärkste Baseline: **{rr['strongest']}**; transitiv: {rr['transitive']}; "
                     f"stabile Spitze: {rr['stable_top']}.")  # fmt: skip
        for block, data in rr["blocks"].items():
            lines += ["", f"### {block}", "", "| Paar | Siegquote A | Wilson-Intervall |", "|---|---|---|"]
            for pair, v in data["pairs"].items():
                lines.append(f"| {pair.replace('|', ' vs ')} | {_fmt(v['win_rate'])} | "
                             f"[{_fmt(v['wilson_lower'])}, {_fmt(v['wilson_upper'])}] |")  # fmt: skip
    else:
        lines.append("Round-Robin noch nicht ausgeführt (`propertyrl round-robin`).")
    lines.append("")
    # Gamma sweep.
    lines += ["## γ-Sweep", ""]
    sweep = _frozen("gamma", smoke)
    if sweep:
        lines += [f"Gewähltes γ: **{sweep.get('gamma')}** ({sweep.get('rule', '')})", "",
                  "| γ | SELECT-Siegquote | EV | Median genuine Entscheidungen | Median Σk | 1/(1−γ) |",
                  "|---|---|---|---|---|---|"]  # fmt: skip
        for p in sweep.get("pilots", []):
            lines.append(
                f"| {p['gamma']} | {_fmt(p['select_win_rate'])} | {_fmt(p['mean_explained_variance'])} | "
                f"{_fmt(p['genuine_decisions_per_game'].get('median'))} | "
                f"{_fmt(p['sum_durations_per_game'].get('median'))} | {_fmt(p['effective_horizon'], 1)} |"
            )
    else:
        lines.append("γ-Sweep noch nicht ausgeführt.")
    lines.append("")
    # Learning curves.
    lines += ["## Lernkurven", ""]
    if learning_curves(runs, fig_dir / "learning_curves.png"):
        lines.append(f"![Lernkurven]({fig_dir.name}/learning_curves.png)")
    else:
        lines.append("Keine SELECT-Evaluationen im Trainingsverlauf vorhanden.")
    lines.append("")
    # Primary endpoint.
    evals = _evals(experiment, smoke)
    lines += ["## Primärer Endpunkt", ""]
    split_name = "SMOKE" if smoke else "TEST"
    primary_rows = [e for e in evals if e.get("split") in (("smoke",) if smoke else ("test",))]
    if primary_rows:
        lines += [f"Split: {split_name}. Wertung: Sieg 1, Niederlage 0, abgeschnitten 0,5 (A-20).", "",
                  "| Agent | Gegner | Spiele | Siegquote | Wilson 95 % | Bootstrap 95 % | Sensitivität | Truncation |",
                  "|---|---|---|---|---|---|---|---|"]  # fmt: skip
        for e in primary_rows:
            pr = _primary(e)
            if pr is None:
                continue
            key, s = pr
            b = s.get("bootstrap", {})
            lines.append(
                f"| {e['agent'][-40:]} | {key} | {s['games']} | {_fmt(s['win_rate'])} | "
                f"[{_fmt(s['wilson_lower'])}, {_fmt(s['wilson_upper'])}] | [{_fmt(b.get('lower'))}, "
                f"{_fmt(b.get('upper'))}] | {_fmt(s['sensitivity_win_rate'])} | {_fmt(s['truncation_rate'])} |"
            )
        pooled = [(_primary(e) or ("", {}))[1] for e in primary_rows]
        rates = [p.get("win_rate", 0.0) for p in pooled if p]
        if rates:
            lines += ["", f"Gepoolt über {len(rates)} Agenten: Mittel {_fmt(sum(rates) / len(rates))}; "
                      f"alle Punktschätzer > 0,5: {all(r > 0.5 for r in rates)}."]  # fmt: skip
        values = {e["agent"][-25:]: (_primary(e) or ("", {"win_rate": 0.0}))[1]["win_rate"] for e in primary_rows}
        bar_plot(values, fig_dir / "primary.png", "Siegquote")
        lines.append(f"\n![Primärer Endpunkt]({fig_dir.name}/primary.png)")
    else:
        lines.append(f"Noch keine {split_name}-Auswertung vorhanden.")
    lines.append("")
    # Secondary metrics, unseen policy and positional bias.
    lines += ["## Sekundärmetriken, ungesehene Policy und Positionsbias", ""]
    for e in evals:
        lines += [f"### {e['split']} – {e['agent'][-50:]}", ""]
        lines.append(f"Sitz-Siegquoten (Positionsbias): {[round(x, 3) for x in e.get('seat_win_rates', [])]}")
        for opp, s in e.get("opponents", {}).items():
            m = s.get("metrics", {})
            tag = " (ungesehene Policy)" if opp == "greedy_v1" else ""
            lines.append(
                f"- gegen {opp}{tag}: Siegquote {_fmt(s['win_rate'])}, mittlere Platzierung {_fmt(s['mean_placement'])},"
                f" Runden {_fmt(m.get('mean_rounds'), 1)}, Käufe {_fmt(m.get('purchases_per_game'), 1)}, Bauten "
                f"{_fmt(m.get('builds_per_game'), 1)}, Handel {_fmt(m.get('trades_per_game'), 2)}, Bau-Effizienz "
                f"{_fmt(m.get('build_efficiency'))}, Haft-Bleiben {m.get('jail_stay_share_by_phase')}"
            )
        lines.append("")
    # Ablations with Holm correction.
    lines += ["## Ablationen (Holm-korrigierte gepaarte Vergleiche gegen A1)", ""]
    base = _ablation_scores("mcr_official_2p", smoke)
    rows, pvals = [], []
    for abl in ABLATIONS[1:]:
        sc = _ablation_scores(abl, smoke)
        if base and sc:
            res = paired_bootstrap(sc, base, reps=2000, seed_key=(len(sc),))
            rows.append((abl, res))
            pvals.append(res.p_value)
    if rows:
        adj = holm(pvals)
        lines += ["| Ablation | Differenz zu A1 | 95 %-CI | p (Holm) |", "|---|---|---|---|"]
        for (abl, res), p in zip(rows, adj, strict=True):
            label = " (Research)" if "research" in abl else ""
            lines.append(f"| {abl}{label} | {_fmt(res.estimate)} | [{_fmt(res.lower)}, {_fmt(res.upper)}] | {_fmt(p)} |")
    else:
        lines.append("Noch keine vergleichbaren Ablations-Auswertungen vorhanden.")
    lines.append("")
    # Self-play.
    lines += ["## Self-Play-Champion-Verlauf", ""]
    sp_runs = _runs("selfplay_official_2p", smoke)
    if sp_runs:
        for m in sp_runs:
            st_path = runs_dir() / m["run_id"] / "training_state.json"
            hist = read_json(st_path).get("champion_history", []) if st_path.exists() else []
            lines.append(f"- {m['run_id']}: {len(hist)} Gate-Prüfungen, {sum(1 for h in hist if h['passed'])} Wechsel")
    else:
        lines.append("Kein Self-Play-Lauf vorhanden.")
    lines.append("")
    # 4P.
    lines += ["## 4 Spieler: OpenSkill und Kingmaking", ""]
    km_dir = sub_artifacts("kingmaking")
    km_files = sorted(km_dir.glob("*smoke*.json" if smoke else "*.json"))
    for f in km_files[-3:]:
        km = read_json(f)
        lines.append(f"- {f.name}: Kingmaking-Rate {_fmt(km.get('kingmaking_rate'))}, mittlere WS {_fmt(km.get('ws_mean'))}"
                     f" ({km.get('points')} Punkte)")  # fmt: skip
    fourp = _evals("fourp_official", smoke) + _evals("fourp_single_seat_fallback", smoke)
    for e in fourp:
        for opp, s in e.get("opponents", {}).items():
            lines.append(f"- {e['experiment']} gegen {opp}: Platz-1-Quote {_fmt(s.get('first_place_rate'))}, "
                         f"mittlere Platzierung {_fmt(s.get('mean_placement'))}")  # fmt: skip
    if not km_files and not fourp:
        lines.append("Noch keine 4P-Auswertung vorhanden.")
    lines.append("")
    # Gates.
    lines += ["## Gate-Status G0–G8", ""]
    gates = evaluate_gates()
    failed = []
    lines += ["| Gate | Status | Kriterien |", "|---|---|---|"]
    for gate, info in gates.items():
        lines.append(f"| {gate} | {info['status']} | {'; '.join(c['name'] + ': ' + c['status'] for c in info['criteria'])} |")
        if info["status"] == "FAIL":
            failed.append(gate)
    lines.append("")
    if failed:
        lines += ["## Negativergebnis", "",
                  f"Folgende Gates sind nicht erfüllt: {', '.join(failed)}. Diagnose: `propertyrl diagnose --run "
                  "runs/<id>` (Reward-Skala, Masken, Observation, Entropie, explained_variance, Dauerverteilung, "
                  "Gegnermix, gültige Zeilen). Fallbacks siehe docs/ROADMAP.md.", ""]  # fmt: skip
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return out


def _ablation_scores(experiment: str, smoke: bool) -> dict[int, float]:
    """Per-seed primary scores of the latest primary evaluation of an experiment (paired comparisons)."""
    evals = [e for e in _evals(experiment, smoke) if e.get("split") == ("smoke" if smoke else "test")]
    if not evals:
        return {}
    pr = _primary(evals[-1])
    if pr is None:
        return {}
    return {int(k): float(v) for k, v in pr[1].get("per_seed", {}).items()}
