"""Environments: Decision Core, observation, spaces, rewards, Gymnasium, multi-seat and AEC adapters (§6)."""

from propertyrl.env.aec import PropertyAECEnv
from propertyrl.env.core import Closed, DecisionCore, EnvConfig
from propertyrl.env.factory import env_fns, make_env, make_vec_env
from propertyrl.env.multi_seat import PropertyMultiSeatEnv
from propertyrl.env.observation import OBS_DIM, OBS_VERSION, encode, obs_schema
from propertyrl.env.opponents import OpponentConfig, OpponentSampler, SeatPlan
from propertyrl.env.rewards import RewardSpec, potential, terminal_reward
from propertyrl.env.single_agent import PropertySingleAgentEnv
from propertyrl.env.spaces import MaskedDiscrete

__all__ = [
    "OBS_DIM",
    "OBS_VERSION",
    "Closed",
    "DecisionCore",
    "EnvConfig",
    "MaskedDiscrete",
    "OpponentConfig",
    "OpponentSampler",
    "PropertyAECEnv",
    "PropertyMultiSeatEnv",
    "PropertySingleAgentEnv",
    "RewardSpec",
    "SeatPlan",
    "encode",
    "env_fns",
    "make_env",
    "make_vec_env",
    "obs_schema",
    "potential",
    "terminal_reward",
]
