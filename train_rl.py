"""
DQN模型训练脚本
用于训练CTF游戏的强化学习模型
"""

import importlib
import lib.game_engine
importlib.reload(lib.game_engine)

from lib.game_engine import GameMap, run_game_server
import RL
import os
import json
import asyncio
import random
import math
from collections import deque

# 初始化world
world = GameMap()

# 从server.py导入必要的函数
def is_in_enemy_territory(player, position):
    """判断玩家是否在敌方领地"""
    team = player.get("team", "")
    is_left = world.is_on_left(position)
    if team == "L":
        return not is_left
    elif team == "R":
        return is_left
    else:
        return False


# 训练相关全局变量
training_agent = None
training_stats = {
    'episode': 0,
    'total_reward': 0,
    'episode_rewards': [],
    'losses': [],
    'epsilon_history': []
}
prev_states = {}  # {player_name: state_dict}
episode_states = []  # 存储episode中的所有经验


def start_game_train(req):
    """训练模式下的游戏开始"""
    global training_agent, prev_states, episode_states
    
    world.init(req)
    print(f"[Training] Episode {training_stats['episode'] + 1} started")
    prev_states = {}
    episode_states = []
    
    # 确保agent已初始化
    if training_agent is None:
        state_dim = 19  # 5(玩家) + 6(目标) + 4(对手) + 4(全局) = 19
        action_dim = 3
        training_agent = RL.DQNAgent(state_dim, action_dim, device='cpu')
        print("[Training] DQN Agent initialized")


def plan_next_actions_train(req):
    """
    训练模式下的决策函数
    收集经验并训练模型
    """
    global training_agent, prev_states, episode_states, training_stats
    
    if not world.update(req):
        return {}
    
    actions = {}
    
    # 获取所有玩家
    my_players_all = world.list_players(mine=True, inPrison=None, hasFlag=None)
    opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
    enemy_flags = world.list_flags(mine=False, canPickup=True)
    my_targets = list(world.list_targets(mine=True))
    my_players_in_prison = world.list_players(mine=True, inPrison=True, hasFlag=None)
    
    if training_agent is None:
        return actions
    
    # 为每个玩家做决策并收集经验
    for player in my_players_all:
        if player.get("inPrison", False):
            continue
        
        player_name = player["name"]
        
        # 提取当前状态
        current_state = RL.extract_state_features(player, world)
        
        # 选择动作（训练模式，使用epsilon-greedy）
        action_idx = training_agent.select_action(current_state, training=True)
        
        # 获取上一帧状态
        prev_state_dict = prev_states.get(player_name)
        
        # 计算奖励（传入当前动作）
        reward = training_agent.calculate_reward(player, world, prev_state_dict, current_action=action_idx)
        training_stats['total_reward'] += reward
        
        # 存储经验（如果上一帧存在）
        if prev_state_dict is not None:
            # 创建上一帧的player对象用于状态提取
            prev_player = {
                "posX": prev_state_dict["posX"],
                "posY": prev_state_dict["posY"],
                "hasFlag": prev_state_dict["hasFlag"],
                "inPrison": prev_state_dict["inPrison"],
                "team": player.get("team", ""),
                "name": player_name
            }
            prev_state = RL.extract_state_features(prev_player, world)
            
            # 判断是否结束（玩家在prison）
            done = player.get("inPrison", False)
            
            # 立即添加到replay buffer（用于在线学习）
            training_agent.replay_buffer.push(
                prev_state,
                action_idx,
                reward,
                current_state,
                done
            )
        
        # 根据动作执行决策（使用RL模块的predict_schedule逻辑）
        # 这里简化处理，直接使用RL的决策逻辑
        if action_idx == 0:  # defence
            if opponents:
                player_pos = (player["posX"], player["posY"])
                best_opponent = None
                min_dist = float('inf')
                for opp in opponents:
                    opp_pos = (opp["posX"], opp["posY"])
                    dist = abs(player_pos[0] - opp_pos[0]) + abs(player_pos[1] - opp_pos[1])
                    if dist < min_dist:
                        min_dist = dist
                        best_opponent = opp
                
                if best_opponent:
                    # 使用server.py中的defence函数
                    try:
                        import server
                        direction = server.defence(player, best_opponent)
                        if direction:
                            actions[player_name] = direction
                    except:
                        # 如果导入失败，使用简单路径规划
                        path = world.route_to(player_pos, (best_opponent["posX"], best_opponent["posY"]))
                        if len(path) > 1:
                            actions[player_name] = GameMap.get_direction(player_pos, path[1])
        
        elif action_idx == 1:  # scoring
            if player.get("hasFlag", False):
                if my_targets:
                    try:
                        import server
                        direction = server.scoring(player, my_targets[0])
                        if direction:
                            actions[player_name] = direction
                    except:
                        path = world.route_to((player["posX"], player["posY"]), my_targets[0])
                        if len(path) > 1:
                            actions[player_name] = GameMap.get_direction((player["posX"], player["posY"]), path[1])
            else:
                if enemy_flags:
                    player_pos = (player["posX"], player["posY"])
                    best_flag = None
                    min_dist = float('inf')
                    for flag in enemy_flags:
                        flag_pos = (flag["posX"], flag["posY"])
                        dist = abs(player_pos[0] - flag_pos[0]) + abs(player_pos[1] - flag_pos[1])
                        if dist < min_dist:
                            min_dist = dist
                            best_flag = flag
                    
                    if best_flag:
                        try:
                            import server
                            direction = server.scoring(player, best_flag)
                            if direction:
                                actions[player_name] = direction
                        except:
                            flag_pos = (best_flag["posX"], best_flag["posY"])
                            path = world.route_to(player_pos, flag_pos)
                            if len(path) > 1:
                                actions[player_name] = GameMap.get_direction(player_pos, path[1])
        
        elif action_idx == 2:  # saving
            if my_players_in_prison:
                try:
                    import server
                    direction = server.saving(player)
                    if direction:
                        actions[player_name] = direction
                except:
                    my_prisons = list(world.list_prisons(mine=True))
                    if my_prisons:
                        player_pos = (player["posX"], player["posY"])
                        path = world.route_to(player_pos, my_prisons[0])
                        if len(path) > 1:
                            actions[player_name] = GameMap.get_direction(player_pos, path[1])
        
        # 更新上一帧状态
        prev_states[player_name] = {
            "hasFlag": player.get("hasFlag", False),
            "inPrison": player.get("inPrison", False),
            "posX": player["posX"],
            "posY": player["posY"]
        }
    
    # 定期训练（每5步训练一次，确保有足够经验）
    if len(training_agent.replay_buffer) >= 32:  # 确保有足够的经验
        # 每5步训练一次
        if len(episode_states) % 5 == 0:
            loss = training_agent.train_step(batch_size=32)
            if loss is not None:
                training_stats['losses'].append(loss)
    
    return actions


