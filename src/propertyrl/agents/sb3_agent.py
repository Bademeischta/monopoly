"""RL agent wrapper around a saved (SMDP-)MaskablePPO model (§5.6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from propertyrl.agents.base import Policy, filtered_mask
from propertyrl.agents.registry import make_policy
from propertyrl.engine import Bid, BidLevel, TradeOffer
from propertyrl.engine import decisions as D
from propertyrl.engine.errors import SchemaVersionError
from propertyrl.engine.rng import AgentRng
from propertyrl.engine.view import PublicState
from propertyrl.versions import ACTION_VERSION, CHECKPOINT_SCHEMA_VERSION, ENV_VERSION

DEFAULT_DELEGATED = ("TRADE_OFFER", "TRADE_RESPONSE", "AUCTION_BID", "DEBT")


def metadata_path(model_path: Path) -> Path:
    """JSON metadata next to a checkpoint zip."""
    return model_path.with_suffix(".json")


def read_metadata(model_path: Path) -> dict[str, Any]:
    """Load and version-check the checkpoint metadata (SchemaVersionError on mismatch)."""
    from propertyrl.env.observation import OBS_VERSION

    meta_file = metadata_path(model_path)
    if not meta_file.exists():
        raise SchemaVersionError(f"checkpoint metadata {meta_file} is missing")
    meta: dict[str, Any] = json.loads(meta_file.read_text(encoding="utf-8"))
    expected = {
        "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
        "obs_version": OBS_VERSION,
        "action_version": ACTION_VERSION,
        "env_version": ENV_VERSION,
    }
    for key, want in expected.items():
        if meta.get(key) != want:
            raise SchemaVersionError(f"checkpoint {model_path}: {key} {meta.get(key)!r} != {want!r}")
    return meta


class SB3Agent(Policy):
    """MAIN (and non-delegated DEBT) decisions from the network; delegated kinds from the delegation."""

    def __init__(self, model_path: str | Path, deterministic: bool = True, spec_prefix: str = "sb3") -> None:
        import torch

        from propertyrl.training.smdp_ppo import SMDPMaskablePPO

        self.path = Path(model_path)
        self.deterministic = deterministic
        self.prefix = spec_prefix
        self.meta = read_metadata(self.path)
        torch.set_num_threads(1)
        self.model = SMDPMaskablePPO.load(str(self.path), device="cpu")
        env_cfg = self.meta.get("env_config", {})
        self.delegated = frozenset(env_cfg.get("delegated_kinds", DEFAULT_DELEGATED))
        self.delegation = make_policy(env_cfg.get("delegation", "delegation_v1"))
        self.name = f"sb3:{self.path.stem}"
        self.version = str(self.meta.get("model_hash", "unknown"))[:12]

    def spec(self) -> str:
        return f"{self.prefix}:{self.path}"

    def _obs(self, view: PublicState) -> np.ndarray:
        from propertyrl.env.observation import encode

        return encode(view, view.board, view.ruleset, view.seat, view.phase)  # type: ignore[arg-type]

    def choose(self, obs: np.ndarray, mask: np.ndarray, rng: AgentRng) -> int:
        """Masked deterministic argmax or stochastic draw via inversion with the seat's AgentRng."""
        if self.deterministic:
            action, _ = self.model.predict(obs, action_masks=mask, deterministic=True)
            return int(action)
        import torch

        obs_tensor, _ = self.model.policy.obs_to_tensor(obs)
        with torch.no_grad():
            dist = self.model.policy.get_distribution(obs_tensor, action_masks=mask.reshape(1, -1))
            probs = dist.distribution.probs.cpu().numpy().reshape(-1)
        u = rng.random()
        cum = 0.0
        legal = np.flatnonzero(mask)
        for a in legal:
            cum += float(probs[a])
            if u < cum:
                return int(a)
        return int(legal[-1])

    def act_main(self, view: PublicState, legal: list[bool], rng: AgentRng) -> int:
        if view.phase == D.BUY_PHASE and "MAIN_BUY" in self.delegated:
            return self.delegation.act_main(view, legal, rng)
        # Same anti-oscillation mask as in training (A-115).
        mask = np.asarray(filtered_mask(view.window_actions, view.seat, legal), dtype=bool)
        if mask.sum() == 1:
            return int(np.flatnonzero(mask)[0])
        return self.choose(self._obs(view), mask, rng)

    def liquidate(self, view: PublicState, legal: list[bool], debt: dict[str, Any], rng: AgentRng) -> int:
        if "DEBT" in self.delegated:
            return self.delegation.liquidate(view, legal, debt, rng)
        mask = np.asarray(filtered_mask(view.window_actions, view.seat, legal), dtype=bool)
        if mask.sum() == 1:
            return int(np.flatnonzero(mask)[0])
        return self.choose(self._obs(view), mask, rng)

    def propose_trades(self, view: PublicState, rng: AgentRng) -> list[TradeOffer]:
        return self.delegation.propose_trades(view, rng)

    def respond_trade(self, view: PublicState, offer: TradeOffer, rng: AgentRng) -> bool:
        return self.delegation.respond_trade(view, offer, rng)

    def bid(self, view: PublicState, auction: dict[str, Any], rng: AgentRng) -> Bid | BidLevel:
        return self.delegation.bid(view, auction, rng)
