"""
CTF游戏后端库
提供游戏引擎、强化学习等核心功能
"""

# 导出游戏引擎
from . import game_engine
from .game_engine import GameMap, run_game_server

# 导出强化学习模块
from . import RL
from .RL import (
    DQNAgent,
    DQN,
    ReplayBuffer,
    extract_state_features,
    is_in_my_territory,
    is_in_enemy_territory,
)

__all__ = [
    # 游戏引擎
    'game_engine',
    'GameMap',
    'run_game_server',
    # 强化学习
    'RL',
    'DQNAgent',
    'DQN',
    'ReplayBuffer',
    'extract_state_features',
    'is_in_my_territory',
    'is_in_enemy_territory',
]

