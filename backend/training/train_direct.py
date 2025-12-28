"""
直接训练脚本 - 不依赖游戏服务器
直接模拟游戏环境进行训练，速度更快
"""

import sys
import os
# 添加父目录到路径，以便访问 lib/ 和 pathfinding_adapter.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from lib import RL
import numpy as np
import random
import math
import json
import time
import torch
from collections import deque
from multiprocessing import Process, Queue, Manager, Value, Lock
import multiprocessing

# 导入路径规划适配器（必需）
try:
    import pathfinding_adapter as pf
except ImportError as e:
    print("=" * 60)
    print("错误: 路径规划适配器不可用！")
    print("=" * 60)
    print(f"导入错误: {e}")
    print("\n请确保 pathfinding_adapter.py 文件存在且可导入")
    print("路径规划是必需的，无法使用简化移动作为回退")
    import sys
    sys.exit(1)

# 简化的游戏模拟器
class SimpleGameSimulator:
    """简化的游戏模拟器，用于直接训练"""
    
    def __init__(self, width=20, height=20, num_players=3, num_flags=9, num_obstacles_1=8, num_obstacles_2=4):
        self.width = width
        self.height = height
        self.num_players = num_players
        self.num_flags = num_flags
        self.num_obstacles_1 = num_obstacles_1  # 单格障碍数量
        self.num_obstacles_2 = num_obstacles_2  # 双格障碍数量
        self.middle_line = width / 2
        
        # 初始化游戏状态
        self.reset()
    
    def _not_contains(self, xy_list, x, y):
        """检查位置是否不在列表中"""
        return not any(pos[0] == x and pos[1] == y for pos in xy_list)
    
    def _is_valid_position(self, x, y, obstacles1, obstacles2, exclude_list=None):
        """检查位置是否有效（不在障碍物上，不在排除列表中）"""
        # 检查边界
        if x < 1 or x >= self.width - 1 or y < 1 or y >= self.height - 1:
            return False
        
        # 检查单格障碍
        if not self._not_contains(obstacles1, x, y):
            return False
        
        # 检查双格障碍（占用y和y+1）
        # 如果(x, y)或(x, y-1)在obstacles2中，则位置无效
        if (x, y) in obstacles2 or (x, y - 1) in obstacles2:
            return False
        
        # 检查排除列表
        if exclude_list:
            if not self._not_contains(exclude_list, x, y):
                return False
        
        # 检查是否在固定的target或prison区域（这些区域不能放障碍和flag）
        center_y = self.height // 2
        # L队target区域
        if 2 <= x < 5 and center_y - 1 <= y < center_y + 2:
            return False
        # R队target区域
        if self.width - 5 <= x < self.width - 2 and center_y - 1 <= y < center_y + 2:
            return False
        # L队prison区域
        if 2 <= x < 5 and self.height - 4 <= y < self.height - 1:
            return False
        # R队prison区域
        if self.width - 5 <= x < self.width - 2 and self.height - 4 <= y < self.height - 1:
            return False
        
        return True
    
    def reset(self):
        """重置游戏状态，随机生成地图、flag和出生点"""
        import random
        
        # 生成随机障碍物
        self.obstacles1 = []  # 单格障碍
        for i in range(self.num_obstacles_1):
            while True:
                x = random.randint(4, self.width - 5)
                y = random.randint(1, self.height - 2)
                if self._is_valid_position(x, y, self.obstacles1, []):
                    self.obstacles1.append((x, y))
                    break
        
        self.obstacles2 = []  # 双格障碍（占用y和y+1）
        for i in range(self.num_obstacles_2):
            attempts = 0
            while attempts < 1000:  # 防止无限循环
                x = random.randint(4, self.width - 5)
                y = random.randint(1, self.height - 3)  # y+1最大为height-2，在有效范围内
                # 检查y和y+1位置都有效，且y+1不在target/prison区域
                if (self._is_valid_position(x, y, self.obstacles1, self.obstacles2, None) and
                    self._is_valid_position(x, y + 1, self.obstacles1, self.obstacles2, None)):
                    self.obstacles2.append((x, y))
                    break
                attempts += 1
            if attempts >= 1000:
                print(f"警告: 无法生成第{i+1}个双格障碍，跳过")
        
        # 目标区域（固定位置）
        self.l_targets = set()
        center_y = self.height // 2
        for x in range(2, 5):
            for y in range(center_y - 1, center_y + 2):
                self.l_targets.add((x, y))
        
        self.r_targets = set()
        for x in range(self.width - 5, self.width - 2):
            for y in range(center_y - 1, center_y + 2):
                self.r_targets.add((x, y))
        
        # Prison区域（固定位置）
        self.l_prison = set()
        for x in range(2, 5):
            for y in range(self.height - 4, self.height - 1):
                self.l_prison.add((x, y))
        
        self.r_prison = set()
        for x in range(self.width - 5, self.width - 2):
            for y in range(self.height - 4, self.height - 1):
                self.r_prison.add((x, y))
        
        # 随机生成L队flag（在左侧半场）
        self.l_flags = []
        l_flag_positions = []
        for i in range(self.num_flags):
            while True:
                x = random.randint(2, self.width // 2 - 1)
                y = random.randint(1, self.height - 3)
                if self._is_valid_position(x, y, self.obstacles1, self.obstacles2, l_flag_positions):
                    l_flag_positions.append((x, y))
                    self.l_flags.append({
                        "posX": x,
                        "posY": y,
                        "canPickup": True,
                        "mine": True
                    })
                    break
        
        # 随机生成R队flag（在右侧半场）
        self.r_flags = []
        r_flag_positions = []
        for i in range(self.num_flags):
            while True:
                x = random.randint(self.width // 2, self.width - 2)
                y = random.randint(1, self.height - 3)
                if self._is_valid_position(x, y, self.obstacles1, self.obstacles2, r_flag_positions):
                    r_flag_positions.append((x, y))
                    self.r_flags.append({
                        "posX": x,
                        "posY": y,
                        "canPickup": True,
                        "mine": False
                    })
                    break
        
        # 随机生成L队玩家出生点（在左侧半场，避开障碍）
        self.l_players = []
        l_spawn_positions = []
        for i in range(self.num_players):
            while True:
                x = random.randint(1, self.width // 2 - 1)
                y = random.randint(1, self.height - 2)
                if (self._is_valid_position(x, y, self.obstacles1, self.obstacles2, l_spawn_positions) and
                    (x, y) not in self.l_targets and (x, y) not in self.l_prison):
                    l_spawn_positions.append((x, y))
                    self.l_players.append({
                        "name": f"L{i}",
                        "posX": x,
                        "posY": y,
                        "hasFlag": False,
                        "inPrison": False,
                        "team": "L"
                    })
                    break
        
        # 随机生成R队玩家出生点（在右侧半场，避开障碍）
        self.r_players = []
        r_spawn_positions = []
        for i in range(self.num_players):
            while True:
                x = random.randint(self.width // 2, self.width - 2)
                y = random.randint(1, self.height - 2)
                if (self._is_valid_position(x, y, self.obstacles1, self.obstacles2, r_spawn_positions) and
                    (x, y) not in self.r_targets and (x, y) not in self.r_prison):
                    r_spawn_positions.append((x, y))
                    self.r_players.append({
                        "name": f"R{i}",
                        "posX": x,
                        "posY": y,
                        "hasFlag": False,
                        "inPrison": False,
                        "team": "R"
                    })
                    break
        
        # 得分
        self.l_score = 0
        self.r_score = 0
        
        # 游戏时间
        self.time = 0
        self.max_time = 300  # 最大时间步数
    
    def is_on_left(self, pos):
        """判断位置是否在左侧"""
        return pos[0] < self.middle_line
    
    def list_players(self, mine, inPrison, hasFlag):
        """列出玩家"""
        players = self.l_players if mine else self.r_players
        result = []
        for p in players:
            if (inPrison is None or p["inPrison"] == inPrison) and \
               (hasFlag is None or p["hasFlag"] == hasFlag):
                result.append(p)
        return result
    
    def list_flags(self, mine, canPickup):
        """列出flag"""
        flags = self.l_flags if mine else self.r_flags
        result = []
        for f in flags:
            if canPickup is None or f.get("canPickup", True) == canPickup:
                result.append(f)
        return result
    
    def list_targets(self, mine):
        """列出目标区域"""
        return self.l_targets if mine else self.r_targets
    
    def list_prisons(self, mine):
        """列出prison区域"""
        return self.l_prison if mine else self.r_prison
    
    def _is_obstacle(self, x, y):
        """检查位置是否是障碍物"""
        # 检查单格障碍
        if (x, y) in self.obstacles1:
            return True
        # 检查双格障碍（占用y和y+1）
        if (x, y) in self.obstacles2 or (x, y - 1) in self.obstacles2:
            return True
        return False
    
    def apply_action(self, player_name, direction):
        """应用动作"""
        # 找到玩家
        player = None
        for p in self.l_players + self.r_players:
            if p["name"] == player_name:
                player = p
                break
        
        if not player or player["inPrison"]:
            return
        
        # 计算新位置
        dx, dy = 0, 0
        if direction == "up":
            dy = -1
        elif direction == "down":
            dy = 1
        elif direction == "left":
            dx = -1
        elif direction == "right":
            dx = 1
        
        new_x = player["posX"] + dx
        new_y = player["posY"] + dy
        
        # 边界检查
        if 0 <= new_x < self.width and 0 <= new_y < self.height:
            # 检查障碍物
            if not self._is_obstacle(new_x, new_y):
                player["posX"] = new_x
                player["posY"] = new_y
        
        # 检查拾取flag
        if not player["hasFlag"]:
            enemy_flags = self.r_flags if player["team"] == "L" else self.l_flags
            for flag in enemy_flags:
                if flag["canPickup"] and (player["posX"], player["posY"]) == (flag["posX"], flag["posY"]):
                    player["hasFlag"] = True
                    flag["canPickup"] = False
                    break
        
        # 检查送达flag
        if player["hasFlag"]:
            targets = self.l_targets if player["team"] == "L" else self.r_targets
            if (player["posX"], player["posY"]) in targets:
                if player["team"] == "L":
                    self.l_score += 1
                else:
                    self.r_score += 1
                player["hasFlag"] = False
                # 重置flag
                enemy_flags = self.r_flags if player["team"] == "L" else self.l_flags
                for flag in enemy_flags:
                    if not flag["canPickup"]:
                        flag["canPickup"] = True
        
        # 检查碰撞：根据碰撞位置决定谁进监狱
        # 在己方半场：把对方送入监狱
        # 在对方半场：自己被送入监狱
        collision_pos = (player["posX"], player["posY"])
        is_collision_on_left = self.is_on_left(collision_pos)
        
        for other in (self.r_players if player["team"] == "L" else self.l_players):
            if other["name"] != player_name and not other["inPrison"]:
                if (other["posX"], other["posY"]) == collision_pos:
                    # 发生碰撞
                    if player["team"] == "L":
                        # L队：左边是己方半场，右边是对方半场
                        if is_collision_on_left:
                            # 在己方半场：把对方（R队）送入监狱
                            other["inPrison"] = True
                            if other["hasFlag"]:
                                other["hasFlag"] = False
                                # 重置flag
                                for flag in self.r_flags:
                                    if not flag["canPickup"]:
                                        flag["canPickup"] = True
                        else:
                            # 在对方半场：自己（L队）被送入监狱
                            player["inPrison"] = True
                            if player["hasFlag"]:
                                player["hasFlag"] = False
                                # 重置flag
                                for flag in self.r_flags:
                                    if not flag["canPickup"]:
                                        flag["canPickup"] = True
                    else:  # player["team"] == "R"
                        # R队：右边是己方半场，左边是对方半场
                        if not is_collision_on_left:
                            # 在己方半场：把对方（L队）送入监狱
                            other["inPrison"] = True
                            if other["hasFlag"]:
                                other["hasFlag"] = False
                                # 重置flag
                                for flag in self.l_flags:
                                    if not flag["canPickup"]:
                                        flag["canPickup"] = True
                        else:
                            # 在对方半场：自己（R队）被送入监狱
                            player["inPrison"] = True
                            if player["hasFlag"]:
                                player["hasFlag"] = False
                                # 重置flag
                                for flag in self.l_flags:
                                    if not flag["canPickup"]:
                                        flag["canPickup"] = True
                    break  # 只处理第一个碰撞的对手
    
    def step(self):
        """游戏步进"""
        self.time += 1
        return self.time >= self.max_time or self.l_score >= 3 or self.r_score >= 3
    
    def get_state_dict(self):
        """获取状态字典（用于world对象）"""
        return {
            'width': self.width,
            'height': self.height,
            'l_players': self.l_players,
            'r_players': self.r_players,
            'l_flags': self.l_flags,
            'r_flags': self.r_flags,
            'l_targets': self.l_targets,
            'r_targets': self.r_targets,
            'l_prison': self.l_prison,
            'r_prison': self.r_prison
        }


# 创建简化的world对象包装器
class SimpleWorldWrapper:
    """将SimpleGameSimulator包装成类似GameMap的对象，支持真实路径规划"""
    
    def __init__(self, simulator, team="L"):
        """
        Args:
            simulator: SimpleGameSimulator实例
            team: 当前视角的队伍 ("L" 或 "R")
        """
        self.simulator = simulator
        self.width = simulator.width
        self.height = simulator.height
        self.middle_line = simulator.middle_line
        self.team = team  # 当前视角的队伍
        
        # 路径规划所需的属性
        self.walls = set()  # 墙壁（当前为空，因为SimpleGameSimulator没有墙壁）
        # 障碍物（从simulator获取）
        self.obstacles = set()
        if hasattr(simulator, 'obstacles1'):
            self.obstacles.update(simulator.obstacles1)
        if hasattr(simulator, 'obstacles2'):
            self.obstacles.update(simulator.obstacles2)
            # obstacles2占用两个格子
            for x, y in simulator.obstacles2:
                self.obstacles.add((x, y + 1))
        
        # 目标区域（从simulator获取）
        if team == "L":
            self.my_team_target = simulator.l_targets
            self.opponent_team_target = simulator.r_targets
        else:
            self.my_team_target = simulator.r_targets
            self.opponent_team_target = simulator.l_targets
    
    def list_players(self, mine, inPrison, hasFlag):
        """根据当前视角列出玩家"""
        if self.team == "L":
            return self.simulator.list_players(mine, inPrison, hasFlag)
        else:  # R队视角：mine的含义相反
            return self.simulator.list_players(not mine if mine is not None else None, inPrison, hasFlag)
    
    def list_flags(self, mine, canPickup):
        """根据当前视角列出flag"""
        if self.team == "L":
            return self.simulator.list_flags(mine, canPickup)
        else:  # R队视角：mine的含义相反
            return self.simulator.list_flags(not mine if mine is not None else None, canPickup)
    
    def list_targets(self, mine):
        """根据当前视角列出目标"""
        if self.team == "L":
            return self.simulator.list_targets(mine)
        else:  # R队视角：mine的含义相反
            return self.simulator.list_targets(not mine if mine is not None else None)
    
    def list_prisons(self, mine):
        """根据当前视角列出prison"""
        if self.team == "L":
            return self.simulator.list_prisons(mine)
        else:  # R队视角：mine的含义相反
            return self.simulator.list_prisons(not mine if mine is not None else None)
    
    def is_on_left(self, pos):
        if isinstance(pos, tuple):
            return self.simulator.is_on_left(pos)
        elif isinstance(pos, (list, set)) and len(pos) > 0:
            # 如果是集合，取第一个元素
            first_pos = next(iter(pos))
            return self.simulator.is_on_left(first_pos)
        return pos[0] < self.middle_line if isinstance(pos, (tuple, list)) else False
    
    def route_to(self, srcXY, dstXY, extra_obstacles=None):
        """
        BFS路径搜索（与game_engine.GameMap.route_to相同）
        """
        import collections
        extras = set(extra_obstacles) if extra_obstacles else set()
        queue = collections.deque([[srcXY]])
        seen = {srcXY}
        
        while queue:
            path = queue.popleft()
            curr = path[-1]
            if curr == dstXY:
                return path

            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:  # Up, Down, Left, Right
                nxt = (curr[0] + dx, curr[1] + dy)
                if (0 <= nxt[0] < self.width and 0 <= nxt[1] < self.height and 
                    nxt not in self.walls and nxt not in self.obstacles and 
                    nxt not in extras and nxt not in seen):
                    queue.append(path + [nxt])
                    seen.add(nxt)
        return []


# 训练统计（全局变量，用于train_episode函数）
training_stats = {
    'episode': 0,
    'total_reward': 0,
    'episode_rewards': [],
    'losses': [],
    'epsilon_history': [],
    'wins': 0,
    'losses_count': 0,
    'draws': 0
}


def train_episode(l_agent, r_agent, simulator, l_world_wrapper, r_world_wrapper):
    """训练一个episode - L队和R队都使用RL策略"""
    global training_stats
    
    simulator.reset()
    l_prev_states = {}
    r_prev_states = {}
    l_episode_reward = 0
    r_episode_reward = 0
    
    while not simulator.step():
        # 获取L队玩家（训练agent）
        l_players = simulator.list_players(mine=True, inPrison=None, hasFlag=None)
        
        actions = {}
        
        # L队玩家决策（使用L agent）
        for player in l_players:
            if player["inPrison"]:
                continue
            
            player_name = player["name"]
            
            # 提取状态（使用L队视角的world wrapper）
            current_state = RL.extract_state_features(player, l_world_wrapper)
            
            # 选择动作
            action_idx = l_agent.select_action(current_state, training=True)
            
            # 获取上一帧状态
            prev_state_dict = l_prev_states.get(player_name)
            
            # 计算奖励
            reward = l_agent.calculate_reward(player, l_world_wrapper, prev_state_dict)
            l_episode_reward += reward
            
            # 存储经验
            if prev_state_dict is not None:
                prev_player = {
                    "posX": prev_state_dict["posX"],
                    "posY": prev_state_dict["posY"],
                    "hasFlag": prev_state_dict["hasFlag"],
                    "inPrison": prev_state_dict["inPrison"],
                    "team": player.get("team", ""),
                    "name": player_name
                }
                prev_state = RL.extract_state_features(prev_player, l_world_wrapper)
                
                done = player.get("inPrison", False)
                
                l_agent.replay_buffer.push(
                    prev_state,
                    action_idx,
                    reward,
                    current_state,
                    done
                )
            
            # 执行动作 - 使用真实路径规划
            action_map = {0: "defence", 1: "scoring", 2: "saving"}
            action_type = action_map[action_idx]
            
            direction = ""
            
            # 使用真实路径规划（必需）
            if action_type == "scoring":
                # 找最近的flag
                flags = simulator.list_flags(mine=False, canPickup=True)
                target_flag = flags[0] if flags else None
                direction = pf.scoring(l_world_wrapper, player, target_flag)
                
            elif action_type == "defence":
                # 找最近的敌人
                enemies = simulator.list_players(mine=False, inPrison=False, hasFlag=None)
                if enemies:
                    enemy = enemies[0]
                    direction = pf.defence(l_world_wrapper, player, enemy)
                    
            elif action_type == "saving":
                direction = pf.saving(l_world_wrapper, player)
            
            if direction:
                simulator.apply_action(player_name, direction)
            
            # 更新上一帧状态
            l_prev_states[player_name] = {
                "hasFlag": player.get("hasFlag", False),
                "inPrison": player.get("inPrison", False),
                "posX": player["posX"],
                "posY": player["posY"]
            }
        
        # R队玩家决策（使用R agent，相同策略）
        r_players = simulator.list_players(mine=False, inPrison=None, hasFlag=None)
        for player in r_players:
            if player["inPrison"]:
                continue
            
            player_name = player["name"]
            
            # 提取状态（使用R队视角的world wrapper）
            current_state = RL.extract_state_features(player, r_world_wrapper)
            
            # 选择动作
            action_idx = r_agent.select_action(current_state, training=True)
            
            # 获取上一帧状态
            prev_state_dict = r_prev_states.get(player_name)
            
            # 计算奖励
            reward = r_agent.calculate_reward(player, r_world_wrapper, prev_state_dict)
            r_episode_reward += reward
            
            # 存储经验
            if prev_state_dict is not None:
                prev_player = {
                    "posX": prev_state_dict["posX"],
                    "posY": prev_state_dict["posY"],
                    "hasFlag": prev_state_dict["hasFlag"],
                    "inPrison": prev_state_dict["inPrison"],
                    "team": player.get("team", ""),
                    "name": player_name
                }
                prev_state = RL.extract_state_features(prev_player, r_world_wrapper)
                
                done = player.get("inPrison", False)
                
                r_agent.replay_buffer.push(
                    prev_state,
                    action_idx,
                    reward,
                    current_state,
                    done
                )
            
            # 执行动作 - 使用真实路径规划（与L队相同）
            action_map = {0: "defence", 1: "scoring", 2: "saving"}
            action_type = action_map[action_idx]
            
            direction = ""
            
            # 使用真实路径规划（必需）
            if action_type == "scoring":
                flags = simulator.list_flags(mine=True, canPickup=True)
                target_flag = flags[0] if flags else None
                direction = pf.scoring(r_world_wrapper, player, target_flag)
                
            elif action_type == "defence":
                enemies = simulator.list_players(mine=True, inPrison=False, hasFlag=None)
                if enemies:
                    enemy = enemies[0]
                    direction = pf.defence(r_world_wrapper, player, enemy)
                    
            elif action_type == "saving":
                direction = pf.saving(r_world_wrapper, player)
            
            if direction:
                simulator.apply_action(player_name, direction)
            
            # 更新上一帧状态
            r_prev_states[player_name] = {
                "hasFlag": player.get("hasFlag", False),
                "inPrison": player.get("inPrison", False),
                "posX": player["posX"],
                "posY": player["posY"]
            }
        
        # 训练（每5步）- 两个agent都训练
        if len(l_agent.replay_buffer) >= 32 and len(l_agent.replay_buffer) % 5 == 0:
            loss = l_agent.train_step(batch_size=32)
            if loss is not None:
                training_stats['losses'].append(loss)
        
        if len(r_agent.replay_buffer) >= 32 and len(r_agent.replay_buffer) % 5 == 0:
            loss = r_agent.train_step(batch_size=32)
            if loss is not None:
                training_stats['losses'].append(loss)
    
    # Episode结束
    training_stats['episode'] += 1
    training_stats['total_reward'] = l_episode_reward  # 使用L队的奖励作为主要指标
    training_stats['episode_rewards'].append(l_episode_reward)
    training_stats['epsilon_history'].append(l_agent.epsilon)
    
    # 判断胜负
    if simulator.l_score > simulator.r_score:
        training_stats['wins'] += 1
        result = "WIN"
    elif simulator.l_score < simulator.r_score:
        training_stats['losses_count'] += 1
        result = "LOSS"
    else:
        training_stats['draws'] += 1
        result = "DRAW"
    
    l_agent.update_epsilon()
    r_agent.update_epsilon()
    
    return result, simulator.l_score, simulator.r_score


def worker_process(worker_id, model_queue, experience_queue, num_episodes_per_worker, state_dim, action_dim, device):
    """Worker进程：并行运行episode收集经验"""
    # 每个worker创建自己的agent和模拟器（启用Double DQN，使用相同超参数）
    l_agent = RL.DQNAgent(state_dim, action_dim,
                          lr=0.0005,
                          epsilon_decay=0.9995,
                          epsilon_end=0.05,
                          device=device, 
                          use_double_dqn=True)
    r_agent = RL.DQNAgent(state_dim, action_dim,
                          lr=0.0005,
                          epsilon_decay=0.9995,
                          epsilon_end=0.05,
                          device=device, 
                          use_double_dqn=True)
    
    simulator = SimpleGameSimulator(width=20, height=20, num_players=3, num_flags=9, 
                                    num_obstacles_1=8, num_obstacles_2=4)
    l_world_wrapper = SimpleWorldWrapper(simulator, team="L")
    r_world_wrapper = SimpleWorldWrapper(simulator, team="R")
    
    episode_count = 0
    
    while episode_count < num_episodes_per_worker:
        # 尝试从队列获取最新模型（非阻塞）
        # 注意：从0训练时，worker也会收到新训练的模型，这是正常的
        # 注意：worker加载模型时，模型会从CUDA自动转换到CPU（如果主进程使用CUDA）
        try:
            model_path = model_queue.get_nowait()
            l_agent.load_model(model_path)
            # R队也加载模型，但保持更高的探索率
            r_agent.load_model(model_path)
            r_agent.epsilon = max(r_agent.epsilon, 0.15)  # 确保R队保持高探索
        except:
            pass  # 队列为空，使用当前模型
        
        # 运行一个episode
        result, l_score, r_score, experiences = train_episode_parallel(
            l_agent, r_agent, simulator, l_world_wrapper, r_world_wrapper
        )
        
        # 将经验发送回主进程
        experience_queue.put({
            'worker_id': worker_id,
            'episode': episode_count,
            'result': result,
            'l_score': l_score,
            'r_score': r_score,
            'experiences': experiences
        })
        
        episode_count += 1


def train_episode_parallel(l_agent, r_agent, simulator, l_world_wrapper, r_world_wrapper):
    """训练一个episode并返回经验（用于并行训练）"""
    simulator.reset()
    l_prev_states = {}
    r_prev_states = {}
    l_episode_reward = 0
    r_episode_reward = 0
    experiences = []  # 收集所有经验
    
    while not simulator.step():
        # L队玩家决策
        l_players = simulator.list_players(mine=True, inPrison=None, hasFlag=None)
        for player in l_players:
            if player["inPrison"]:
                continue
            
            player_name = player["name"]
            current_state = RL.extract_state_features(player, l_world_wrapper)
            action_idx = l_agent.select_action(current_state, training=True)
            prev_state_dict = l_prev_states.get(player_name)
            reward = l_agent.calculate_reward(player, l_world_wrapper, prev_state_dict, current_action=action_idx)
            l_episode_reward += reward
            
            if prev_state_dict is not None:
                prev_player = {
                    "posX": prev_state_dict["posX"],
                    "posY": prev_state_dict["posY"],
                    "hasFlag": prev_state_dict["hasFlag"],
                    "inPrison": prev_state_dict["inPrison"],
                    "team": player.get("team", ""),
                    "name": player_name
                }
                prev_state = RL.extract_state_features(prev_player, l_world_wrapper)
                done = player.get("inPrison", False)
                
                experiences.append(('l', prev_state, action_idx, reward, current_state, done))
            
            # 执行动作 - 使用真实路径规划
            action_map = {0: "defence", 1: "scoring", 2: "saving"}
            action_type = action_map[action_idx]
            
            direction = ""
            
            # 使用真实路径规划（必需）
            if action_type == "scoring":
                flags = simulator.list_flags(mine=False, canPickup=True)
                target_flag = flags[0] if flags else None
                direction = pf.scoring(l_world_wrapper, player, target_flag)
            elif action_type == "defence":
                enemies = simulator.list_players(mine=False, inPrison=False, hasFlag=None)
                if enemies:
                    enemy = enemies[0]
                    direction = pf.defence(l_world_wrapper, player, enemy)
            elif action_type == "saving":
                direction = pf.saving(l_world_wrapper, player)
            
            if direction:
                simulator.apply_action(player_name, direction)
            
            l_prev_states[player_name] = {
                "hasFlag": player.get("hasFlag", False),
                "inPrison": player.get("inPrison", False),
                "posX": player["posX"],
                "posY": player["posY"]
            }
        
        # R队玩家决策
        r_players = simulator.list_players(mine=False, inPrison=None, hasFlag=None)
        for player in r_players:
            if player["inPrison"]:
                continue
            
            player_name = player["name"]
            current_state = RL.extract_state_features(player, r_world_wrapper)
            action_idx = r_agent.select_action(current_state, training=True)
            prev_state_dict = r_prev_states.get(player_name)
            reward = r_agent.calculate_reward(player, r_world_wrapper, prev_state_dict, current_action=action_idx)
            r_episode_reward += reward
            
            if prev_state_dict is not None:
                prev_player = {
                    "posX": prev_state_dict["posX"],
                    "posY": prev_state_dict["posY"],
                    "hasFlag": prev_state_dict["hasFlag"],
                    "inPrison": prev_state_dict["inPrison"],
                    "team": player.get("team", ""),
                    "name": player_name
                }
                prev_state = RL.extract_state_features(prev_player, r_world_wrapper)
                done = player.get("inPrison", False)
                
                experiences.append(('r', prev_state, action_idx, reward, current_state, done))
            
            # 执行动作 - 使用真实路径规划
            action_map = {0: "defence", 1: "scoring", 2: "saving"}
            action_type = action_map[action_idx]
            
            direction = ""
            
            # 使用真实路径规划（必需）
            if action_type == "scoring":
                flags = simulator.list_flags(mine=True, canPickup=True)
                target_flag = flags[0] if flags else None
                direction = pf.scoring(r_world_wrapper, player, target_flag)
            elif action_type == "defence":
                enemies = simulator.list_players(mine=True, inPrison=False, hasFlag=None)
                if enemies:
                    enemy = enemies[0]
                    direction = pf.defence(r_world_wrapper, player, enemy)
            elif action_type == "saving":
                direction = pf.saving(r_world_wrapper, player)
            
            if direction:
                simulator.apply_action(player_name, direction)
            
            r_prev_states[player_name] = {
                "hasFlag": player.get("hasFlag", False),
                "inPrison": player.get("inPrison", False),
                "posX": player["posX"],
                "posY": player["posY"]
            }
    
    # 判断胜负
    if simulator.l_score > simulator.r_score:
        result = "WIN"
    elif simulator.l_score < simulator.r_score:
        result = "LOSS"
    else:
        result = "DRAW"
    
    return result, simulator.l_score, simulator.r_score, experiences


def evaluate_model(current_agent, best_agent, num_games=10):
    """
    评估模型：运行指定数量的比赛，返回胜率
    Args:
        current_agent: 当前要评估的模型
        best_agent: 历史最佳模型（作为对手）
        num_games: 评估比赛数量
    Returns:
        (win_rate, wins, losses, draws): 胜率、胜利数、失败数、平局数
    """
    state_dim = 19
    action_dim = 3
    
    # 创建评估用的模拟器和world wrapper
    simulator = SimpleGameSimulator(width=20, height=20, num_players=3, num_flags=9, 
                                    num_obstacles_1=8, num_obstacles_2=4)
    l_world_wrapper = SimpleWorldWrapper(simulator, team="L")
    r_world_wrapper = SimpleWorldWrapper(simulator, team="R")
    
    # 创建评估用的对手agent（使用best_agent的模型）
    eval_opponent = RL.DQNAgent(state_dim, action_dim, device=current_agent.device, use_double_dqn=True)
    eval_opponent.q_network.load_state_dict(best_agent.q_network.state_dict())
    eval_opponent.target_network.load_state_dict(best_agent.target_network.state_dict())
    eval_opponent.epsilon = 0.0  # 评估时不探索，使用确定性策略
    
    # 当前模型也设置为不探索
    current_agent_eval = RL.DQNAgent(state_dim, action_dim, device=current_agent.device, use_double_dqn=True)
    current_agent_eval.q_network.load_state_dict(current_agent.q_network.state_dict())
    current_agent_eval.target_network.load_state_dict(current_agent.target_network.state_dict())
    current_agent_eval.epsilon = 0.0  # 评估时不探索
    
    wins = 0
    losses = 0
    draws = 0
    
    # 运行评估比赛
    for game_idx in range(num_games):
        simulator.reset()
        
        while not simulator.step():
            # L队（当前模型）决策
            l_players = simulator.list_players(mine=True, inPrison=None, hasFlag=None)
            for player in l_players:
                if player["inPrison"]:
                    continue
                
                player_name = player["name"]
                current_state = RL.extract_state_features(player, l_world_wrapper)
                action_idx = current_agent_eval.select_action(current_state, training=False)
                
                # 执行动作
                action_map = {0: "defence", 1: "scoring", 2: "saving"}
                action_type = action_map[action_idx]
                direction = ""
                
                try:
                    import pathfinding_adapter as pf
                    if action_type == "scoring":
                        flags = simulator.list_flags(mine=False, canPickup=True)
                        target_flag = flags[0] if flags else None
                        if target_flag:
                            direction = pf.scoring(l_world_wrapper, player, target_flag)
                    elif action_type == "defence":
                        enemies = simulator.list_players(mine=False, inPrison=False, hasFlag=None)
                        if enemies:
                            enemy = enemies[0]
                            direction = pf.defence(l_world_wrapper, player, enemy)
                    elif action_type == "saving":
                        direction = pf.saving(l_world_wrapper, player)
                except:
                    pass
                
                if direction:
                    simulator.apply_action(player_name, direction)
            
            # R队（最佳模型）决策
            r_players = simulator.list_players(mine=False, inPrison=None, hasFlag=None)
            for player in r_players:
                if player["inPrison"]:
                    continue
                
                player_name = player["name"]
                current_state = RL.extract_state_features(player, r_world_wrapper)
                action_idx = eval_opponent.select_action(current_state, training=False)
                
                # 执行动作
                action_map = {0: "defence", 1: "scoring", 2: "saving"}
                action_type = action_map[action_idx]
                direction = ""
                
                try:
                    import pathfinding_adapter as pf
                    if action_type == "scoring":
                        flags = simulator.list_flags(mine=True, canPickup=True)
                        target_flag = flags[0] if flags else None
                        if target_flag:
                            direction = pf.scoring(r_world_wrapper, player, target_flag)
                    elif action_type == "defence":
                        enemies = simulator.list_players(mine=True, inPrison=False, hasFlag=None)
                        if enemies:
                            enemy = enemies[0]
                            direction = pf.defence(r_world_wrapper, player, enemy)
                    elif action_type == "saving":
                        direction = pf.saving(r_world_wrapper, player)
                except:
                    pass
                
                if direction:
                    simulator.apply_action(player_name, direction)
        
        # 判断胜负
        if simulator.l_score > simulator.r_score:
            wins += 1
        elif simulator.l_score < simulator.r_score:
            losses += 1
        else:
            draws += 1
    
    win_rate = wins / num_games * 100
    return win_rate, wins, losses, draws


def main():
    """主函数 - 并行训练版本"""
    print("=" * 60)
    print("并行训练模式 - 多进程加速")
    print("L队和R队使用相同RL策略对打")
    print("=" * 60)
    
    # ========== 训练配置选项 ==========
    # 是否从已有模型继续训练（False=从0开始，True=从已有模型继续）
    LOAD_EXISTING_MODEL = False # 设置为False从0开始训练，True从已有模型继续
    
    # 配置
    num_workers = multiprocessing.cpu_count()  # 使用所有CPU核心
    print(f"使用 {num_workers} 个worker进程并行训练")
    
    state_dim = 19
    action_dim = 3
    
    # 自动检测并使用CUDA（如果可用）
    import torch
    if torch.cuda.is_available():
        device = 'cuda'
        print(f"✅ 使用CUDA加速训练 (设备: {torch.cuda.get_device_name(0)})")
        print(f"   CUDA版本: {torch.version.cuda}")
        print(f"   可用GPU数量: {torch.cuda.device_count()}")
    else:
        device = 'cpu'
        print("ℹ️  使用CPU训练（CUDA不可用）")
    
    if LOAD_EXISTING_MODEL:
        print("✅ 训练模式: 从已有模型继续训练")
    else:
        print("🆕 训练模式: 从0开始训练（不加载已有模型）")
    
    # 创建主agent（启用Double DQN，调整超参数）
    # L队：当前最新策略（训练目标）
    l_agent = RL.DQNAgent(state_dim, action_dim, 
                          lr=0.0005,  # 降低学习率（从0.001降到0.0005）
                          epsilon_decay=0.9995,  # 减慢epsilon衰减（从0.995到0.9995）
                          epsilon_end=0.05,  # 提高最小epsilon（从0.01到0.05，保持更多探索）
                          device=device, 
                          use_double_dqn=True)
    
    # R队：使用更高的探索率，增加策略多样性
    r_agent = RL.DQNAgent(state_dim, action_dim,
                          lr=0.0005,
                          epsilon_decay=0.9995,
                          epsilon_end=0.15,  # R队保持更高探索（0.15 vs 0.05）
                          epsilon_start=1.0,  # 重新开始探索
                          device=device, 
                          use_double_dqn=True)
    r_agent.epsilon = 0.2  # R队初始epsilon更高，保持更多探索
    
    print("✅ 使用Double DQN算法（减少Q值过估计）")
    print("✅ 超参数调整：lr=0.0005, epsilon_decay=0.9995")
    print("✅ 策略多样性：L队epsilon_end=0.05, R队epsilon_end=0.15（更高探索）")
    
    # 初始化最佳模型（用于评估对比）
    best_model_path = "lib/models/dqn_model_final.pth"
    best_win_rate = 0.0  # 历史最佳胜率
    best_agent = RL.DQNAgent(state_dim, action_dim, device=device, use_double_dqn=True)
    if os.path.exists(best_model_path):
        best_agent.load_model(best_model_path)
        print(f"✅ 加载历史最佳模型: {best_model_path}")
    else:
        # 初始时，当前模型就是最佳模型
        best_agent.q_network.load_state_dict(l_agent.q_network.state_dict())
        best_agent.target_network.load_state_dict(l_agent.target_network.state_dict())
        print(f"🆕 初始化最佳模型（使用当前模型）")
    
    # 加载模型（根据配置决定是否加载）
    model_path = "./lib/models/dqn_model_latest.pth"
    if LOAD_EXISTING_MODEL and os.path.exists(model_path):
        l_agent.load_model(model_path)
        r_agent.load_model(model_path)
        # R队加载后保持高探索率（策略多样性）
        r_agent.epsilon = max(r_agent.epsilon, 0.2)
        print(f"✅ 加载已有模型: {model_path}")
        print(f"  R队初始epsilon: {r_agent.epsilon:.3f} (保持高探索以实现策略多样性)")
    else:
        if LOAD_EXISTING_MODEL:
            print(f"⚠️  模型文件不存在: {model_path}，使用随机初始化的模型")
        else:
            print("🆕 从0开始训练，使用随机初始化的模型")
        # 确保R队初始高探索
        r_agent.epsilon = 0.2
    
    # 创建队列
    model_queue = Queue()  # 用于向worker发送模型更新
    experience_queue = Queue()  # 用于接收worker的经验
    
    # 对手池：存储历史模型路径（每500个episode保存一次）
    opponent_pool = []
    opponent_pool_dir = "lib/models/opponent_pool"
    os.makedirs(opponent_pool_dir, exist_ok=True)
    
    # 加载已有的对手池模型
    if os.path.exists(opponent_pool_dir):
        existing_models = sorted([f for f in os.listdir(opponent_pool_dir) if f.endswith('.pth')])
        for model_file in existing_models[-10:]:  # 只加载最近10个
            opponent_pool.append(os.path.join(opponent_pool_dir, model_file))
    
    print(f"✅ 对手池已初始化: {opponent_pool_dir} (已有 {len(opponent_pool)} 个模型)")
    
    # 策略多样性配置
    strategy_diversity_config = {
        'use_opponent_pool_prob': 0.5,  # 50%概率使用对手池
        'use_high_exploration_prob': 0.3,  # 30%概率使用高探索率
        'use_current_model_prob': 0.2,  # 20%概率使用当前模型（但不同epsilon）
        'opponent_switch_freq': 5,  # 每5个episode切换一次策略
    }
    last_strategy_switch = 0
    current_r_strategy = 'current'  # 'current', 'opponent_pool', 'high_exploration'
    
    # 启动worker进程
    workers = []
    for i in range(num_workers):
        p = Process(target=worker_process, args=(
            i, model_queue, experience_queue, 
            1000,  # 每个worker运行1000个episode（或直到主进程停止）
            state_dim, action_dim, device
        ))
        p.start()
        workers.append(p)
        print(f"启动worker {i}")
    
    # 训练配置
    MAX_EPISODES = 10000  # 最大训练次数
    TARGET_WIN_RATE = 80.0  # 目标胜率
    
    print(f"\n开始长期并行训练...")
    print(f"🎯 训练目标：胜率 >= {TARGET_WIN_RATE}%")
    print(f"📊 最大训练次数：{MAX_EPISODES} episodes")
    print(f"💾 保存频率：每1000个episode")
    print(f"⏸️  按 Ctrl+C 可手动停止")
    print("=" * 60)
    
    # 初始化训练统计（在main函数中）
    training_stats = {
        'episode': 0,
        'total_reward': 0,
        'episode_rewards': [],
        'losses': [],
        'epsilon_history': [],
        'wins': 0,
        'losses_count': 0,
        'draws': 0
    }
    
    # 评估窗口：用于计算最近10个episode的胜率
    evaluation_window = []  # 存储最近10个episode的结果 ["WIN", "LOSS", "DRAW", ...]
    EVALUATION_WINDOW_SIZE = 10  # 评估窗口大小
    
    try:
        episode = 0
        while True:
            # 收集经验
            batch_experiences = []
            for _ in range(num_workers):  # 从每个worker收集一个episode
                try:
                    data = experience_queue.get(timeout=10)
                    batch_experiences.append(data)
                except:
                    continue
            
            # 将经验添加到主agent的replay buffer
            for data in batch_experiences:
                for exp in data['experiences']:
                    team, prev_state, action, reward, next_state, done = exp
                    if team == 'l':
                        l_agent.replay_buffer.push(prev_state, action, reward, next_state, done)
                    else:
                        r_agent.replay_buffer.push(prev_state, action, reward, next_state, done)
                
                # 更新统计
                episode += 1
                training_stats['episode'] = episode
                if data['result'] == "WIN":
                    training_stats['wins'] += 1
                elif data['result'] == "LOSS":
                    training_stats['losses_count'] += 1
                else:
                    training_stats['draws'] += 1
                
                # 更新评估窗口（用于计算最近10个episode的胜率）
                evaluation_window.append(data['result'])
                if len(evaluation_window) > EVALUATION_WINDOW_SIZE:
                    evaluation_window.pop(0)  # 保持窗口大小为10
            
            # 训练
            if len(l_agent.replay_buffer) >= 32:
                for _ in range(min(10, len(batch_experiences))):  # 训练多次
                    loss = l_agent.train_step(batch_size=32)
                    if loss is not None:
                        training_stats['losses'].append(loss)
                
                for _ in range(min(10, len(batch_experiences))):
                    loss = r_agent.train_step(batch_size=32)
                    if loss is not None:
                        training_stats['losses'].append(loss)
            
            # 策略多样性：定期切换R队的策略
            if episode - last_strategy_switch >= strategy_diversity_config['opponent_switch_freq']:
                rand = random.random()
                if rand < strategy_diversity_config['use_opponent_pool_prob'] and len(opponent_pool) > 0:
                    # 使用对手池中的历史模型
                    selected_opponent = random.choice(opponent_pool)
                    try:
                        r_agent.load_model(selected_opponent)
                        # 保持较高的探索率
                        r_agent.epsilon = max(r_agent.epsilon, 0.15)
                        current_r_strategy = 'opponent_pool'
                        print(f"  🎯 R队策略切换: 使用历史对手 {os.path.basename(selected_opponent)} (epsilon={r_agent.epsilon:.3f})")
                    except Exception as e:
                        print(f"  ⚠️  加载对手模型失败: {e}")
                        current_r_strategy = 'current'
                elif rand < strategy_diversity_config['use_opponent_pool_prob'] + strategy_diversity_config['use_high_exploration_prob']:
                    # 使用当前模型但提高探索率
                    latest_path = "lib/models/dqn_model_latest.pth"
                    if os.path.exists(latest_path):
                        r_agent.load_model(latest_path)
                    r_agent.epsilon = max(r_agent.epsilon, 0.2)  # 强制高探索
                    current_r_strategy = 'high_exploration'
                    print(f"  🎯 R队策略切换: 高探索模式 (epsilon={r_agent.epsilon:.3f})")
                else:
                    # 使用当前模型，但保持不同epsilon
                    latest_path = "lib/models/dqn_model_latest.pth"
                    if os.path.exists(latest_path):
                        r_agent.load_model(latest_path)
                    r_agent.epsilon = max(r_agent.epsilon, 0.1)  # 中等探索
                    current_r_strategy = 'current'
                    print(f"  🎯 R队策略切换: 当前模型 (epsilon={r_agent.epsilon:.3f})")
                
                last_strategy_switch = episode
            
            # 定期同步L队模型到worker（无论是否从0训练，都保存模型供后续使用）
            if episode % 10 == 0:
                latest_path = "lib/models/dqn_model_latest.pth"
                l_agent.save_model(latest_path)
                # 向所有worker发送模型更新（从0训练时，worker也会收到新训练的模型）
                for _ in range(num_workers):
                    model_queue.put(latest_path)
            
            # 更新epsilon（但R队保持更高探索）
            if episode % 10 == 0:
                l_agent.update_epsilon()
                # R队也更新epsilon，但确保不低于最小值
                r_agent.update_epsilon()
                r_agent.epsilon = max(r_agent.epsilon, r_agent.epsilon_end)  # 确保不低于epsilon_end
            
            # 打印统计（每10个episode）
            if episode % 10 == 0:
                avg_loss = sum(training_stats['losses'][-10:]) / min(10, len(training_stats['losses'])) if training_stats['losses'] else 0
                total_games = training_stats['wins'] + training_stats['losses_count'] + training_stats['draws']
                win_rate = training_stats['wins'] / max(1, total_games) * 100
                win_display = f"{training_stats['wins']}W/{training_stats['losses_count']}L/{training_stats['draws']}D (累积)"
                
                print(f"\nEpisode {episode} (并行)")
                print(f"  平均损失: {avg_loss:.4f} | L队Epsilon: {l_agent.epsilon:.4f} | R队Epsilon: {r_agent.epsilon:.4f}")
                print(f"  R队策略: {current_r_strategy} | 累积胜率: {win_rate:.1f}% ({win_display}) [目标: {TARGET_WIN_RATE}%] | 进度: {episode}/{MAX_EPISODES}")
            
            # 模型评估（每1000个episode）
            if episode % 1000 == 0 and episode > 0:
                avg_loss = sum(training_stats['losses'][-100:]) / min(100, len(training_stats['losses'])) if training_stats['losses'] else 0
                
                # 进行模型评估：运行10次比赛与最佳模型对比
                print(f"\n{'='*60}")
                print(f"Episode {episode} - 模型评估中...")
                print(f"{'='*60}")
                
                eval_win_rate, eval_wins, eval_losses, eval_draws = evaluate_model(l_agent, best_agent, num_games=10)
                
                print(f"  评估结果: {eval_win_rate:.1f}% ({eval_wins}W/{eval_losses}L/{eval_draws}D) vs 最佳模型")
                print(f"  历史最佳胜率: {best_win_rate:.1f}%")
                
                # 如果当前模型更好，更新最佳模型
                if eval_win_rate > best_win_rate:
                    best_win_rate = eval_win_rate
                    best_agent.q_network.load_state_dict(l_agent.q_network.state_dict())
                    best_agent.target_network.load_state_dict(l_agent.target_network.state_dict())
                    os.makedirs("models", exist_ok=True)
                    best_agent.save_model(best_model_path)
                    print(f"  🎉 新最佳模型！胜率: {best_win_rate:.1f}% (已保存到 {best_model_path})")
                else:
                    print(f"  ℹ️  当前模型未超越历史最佳")
                
                print(f"{'='*60}")
                
                # 使用评估胜率进行判断
                win_rate = eval_win_rate
                win_display = f"{eval_wins}W/{eval_losses}L/{eval_draws}D (评估10局)"
                
                print(f"\nEpisode {episode} (评估结果)")
                print(f"  平均损失: {avg_loss:.4f} | L队Epsilon: {l_agent.epsilon:.4f} | R队Epsilon: {r_agent.epsilon:.4f}")
                print(f"  评估胜率: {win_rate:.1f}% ({win_display}) [目标: {TARGET_WIN_RATE}%] | 进度: {episode}/{MAX_EPISODES}")
                
                # 检查是否达到最大训练次数
                if episode >= MAX_EPISODES:
                    print("\n" + "=" * 60)
                    print("📊 达到最大训练次数！")
                    print("=" * 60)
                    print(f"当前Episode: {episode} / {MAX_EPISODES}")
                    print(f"当前胜率: {win_rate:.1f}% (目标: {TARGET_WIN_RATE}%)")
                    print(f"总游戏数: {total_games}")
                    print("=" * 60)
                    print("\n正在保存最终模型并停止训练...")
                    
                    # 保存最终模型
                    os.makedirs("models", exist_ok=True)
                    final_path = f"lib/models/dqn_model_final_ep{episode}.pth"
                    l_agent.save_model(final_path)
                    latest_path = "lib/models/dqn_model_latest.pth"
                    l_agent.save_model(latest_path)
                    
                    stats_path = "lib/models/training_stats.json"
                    with open(stats_path, 'w') as f:
                        json.dump(training_stats, f, indent=2)
                    
                    print(f"✅ 最终模型已保存: {final_path}")
                    print(f"✅ 训练统计已保存: {stats_path}")
                    
                    # 停止所有worker
                    print("\n正在停止worker进程...")
                    for p in workers:
                        p.terminate()
                        p.join()
                    
                    if win_rate >= TARGET_WIN_RATE:
                        print(f"\n🎉 训练完成！模型已达到{TARGET_WIN_RATE}%胜率目标。")
                    else:
                        print(f"\n训练完成！当前胜率 {win_rate:.1f}%，未达到 {TARGET_WIN_RATE}% 目标。")
                    break
                
                # 检查是否达到目标胜率（80%）
                # 使用评估胜率进行判断（仅在评估时检查）
                if eval_win_rate >= TARGET_WIN_RATE:
                    print("\n" + "=" * 60)
                    print("🎉 训练目标达成！")
                    print("=" * 60)
                    print(f"胜率: {win_rate:.1f}% >= 80.0%")
                    print(f"总游戏数: {total_games}")
                    print(f"当前Episode: {episode}")
                    print("=" * 60)
                    print("\n正在保存最终模型并停止训练...")
                    
                    # 保存最终模型
                    os.makedirs("models", exist_ok=True)
                    final_path = "lib/models/dqn_model_final_winrate80.pth"
                    l_agent.save_model(final_path)
                    latest_path = "lib/models/dqn_model_latest.pth"
                    l_agent.save_model(latest_path)
                    
                    stats_path = "lib/models/training_stats.json"
                    with open(stats_path, 'w') as f:
                        json.dump(training_stats, f, indent=2)
                    
                    print(f"✅ 最终模型已保存: {final_path}")
                    print(f"✅ 训练统计已保存: {stats_path}")
                    
                    # 停止所有worker
                    print("\n正在停止worker进程...")
                    for p in workers:
                        p.terminate()
                        p.join()
                    
                    print("\n训练完成！模型已达到80%胜率目标。")
                    break
            
            # 保存模型（每1000个episode，长期训练）
            if episode % 1000 == 0 and episode > 0:
                os.makedirs("models", exist_ok=True)
                model_path = f"lib/models/dqn_model_ep{episode}.pth"
                l_agent.save_model(model_path)
                latest_path = "lib/models/dqn_model_latest.pth"
                l_agent.save_model(latest_path)
                # 从0训练时，R队不加载模型，只保持高探索率
                # 从已有模型继续时，R队加载最新模型
                if LOAD_EXISTING_MODEL:
                    r_agent.load_model(latest_path)
                r_agent.epsilon = max(r_agent.epsilon, 0.15)  # 确保R队保持高探索
                
                stats_path = "lib/models/training_stats.json"
                with open(stats_path, 'w') as f:
                    json.dump(training_stats, f, indent=2)
                
                # 计算窗口胜率
                if len(evaluation_window) >= EVALUATION_WINDOW_SIZE:
                    window_wins = evaluation_window.count("WIN")
                    window_win_rate = window_wins / EVALUATION_WINDOW_SIZE * 100
                    current_win_rate = window_win_rate
                    win_rate_info = f"窗口胜率: {current_win_rate:.1f}% (最近10局)"
                else:
                    total_games = training_stats['wins'] + training_stats['losses_count'] + training_stats['draws']
                    current_win_rate = training_stats['wins'] / max(1, total_games) * 100
                    win_rate_info = f"累积胜率: {current_win_rate:.1f}%"
                
                print(f"  ✅ 模型已保存: {latest_path}")
                print(f"  📊 {win_rate_info} (目标: {TARGET_WIN_RATE}%) | 进度: {episode}/{MAX_EPISODES}")
            
            # 对手池：每500个episode保存一次历史模型（仅当从已有模型继续训练时使用）
            if LOAD_EXISTING_MODEL and episode % 500 == 0 and episode > 0:
                opponent_model_path = f"{opponent_pool_dir}/opponent_ep{episode}.pth"
                l_agent.save_model(opponent_model_path)
                opponent_pool.append(opponent_model_path)
                print(f"  ✅ 对手池新增模型: {opponent_model_path} (池大小: {len(opponent_pool)})")
                
                # 限制对手池大小（保留最近15个模型，增加多样性）
                if len(opponent_pool) > 15:
                    old_model = opponent_pool.pop(0)
                    try:
                        os.remove(old_model)
                        print(f"  🗑️  移除旧对手模型: {old_model}")
                    except:
                        pass
    
    except KeyboardInterrupt:
        print("\n\n训练中断，正在停止worker...")
        
        # 停止所有worker
        for p in workers:
            p.terminate()
            p.join()
        
        # 计算最终胜率（优先使用窗口胜率）
        if len(evaluation_window) >= EVALUATION_WINDOW_SIZE:
            window_wins = evaluation_window.count("WIN")
            final_win_rate = window_wins / EVALUATION_WINDOW_SIZE * 100
            win_rate_type = "窗口胜率（最近10局）"
        else:
            total_games = training_stats['wins'] + training_stats['losses_count'] + training_stats['draws']
            final_win_rate = training_stats['wins'] / max(1, total_games) * 100
            win_rate_type = "累积胜率"
        
        total_games = training_stats['wins'] + training_stats['losses_count'] + training_stats['draws']
        
        # 保存最终模型
        os.makedirs("models", exist_ok=True)
        final_path = "lib/models/dqn_model_final.pth"
        l_agent.save_model(final_path)
        latest_path = "lib/models/dqn_model_latest.pth"
        l_agent.save_model(latest_path)
        
        stats_path = "lib/models/training_stats.json"
        with open(stats_path, 'w') as f:
            json.dump(training_stats, f, indent=2)
        
        print(f"\n最终统计:")
        print(f"  总Episode: {training_stats['episode']} / {MAX_EPISODES}")
        print(f"  总游戏数: {total_games}")
        print(f"  {win_rate_type}: {final_win_rate:.1f}% (目标: {TARGET_WIN_RATE}%)")
        if len(evaluation_window) >= EVALUATION_WINDOW_SIZE:
            window_wins = evaluation_window.count("WIN")
            window_losses = evaluation_window.count("LOSS")
            window_draws = evaluation_window.count("DRAW")
            print(f"  最近10局: {window_wins}W/{window_losses}L/{window_draws}D")
        print(f"  累积记录: {training_stats['wins']}W/{training_stats['losses_count']}L/{training_stats['draws']}D")
        print(f"\n✅ 最终模型已保存: {final_path}")
        print(f"✅ 训练统计已保存: {stats_path}")
        
        if final_win_rate >= TARGET_WIN_RATE:
            print(f"\n🎉 恭喜！模型已达到{TARGET_WIN_RATE}%胜率目标！")
        else:
            print(f"\n💡 当前胜率 {final_win_rate:.1f}%，继续训练可达到{TARGET_WIN_RATE}%目标")


if __name__ == "__main__":
    # 多进程需要这个保护
    multiprocessing.set_start_method('spawn', force=True)
    main()