def game_over_train(req):
    """训练模式下的游戏结束"""
    global training_agent, episode_states, training_stats, prev_states
    
    # 注意：经验已经在plan_next_actions中添加到replay buffer了
    # 这里只需要处理episode结束的标记
    
    # 更新统计信息
    training_stats['episode'] += 1
    episode_reward = training_stats['total_reward']
    training_stats['episode_rewards'].append(episode_reward)
    training_stats['epsilon_history'].append(training_agent.epsilon)
    
    # 更新epsilon
    training_agent.update_epsilon()
    
    # 打印统计信息
    avg_reward = sum(training_stats['episode_rewards'][-10:]) / min(10, len(training_stats['episode_rewards']))
    avg_loss = sum(training_stats['losses'][-10:]) / min(10, len(training_stats['losses'])) if training_stats['losses'] else 0
    
    print(f"[Training] Episode {training_stats['episode']} finished")
    print(f"  Total Reward: {episode_reward:.2f}")
    print(f"  Avg Reward (last 10): {avg_reward:.2f}")
    print(f"  Avg Loss (last 10): {avg_loss:.4f}")
    print(f"  Epsilon: {training_agent.epsilon:.4f}")
    print(f"  Replay Buffer Size: {len(training_agent.replay_buffer)}")
    
    # 重置episode奖励
    training_stats['total_reward'] = 0
    episode_states = []
    prev_states = {}
    
    # 定期保存模型（每10个episode）
    if training_stats['episode'] % 10 == 0:
        model_dir = "models"
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, f"dqn_model_ep{training_stats['episode']}.pth")
        training_agent.save_model(model_path)
        print(f"[Training] Model saved to {model_path}")
        
        # 同时保存最新模型
        latest_path = os.path.join(model_dir, "dqn_model_latest.pth")
        training_agent.save_model(latest_path)
        print(f"[Training] Latest model saved to {latest_path}")
    
    # 显示训练进度
    world.show(force=True)


async def main():
    """主函数"""
    import sys
    
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <port>")
        print(f"Example: python3 {sys.argv[0]} 8080")
        sys.exit(1)
    
    port = int(sys.argv[1])
    print(f"[Training] Starting training server on port {port}...")
    print(f"[Training] Model will be saved to ./models/ directory")
    print(f"[Training] Training will run until interrupted (Ctrl+C)")
    
    try:
        await run_game_server(port, start_game_train, plan_next_actions_train, game_over_train)
    except KeyboardInterrupt:
        print("\n[Training] Training interrupted by user")
        
        # 保存最终模型
        if training_agent is not None:
            model_dir = "models"
            os.makedirs(model_dir, exist_ok=True)
            final_path = os.path.join(model_dir, "dqn_model_final.pth")
            training_agent.save_model(final_path)
            print(f"[Training] Final model saved to {final_path}")
            
            # 保存训练统计
            stats_path = os.path.join(model_dir, "training_stats.json")
            with open(stats_path, 'w') as f:
                json.dump(training_stats, f, indent=2)
            print(f"[Training] Training statistics saved to {stats_path}")
    except Exception as e:
        print(f"[Training] Server Stopped: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

