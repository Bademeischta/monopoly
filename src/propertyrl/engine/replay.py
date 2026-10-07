"""JSONL game logs and replay (§4.10)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from propertyrl.engine import decisions as D
from propertyrl.engine.board import Board
from propertyrl.engine.cards import Decks
from propertyrl.engine.errors import IllegalActionError, ReplayMismatchError, SchemaVersionError
from propertyrl.engine.ruleset import Ruleset
from propertyrl.engine.state import GameState
from propertyrl.engine.trade import TradeOffer
from propertyrl.versions import ENGINE_VERSION, EVENT_SCHEMA_VERSION, LOG_SCHEMA_VERSION

if TYPE_CHECKING:
    from propertyrl.engine.game import Engine


def build_log(eng: Engine) -> dict[str, Any]:
    """Build a self-contained log dict: header, decisions and (optionally) events."""
    st = eng.state
    header = {
        "type": "header",
        "log_schema_version": LOG_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "ruleset_id": eng.ruleset.ruleset_id,
        "ruleset": eng.ruleset.to_dict(),
        "board": eng.board.to_dict(),
        "decks": eng.decks.to_dict(),
        "n_players": st.n_players,
        "game_seed": st.game_seed,
        "options": eng.options.to_dict(),
        "meta": dict(eng.meta),
        "decisions": st.decision_index,
        "final_state_hash": st.state_hash(),
        "game_over": st.game_over,
        "initial_state": eng.initial_state,
    }
    return {
        "header": header,
        "decisions": [dict(e) for e in eng.decision_log],
        "events": [e.to_dict() for e in eng.events] if eng.log else [],
    }


def write_log(log: dict[str, Any], path: Path) -> None:
    """Write a log as JSONL (header line, one line per decision, then event lines)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(log["header"], sort_keys=True) + "\n")
        for entry in log["decisions"]:
            fh.write(json.dumps({"type": "decision", **entry}, sort_keys=True) + "\n")
        for ev in log.get("events", []):
            fh.write(json.dumps({"type": "event", **ev}, sort_keys=True) + "\n")


def read_log(path: Path) -> dict[str, Any]:
    """Read a JSONL log written by :func:`write_log` and check its schema versions."""
    header: dict[str, Any] | None = None
    decisions: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            kind = row.pop("type", None)
            if kind == "header":
                header = row
            elif kind == "decision":
                decisions.append(row)
            elif kind == "event":
                events.append(row)
    if header is None:
        raise SchemaVersionError(f"log {path} has no header")
    log = {"header": header, "decisions": decisions, "events": events}
    check_versions(log)
    return log


def check_versions(log: dict[str, Any]) -> None:
    """Raise SchemaVersionError on incompatible log, engine or event schema versions."""
    h = log["header"]
    if h.get("log_schema_version") != LOG_SCHEMA_VERSION:
        raise SchemaVersionError(f"log schema {h.get('log_schema_version')} != {LOG_SCHEMA_VERSION}")
    if h.get("engine_version") != ENGINE_VERSION:
        raise SchemaVersionError(
            f"log written by engine {h.get('engine_version')}, current {ENGINE_VERSION}; "
            "regenerate with 'propertyrl replay --regenerate'",
            game_seed=h.get("game_seed"),
        )
    if h.get("event_schema_version") != EVENT_SCHEMA_VERSION:
        raise SchemaVersionError(f"event schema {h.get('event_schema_version')} != {EVENT_SCHEMA_VERSION}")


def deserialize_response(kind: str, sealed: bool, raw: Any) -> Any:
    """Turn a logged response back into the engine response object."""
    if kind in (D.MAIN, D.DEBT):
        return int(raw)
    if kind == D.TRADE_OFFER:
        return [TradeOffer.from_dict(o) for o in raw]
    if kind == D.TRADE_RESPONSE:
        return bool(raw)
    if kind == D.AUCTION_BID:
        if sealed:
            return D.BidLevel(None if raw is None else int(raw))
        return D.Bid(None if raw is None else int(raw))
    raise ReplayMismatchError(f"unknown decision kind {kind!r}")


def replay_log(log: dict[str, Any], check_events: bool = False) -> Engine:
    """Replay a log decision by decision; raise ReplayMismatchError at the first divergence."""
    from propertyrl.engine.game import Engine, EngineOptions

    check_versions(log)
    h = log["header"]
    ruleset = Ruleset.from_dict(h["ruleset"])
    board = Board.from_dict(h["board"])
    decks = Decks.from_dict(h["decks"])
    opts = EngineOptions.from_dict(h["options"])
    seed = int(h["game_seed"])
    init = h.get("initial_state")
    if init:
        state = GameState.from_canonical_dict(init)
        eng = Engine.from_state(ruleset, board, decks, state, opts, int(init["_first_seat"]))
    else:
        eng = Engine.new(ruleset, board, decks, int(h["n_players"]), seed, opts)
    eng.meta = dict(h.get("meta", {}))
    for entry in log["decisions"]:
        d = eng.pending()
        idx = int(entry["i"])
        if d is None:
            raise ReplayMismatchError("game ended before the logged decision", game_seed=seed, decision_index=idx)
        if d.seat != entry["seat"] or d.kind != entry["kind"]:
            raise ReplayMismatchError(
                f"decision mismatch: engine expects seat {d.seat}/{d.kind}, log has {entry['seat']}/{entry['kind']}",
                game_seed=seed,
                decision_index=idx,
                seat=d.seat,
            )
        sealed = eng.ruleset.sealed
        try:
            eng.apply(deserialize_response(d.kind, sealed, entry["r"]))
        except IllegalActionError as exc:
            raise ReplayMismatchError(
                f"logged response is illegal now: {exc.raw_message}",
                game_seed=seed,
                decision_index=idx,
                seat=d.seat,
            ) from exc
        if "h" in entry and eng.state_hash() != entry["h"]:
            raise ReplayMismatchError(
                "state hash differs after this decision", game_seed=seed, decision_index=idx, seat=d.seat
            )
    final = h.get("final_state_hash")
    if final is not None and eng.state_hash() != final:
        raise ReplayMismatchError("final state hash differs", game_seed=seed, decision_index=eng.state.decision_index)
    if check_events and log.get("events"):
        got = [e.to_dict() for e in eng.events]
        if got != log["events"]:
            raise ReplayMismatchError("event stream differs", game_seed=seed)
    return eng
