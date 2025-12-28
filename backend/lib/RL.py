"""
DQN强化学习实现
用于CTF游戏的决策系统
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import random
from collections import deque, namedtuple
import math
import os

# 经验元组
Experience = namedtuple('Experience', ['state', 'action', 'reward', 'next_state', 'done'])


def is_in_enemy_territory(player, position, world):
    """
    判断玩家是否在敌方领地（从server.py复制）
    """
    team = player.get("team", "")
    is_left = world.is_on_left(position)
    
    if team == "L":
        return not is_left
    elif team == "R":
        return is_left
    else:
        return False


def is_in_my_territory(position, world):
    """
    判断位置是否在我方半场
    """
    my_targets = list(world.list_targets(mine=True))
    if not my_targets:
        return False
    
    my_side_is_left = world.is_on_left(my_targets[0])
    is_left = world.is_on_left(position)
    
    return (my_side_is_left and is_left) or (not my_side_is_left and not is_left)


def extract_state_features(player, world):
    """
    提取玩家的状态特征向量
    
    Args:
        player: 玩家对象
        world: GameMap对象
    
    Returns:
        numpy array: 状态特征向量
    """
    features = []
    
    # ========== 玩家自身信息 (5维) ==========
    player_pos = (player["posX"], player["posY"])
    
    # 归一化位置 [0,1]
    player_pos_x = player["posX"] / max(world.width, 1)
    player_pos_y = player["posY"] / max(world.height, 1)
    features.extend([player_pos_x, player_pos_y])
    
    # 玩家状态
    player_has_flag = 1.0 if player.get("hasFlag", False) else 0.0
    player_in_prison = 1.0 if player.get("inPrison", False) else 0.0
    is_in_enemy_territory_val = 1.0 if is_in_enemy_territory(player, player_pos, world) else 0.0
    features.extend([player_has_flag, player_in_prison, is_in_enemy_territory_val])
    
    # ========== 目标信息 (6维: 1距离 + 4方向 + 1flag_dist) ==========
    enemy_flags = world.list_flags(mine=False, canPickup=True)
    my_targets = list(world.list_targets(mine=True))
    
    if enemy_flags:
        # 找到最近的敌方flag
        min_flag_dist = float('inf')
        nearest_flag = None
        for flag in enemy_flags:
            flag_pos = (flag["posX"], flag["posY"])
            dist = abs(player_pos[0] - flag_pos[0]) + abs(player_pos[1] - flag_pos[1])
            if dist < min_flag_dist:
                min_flag_dist = dist
                nearest_flag = flag_pos
        
        # 归一化距离（假设最大距离为地图对角线）
        max_dist = math.sqrt(world.width**2 + world.height**2)
        nearest_flag_dist = min(min_flag_dist / max_dist, 1.0) if max_dist > 0 else 0.0
        
        # 方向编码（4维one-hot）
        if nearest_flag:
            dx = nearest_flag[0] - player_pos[0]
            dy = nearest_flag[1] - player_pos[1]
            
            # 确定主要方向
            if abs(dx) > abs(dy):
                if dx > 0:
                    nearest_flag_dir = [1.0, 0.0, 0.0, 0.0]  # right
                else:
                    nearest_flag_dir = [0.0, 0.0, 1.0, 0.0]  # left
            else:
                if dy > 0:
                    nearest_flag_dir = [0.0, 1.0, 0.0, 0.0]  # down
                else:
                    nearest_flag_dir = [0.0, 0.0, 0.0, 1.0]  # up
        else:
            nearest_flag_dir = [0.0, 0.0, 0.0, 0.0]
    else:
        nearest_flag_dist = 1.0  # 没有flag，距离设为最大
        nearest_flag_dir = [0.0, 0.0, 0.0, 0.0]
    
    features.append(nearest_flag_dist)
    features.extend(nearest_flag_dir)
    
    # flag_dist: 如果玩家有flag，到目标区域的距离
    if player_has_flag and my_targets:
        target = my_targets[0]
        flag_dist = abs(player_pos[0] - target[0]) + abs(player_pos[1] - target[1])
        max_dist = math.sqrt(world.width**2 + world.height**2)
        flag_dist = min(flag_dist / max_dist, 1.0) if max_dist > 0 else 0.0
    else:
        flag_dist = 0.0
    features.append(flag_dist)
    
    # ========== 对手信息 (4维) ==========
    opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
    my_flags = world.list_flags(mine=True, canPickup=None)
    
    if opponents:
        # 找到最近的敌人
        min_enemy_dist = float('inf')
        nearest_enemy = None
        for opp in opponents:
            opp_pos = (opp["posX"], opp["posY"])
            dist = abs(player_pos[0] - opp_pos[0]) + abs(player_pos[1] - opp_pos[1])
            if dist < min_enemy_dist:
                min_enemy_dist = dist
                nearest_enemy = opp
        
        # 归一化距离
        max_dist = math.sqrt(world.width**2 + world.height**2)
        enemy_dist = min(min_enemy_dist / max_dist, 1.0) if max_dist > 0 else 0.0
        
        # enemy_danger: 根据敌人到最近己方flag的距离和是否在己方区域加权
        enemy_danger = 0.0
        if nearest_enemy and my_flags:
            enemy_pos = (nearest_enemy["posX"], nearest_enemy["posY"])
            
            # 找到敌人到最近己方flag的距离
            min_flag_dist_to_enemy = float('inf')
            for flag in my_flags:
                flag_pos = (flag["posX"], flag["posY"])
                dist = abs(enemy_pos[0] - flag_pos[0]) + abs(enemy_pos[1] - flag_pos[1])
                if dist < min_flag_dist_to_enemy:
                    min_flag_dist_to_enemy = dist
            
            # 计算危险度：距离越近危险度越高，在己方区域危险度翻倍
            in_my_territory = is_in_my_territory(enemy_pos, world)
            danger_base = 1.0 / (min_flag_dist_to_enemy + 1.0)
            territory_multiplier = 2.0 if in_my_territory else 1.0
            enemy_danger = danger_base * territory_multiplier
            # 归一化到[0,1]
            enemy_danger = min(enemy_danger / 2.0, 1.0)
        
        # 是否有敌人持旗
        enemy_has_flag = 1.0 if any(opp.get("hasFlag", False) for opp in opponents) else 0.0
    else:
        enemy_dist = 1.0  # 没有敌人，距离设为最大
        enemy_danger = 0.0
        enemy_has_flag = 0.0
    
    # 是否有敌人在prison
    enemies_in_prison = world.list_players(mine=False, inPrison=True, hasFlag=None)
    enemy_in_prison = 1.0 if enemies_in_prison else 0.0
    
    features.extend([enemy_dist, enemy_danger, enemy_has_flag, enemy_in_prison])
    
    # ========== 全局信息 (4维) ==========
    my_flags_list = world.list_flags(mine=True, canPickup=None)
    enemy_flags_list = world.list_flags(mine=False, canPickup=None)
    
    # flag数量（归一化，假设最多3个flag）
    my_flags_count = min(len(my_flags_list) / 3.0, 1.0) if my_flags_list else 0.0
    enemy_flags_count = min(len(enemy_flags_list) / 3.0, 1.0) if enemy_flags_list else 0.0
    
    # 得分（需要从flag位置推断：flag在目标区域表示得分）
    my_score = 0.0
    enemy_score = 0.0
    
    my_targets_set = world.list_targets(mine=True)
    enemy_targets_set = world.list_targets(mine=False)
    
    # 检查己方flag是否在目标区域
    for flag in my_flags_list:
        flag_pos = (flag["posX"], flag["posY"])
        if flag_pos in my_targets_set:
            my_score += 1.0
    
    # 检查敌方flag是否在目标区域
    for flag in enemy_flags_list:
        flag_pos = (flag["posX"], flag["posY"])
        if flag_pos in enemy_targets_set:
            enemy_score += 1.0
    
    # 归一化得分（假设最多3分）
    my_score = min(my_score / 3.0, 1.0)
    enemy_score = min(enemy_score / 3.0, 1.0)
    
    features.extend([my_flags_count, enemy_flags_count, my_score, enemy_score])
    
    # 验证特征向量维度
    feature_array = np.array(features, dtype=np.float32)
    expected_dim = 19  # 5(玩家) + 6(目标) + 4(对手) + 4(全局) = 19
    
    if len(feature_array) != expected_dim:
        print(f"⚠️  警告：状态特征向量维度不匹配！")
        print(f"   玩家: {player.get('name', 'unknown')}, 在prison: {player.get('inPrison', False)}")
        print(f"   期望维度: {expected_dim}, 实际维度: {len(feature_array)}")
        print(f"   特征列表: {features}")
        # 如果维度不匹配，尝试修复或抛出错误
        if len(feature_array) < expected_dim:
            # 补零
            feature_array = np.pad(feature_array, (0, expected_dim - len(feature_array)), 'constant')
        elif len(feature_array) > expected_dim:
            # 截断
            feature_array = feature_array[:expected_dim]
        print(f"   已修复为: {len(feature_array)}维")
    
    return feature_array


class DQN(nn.Module):
    """DQN神经网络模型"""
    
    def __init__(self, state_dim, action_dim, hidden_dim1=128, hidden_dim2=64):
        super(DQN, self).__init__()
        self.fc1 = nn.Linear(state_dim, hidden_dim1)
        self.fc2 = nn.Linear(hidden_dim1, hidden_dim2)
        self.fc3 = nn.Linear(hidden_dim2, action_dim)
        self.relu = nn.ReLU()
    
    def forward(self, x):
        x = self.relu(self.fc1(x))
        x = self.relu(self.fc2(x))
        x = self.fc3(x)
        return x


class ReplayBuffer:
    """经验回放缓冲区"""
    
    def __init__(self, capacity=10000):
        self.buffer = deque(maxlen=capacity)
    
    def push(self, state, action, reward, next_state, done):
        """添加经验"""
        experience = Experience(state, action, reward, next_state, done)
        self.buffer.append(experience)
    
    def sample(self, batch_size):
        """采样批次"""
        batch = random.sample(self.buffer, min(batch_size, len(self.buffer)))
        
        states = torch.FloatTensor([e.state for e in batch])
        actions = torch.LongTensor([e.action for e in batch])
        rewards = torch.FloatTensor([e.reward for e in batch])
        next_states = torch.FloatTensor([e.next_state for e in batch])
        dones = torch.BoolTensor([e.done for e in batch])
        
        return states, actions, rewards, next_states, dones
    
    def __len__(self):
        return len(self.buffer)


class DQNAgent:
    """DQN智能体"""
    
    def __init__(self, state_dim, action_dim, lr=0.001, gamma=0.99, 
                 epsilon_start=1.0, epsilon_end=0.01, epsilon_decay=0.995,
                 target_update_freq=100, device='cpu', use_double_dqn=True):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.epsilon = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.target_update_freq = target_update_freq
        self.device = device
        self.use_double_dqn = use_double_dqn  # 是否使用Double DQN
        
        # 创建网络
        self.q_network = DQN(state_dim, action_dim).to(device)
        self.target_network = DQN(state_dim, action_dim).to(device)
        self.target_network.load_state_dict(self.q_network.state_dict())
        self.target_network.eval()
        
        # 优化器
        self.optimizer = optim.Adam(self.q_network.parameters(), lr=lr)
        
        # 经验回放
        self.replay_buffer = ReplayBuffer()
        
        # 训练步数（使用training_step避免与方法名冲突）
        self.training_step = 0
        
        # 上一帧状态（用于奖励计算）
        self.prev_states = {}  # {player_name: state_dict}
    
    def select_action(self, state, training=True):
        """选择动作（epsilon-greedy）"""
        if training and random.random() < self.epsilon:
            return random.randint(0, self.action_dim - 1)
        
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.q_network(state_tensor)
            return q_values.argmax().item()
    
    def update_epsilon(self):
        """更新epsilon"""
        if self.epsilon > self.epsilon_end:
            self.epsilon *= self.epsilon_decay
    
    def train_step(self, batch_size=32):
        """训练一步"""
        if len(self.replay_buffer) < batch_size:
            return None
        
        # 采样批次
        states, actions, rewards, next_states, dones = self.replay_buffer.sample(batch_size)
        states = states.to(self.device)
        actions = actions.to(self.device)
        rewards = rewards.to(self.device)
        next_states = next_states.to(self.device)
        dones = dones.to(self.device)
        
        # 当前Q值
        q_values = self.q_network(states).gather(1, actions.unsqueeze(1))
        
        # 目标Q值 - 使用Double DQN
        with torch.no_grad():
            if self.use_double_dqn:
                # Double DQN: 使用主网络选择动作，target network评估Q值
                # 这样可以减少过估计问题
                next_actions = self.q_network(next_states).argmax(1)  # 主网络选择动作
                next_q_values = self.target_network(next_states).gather(1, next_actions.unsqueeze(1)).squeeze(1)  # target network评估
            else:
                # 标准DQN: 使用target network选择动作和评估Q值
                next_q_values = self.target_network(next_states).max(1)[0]
            
            target_q_values = rewards + (self.gamma * next_q_values * ~dones)
        
        # 计算损失
        loss = nn.MSELoss()(q_values.squeeze(), target_q_values)
        
        # 反向传播
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        
        # 更新target network
        self.training_step += 1
        if self.training_step % self.target_update_freq == 0:
            self.target_network.load_state_dict(self.q_network.state_dict())
        
        return loss.item()
    
    def save_model(self, path):
        """保存模型"""
        torch.save({
            'q_network': self.q_network.state_dict(),
            'target_network': self.target_network.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'training_step': self.training_step,
            'use_double_dqn': self.use_double_dqn
        }, path)
    
    def load_model(self, path):
        """加载模型"""
        # 使用map_location确保模型加载到正确的设备
        checkpoint = torch.load(path, map_location=self.device)
        self.q_network.load_state_dict(checkpoint['q_network'])
        self.target_network.load_state_dict(checkpoint['target_network'])
        # 确保网络在正确的设备上
        self.q_network = self.q_network.to(self.device)
        self.target_network = self.target_network.to(self.device)
        self.optimizer.load_state_dict(checkpoint['optimizer'])
        self.epsilon = checkpoint.get('epsilon', self.epsilon_end)
        self.training_step = checkpoint.get('training_step', checkpoint.get('train_step', 0))  # 兼容旧版本
        # 兼容旧模型（可能没有use_double_dqn字段）
        if 'use_double_dqn' in checkpoint:
            self.use_double_dqn = checkpoint['use_double_dqn']
        self.target_network.eval()
    
    def calculate_reward(self, player, world, prev_state_dict=None, current_action=None):
        """
        计算奖励
        
        Args:
            player: 当前玩家对象
            world: GameMap对象
            prev_state_dict: 上一帧的状态字典 {hasFlag, inPrison, posX, posY, ...}
            current_action: 当前选择的动作 (0=defence, 1=scoring, 2=saving) 或 None
        
        Returns:
            float: 奖励值
        """
        reward = 0.0
        
        if prev_state_dict is None:
            # 第一帧，只有步惩罚
            reward = -0.1
            return reward
        
        # 步惩罚
        reward -= 0.1
        
        # 检测事件
        current_has_flag = player.get("hasFlag", False)
        prev_has_flag = prev_state_dict.get("hasFlag", False)
        current_in_prison = player.get("inPrison", False)
        prev_in_prison = prev_state_dict.get("inPrison", False)
        
        # pick_flag: 玩家刚获得flag（降低奖励）
        if current_has_flag and not prev_has_flag:
            reward += 5.0  # 从10.0降低到5.0
        
        # lose_flag: 玩家失去flag
        if not current_has_flag and prev_has_flag:
            reward -= 50.0
        
        # get_caught: 玩家被捕获
        if current_in_prison and not prev_in_prison:
            reward -= 30.0
        
        # score_flag: 检测flag是否到达目标区域
        # 通过检查flag位置是否在目标区域
        if prev_has_flag:
            prev_pos = (prev_state_dict.get("posX"), prev_state_dict.get("posY"))
            current_pos = (player["posX"], player["posY"])
            my_targets = world.list_targets(mine=True)
            
            # 如果上一帧不在目标区域，当前帧在目标区域
            prev_in_target = prev_pos in my_targets
            current_in_target = current_pos in my_targets
            
            if current_in_target and not prev_in_target:
                reward += 100.0
        
        # ========== 基于动作的奖励调整 ==========
        if current_action is not None:
            player_pos = (player["posX"], player["posY"])
            
            # 1. 防御决策奖励：有敌人在己方领地时，选择防御动作给予奖励
            if current_action == 0:  # defence
                opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
                my_targets = list(world.list_targets(mine=True))
                
                if my_targets:
                    my_side_is_left = world.is_on_left(my_targets[0])
                    
                    # 检查是否有敌人在己方领地
                    enemies_in_my_territory = []
                    for opp in opponents:
                        opp_pos = (opp["posX"], opp["posY"])
                        is_left = world.is_on_left(opp_pos)
                        in_my_territory = (my_side_is_left and is_left) or (not my_side_is_left and not is_left)
                        if in_my_territory:
                            enemies_in_my_territory.append(opp)
                    
                    # 如果有敌人在己方领地，选择防御动作给予奖励
                    if enemies_in_my_territory:
                        # 检查是否有其他己方玩家也在防御（避免重复）
                        my_players = world.list_players(mine=True, inPrison=False, hasFlag=None)
                        other_defenders = 0
                        for p in my_players:
                            if p["name"] != player.get("name", ""):
                                # 这里无法直接知道其他玩家的动作，所以只基于当前玩家
                                # 奖励所有在己方领地选择防御的玩家
                                pass
                        
                        # 给予防御奖励（鼓励至少有一个玩家防御）
                        reward += 15.0  # 增加防御决策奖励
                        
                        # 如果玩家距离敌人很近，额外奖励
                        min_enemy_dist = float('inf')
                        for enemy in enemies_in_my_territory:
                            enemy_pos = (enemy["posX"], enemy["posY"])
                            dist = abs(player_pos[0] - enemy_pos[0]) + abs(player_pos[1] - enemy_pos[1])
                            if dist < min_enemy_dist:
                                min_enemy_dist = dist
                        
                        if min_enemy_dist <= 3:
                            reward += 5.0  # 距离敌人很近时额外奖励
            
            # 2. 拿旗决策奖励：降低奖励（已在pick_flag中降低）
            if current_action == 1:  # scoring
                # pick_flag的奖励已经从10.0降低到5.0
                # 这里可以进一步降低距离奖励
                if not current_has_flag:
                    enemy_flags = world.list_flags(mine=False, canPickup=True)
                    if enemy_flags:
                        min_dist = float('inf')
                        for flag in enemy_flags:
                            flag_pos = (flag["posX"], flag["posY"])
                            dist = abs(player_pos[0] - flag_pos[0]) + abs(player_pos[1] - flag_pos[1])
                            if dist < min_dist:
                                min_dist = dist
                        
                        # 降低距离奖励（从-0.01改为-0.005）
                        reward -= 0.005 * min_dist
            
            # 3. 救人决策奖励：场上仅有一个己方玩家时，增加奖励
            if current_action == 2:  # saving
                my_players_all = world.list_players(mine=True, inPrison=None, hasFlag=None)
                my_players_active = world.list_players(mine=True, inPrison=False, hasFlag=None)
                my_players_in_prison = world.list_players(mine=True, inPrison=True, hasFlag=None)
                
                # 如果场上只有一个己方玩家（且不在prison中），且有队友在prison中
                if len(my_players_active) == 1 and len(my_players_in_prison) > 0:
                    reward += 20.0  # 大幅增加救人奖励
                elif len(my_players_active) <= 2 and len(my_players_in_prison) > 0:
                    reward += 10.0  # 场上玩家较少时也给予奖励
        
        # distance_to_flag: 基于距离的连续奖励（仅在未指定动作时使用）
        if current_action is None and not current_has_flag:
            enemy_flags = world.list_flags(mine=False, canPickup=True)
            if enemy_flags:
                player_pos = (player["posX"], player["posY"])
                min_dist = float('inf')
                for flag in enemy_flags:
                    flag_pos = (flag["posX"], flag["posY"])
                    dist = abs(player_pos[0] - flag_pos[0]) + abs(player_pos[1] - flag_pos[1])
                    if dist < min_dist:
                        min_dist = dist
                
                # 距离越近奖励越高
                reward -= 0.01 * min_dist
        
        return reward
    
    def predict_schedule(self, players, world, training=False):
        """
        预测决策表（快速推理，<0.1秒）
        
        Args:
            players: 己方玩家列表
            world: GameMap对象
            training: 是否处于训练模式
        
        Returns:
            dict: 决策表 {player_name + "schedule": (action_type, player, target)}
        """
        schedule = {}
        
        # 获取所有相关信息
        opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
        enemy_flags = world.list_flags(mine=False, canPickup=True)
        my_players_in_prison = world.list_players(mine=True, inPrison=True, hasFlag=None)
        
        # 批量提取状态特征
        states = []
        valid_players = []
        
        for player in players:
            if player.get("inPrison", False):
                continue  # 跳过在prison中的玩家
            
            state = extract_state_features(player, world)
            # 验证状态维度
            if len(state) != 19:
                print(f"⚠️  警告：玩家 {player.get('name', 'unknown')} 的状态维度错误: {len(state)} (期望19)")
                continue  # 跳过维度不正确的状态
            
            states.append(state)
            valid_players.append(player)
        
        if not states:
            return schedule
        
        # 批量推理（加速）
        with torch.no_grad():
            states_tensor = torch.FloatTensor(np.array(states)).to(self.device)
            q_values = self.q_network(states_tensor)
            actions = q_values.argmax(dim=1).cpu().numpy()
        
        # 检查是否有敌人在己方领地（需要至少一个玩家防御）
        my_targets = list(world.list_targets(mine=True))
        enemies_in_my_territory = []
        if my_targets:
            my_side_is_left = world.is_on_left(my_targets[0])
            for opp in opponents:
                opp_pos = (opp["posX"], opp["posY"])
                is_left = world.is_on_left(opp_pos)
                in_my_territory = (my_side_is_left and is_left) or (not my_side_is_left and not is_left)
                if in_my_territory:
                    enemies_in_my_territory.append(opp)
        
        # 为每个玩家分配任务
        assigned_enemies = set()
        assigned_flags = set()
        has_defender = False  # 记录是否已有玩家选择防御
        
        for i, player in enumerate(valid_players):
            action = actions[i]
            player_name = player["name"]
            
            if action == 0:  # defence
                # 找到最近的敌人（优先选择己方领地内的敌人）
                best_opponent = None
                min_dist = float('inf')
                player_pos = (player["posX"], player["posY"])
                
                # 优先选择己方领地内的敌人
                for opp in opponents:
                    if opp["name"] in assigned_enemies:
                        continue
                    opp_pos = (opp["posX"], opp["posY"])
                    dist = abs(player_pos[0] - opp_pos[0]) + abs(player_pos[1] - opp_pos[1])
                    
                    # 如果敌人在己方领地，优先选择
                    if my_targets:
                        my_side_is_left = world.is_on_left(my_targets[0])
                        is_left = world.is_on_left(opp_pos)
                        in_my_territory = (my_side_is_left and is_left) or (not my_side_is_left and not is_left)
                        if in_my_territory and (best_opponent is None or dist < min_dist):
                            min_dist = dist
                            best_opponent = opp
                
                # 如果没有找到己方领地的敌人，选择最近的敌人
                if best_opponent is None:
                    for opp in opponents:
                        if opp["name"] in assigned_enemies:
                            continue
                        opp_pos = (opp["posX"], opp["posY"])
                        dist = abs(player_pos[0] - opp_pos[0]) + abs(player_pos[1] - opp_pos[1])
                        if dist < min_dist:
                            min_dist = dist
                            best_opponent = opp
                
                if best_opponent:
                    schedule[f"{player_name}schedule"] = ("defence", player, best_opponent)
                    assigned_enemies.add(best_opponent["name"])
                    has_defender = True
                else:
                    # 所有敌方都在prison，无法防御，转换为scoring动作
                    # 找到最近的flag或目标
                    if player.get("hasFlag", False):
                        # 有flag，返回目标区域
                        my_targets = list(world.list_targets(mine=True))
                        if my_targets:
                            schedule[f"{player_name}schedule"] = ("scoring", player, my_targets[0])
                    else:
                        # 无flag，找最近的敌方flag
                        best_flag = None
                        min_dist = float('inf')
                        player_pos = (player["posX"], player["posY"])
                        
                        for flag in enemy_flags:
                            flag_pos = (flag["posX"], flag["posY"])
                            if flag_pos in assigned_flags:
                                continue
                            dist = abs(player_pos[0] - flag_pos[0]) + abs(player_pos[1] - flag_pos[1])
                            if dist < min_dist:
                                min_dist = dist
                                best_flag = flag
                        
                        if best_flag:
                            schedule[f"{player_name}schedule"] = ("scoring", player, best_flag)
                            assigned_flags.add((best_flag["posX"], best_flag["posY"]))
                        elif my_players_in_prison:
                            # 如果没有flag可拿，且队友在prison，改为saving
                            schedule[f"{player_name}schedule"] = ("saving", player, None)
            
            # 如果有敌人在己方领地但没有玩家选择防御，强制第一个玩家选择防御
            elif enemies_in_my_territory and not has_defender and i == 0:
                # 强制第一个玩家选择防御
                best_opponent = None
                min_dist = float('inf')
                player_pos = (player["posX"], player["posY"])
                
                for opp in enemies_in_my_territory:
                    if opp["name"] in assigned_enemies:
                        continue
                    opp_pos = (opp["posX"], opp["posY"])
                    dist = abs(player_pos[0] - opp_pos[0]) + abs(player_pos[1] - opp_pos[1])
                    if dist < min_dist:
                        min_dist = dist
                        best_opponent = opp
                
                if best_opponent:
                    schedule[f"{player_name}schedule"] = ("defence", player, best_opponent)
                    assigned_enemies.add(best_opponent["name"])
                    has_defender = True
                    continue  # 跳过原来的动作分配
            
            elif action == 1:  # scoring
                # 找到最近的flag或目标
                if player.get("hasFlag", False):
                    # 有flag，返回目标区域
                    my_targets = list(world.list_targets(mine=True))
                    if my_targets:
                        schedule[f"{player_name}schedule"] = ("scoring", player, my_targets[0])
                else:
                    # 无flag，找最近的敌方flag
                    best_flag = None
                    min_dist = float('inf')
                    player_pos = (player["posX"], player["posY"])
                    
                    for flag in enemy_flags:
                        flag_pos = (flag["posX"], flag["posY"])
                        if flag_pos in assigned_flags:
                            continue
                        dist = abs(player_pos[0] - flag_pos[0]) + abs(player_pos[1] - flag_pos[1])
                        if dist < min_dist:
                            min_dist = dist
                            best_flag = flag
                    
                    if best_flag:
                        schedule[f"{player_name}schedule"] = ("scoring", player, best_flag)
                        assigned_flags.add((best_flag["posX"], best_flag["posY"]))
            
            elif action == 2:  # saving
                # 营救在prison中的队友
                if my_players_in_prison:
                    schedule[f"{player_name}schedule"] = ("saving", player, None)
        
        return schedule


# 全局智能体实例
_agent = None


def get_agent(state_dim=19, action_dim=3, device='cpu'):
    """获取或创建全局智能体"""
    global _agent
    if _agent is None:
        _agent = DQNAgent(state_dim, action_dim, device=device)
    return _agent


def initialize_rl(state_dim=19, action_dim=3, model_path=None, device='cpu'):
    """
    初始化RL系统
    
    Args:
        state_dim: 状态维度
        action_dim: 动作维度（3: defence, scoring, saving）
        model_path: 模型路径（如果存在则加载）
        device: 设备（'cpu' 或 'cuda'）
    """
    agent = get_agent(state_dim, action_dim, device)
    if model_path and os.path.exists(model_path):
        agent.load_model(model_path)
        print(f"Loaded model from {model_path}")
    return agent

