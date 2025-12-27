import importlib
import lib.game_engine

# Force the reload manually
importlib.reload(lib.game_engine)

# Re-import the specific classes/functions
from lib.game_engine import GameMap, run_game_server

# Now initialize your objects
world = GameMap()

from IPython.display import clear_output
import os
import json
import random
import asyncio


def is_in_enemy_territory(player, position):
    """
    判断玩家是否在敌方领地
    Args:
        player: 玩家对象，包含team信息
        position: 位置坐标 (x, y)
    Returns:
        bool: True表示在敌方领地，False表示不在敌方领地
    """
    team = player.get("team", "")
    is_left = world.is_on_left(position)
    
    # L队在左边是自己的领地，在右边是敌方领地
    # R队在右边是自己的领地，在左边是敌方领地
    if team == "L":
        return not is_left  # L队在右边就是敌方领地
    elif team == "R":
        return is_left  # R队在左边就是敌方领地
    else:
        return False  # 未知队伍，默认返回False


# 全局变量：玩家到敌人的分配
player_to_enemy_assignments = {}
player_to_flag_assignments = {}
player_to_rescue_assignments = {}  # 玩家到需要救援的prison玩家的分配

## 这是你要编写的策略
def start_game(req):
    """Called when the game begins."""
    global player_to_enemy_assignments, player_to_flag_assignments, player_to_rescue_assignments
    world.init(req)
    print(f"Map initialized: {world.width}x{world.height}")
    player_to_enemy_assignments = {}
    player_to_flag_assignments = {}
    player_to_rescue_assignments = {}

def game_over(req):
    """Called when the game ends."""
    print("Game Over!")
    world.show(force=True)




    ## 这是你要编写的策略。以下always_move_right和walk_to_first_flag_and_return是两个例子
def plan_next_actions(req):
    """
    Called every tick. 
    Return a dictionary: {"playerName": "direction"}
    direction is "up", "down", "right", "left, "" . "" means the player should stand still.
    """
    world.update(req)    
    actions = dict()
    
    # world.show() always show targets and prisons, regardless whether flags and players are not there or not
    # Only show in Jupyter notebook environment
    try:
        world.show(flag_over_target=True, player_over_prison=True)
    except:
        pass  # Ignore errors in non-Jupyter environments 

    global player_to_enemy_assignments, player_to_flag_assignments, player_to_rescue_assignments
    
    # List all players that can move freely (set `hasFlag=True`)
    my_players_go = world.list_players(mine=True, inPrison=False, hasFlag=False)
    my_players_return = world.list_players(mine=True, inPrison=False, hasFlag=True)
    my_players_in_prison = world.list_players(mine=True, inPrison=True, hasFlag=None)  # 在prison中的玩家
    # List a
    opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
    enemy_flags = world.list_flags(mine=False, canPickup=True)  # 可以拾取的敌方旗子
    my_flags = world.list_flags(mine=True, canPickup=None)  # 己方旗子
    my_targets = list(world.list_targets(mine=True))
    my_prisons = list(world.list_prisons(mine=True))  # 己方prison位置
    
    # 清理已失效的分配（玩家被捕获或敌人不存在或flag已被拾取）
    active_player_names = {p["name"] for p in my_players_go}
    available_flag_positions = {(f["posX"], f["posY"]) for f in enemy_flags}
    players_in_prison_names = {p["name"] for p in my_players_in_prison}
    
    player_to_enemy_assignments = {
        name: enemy_name for name, enemy_name in player_to_enemy_assignments.items()
        if name in active_player_names
    }
    player_to_flag_assignments = {
        name: pos for name, pos in player_to_flag_assignments.items()
        if name in active_player_names and pos in available_flag_positions
    }
    # 清理已释放的prison玩家分配
    player_to_rescue_assignments = {
        rescuer_name: prisoner_name for rescuer_name, prisoner_name in player_to_rescue_assignments.items()
        if rescuer_name in active_player_names and prisoner_name in players_in_prison_names
    }
    
    # 为没有敌人的玩家分配敌人（确保不重复）
    assigned_enemy_names = set(player_to_enemy_assignments.values())
    available_opponents = [op for op in opponents if op["name"] not in assigned_enemy_names]
    
    # 根据玩家name（{Team}0, {Team}1, {Team}2）分配不同的敌人
    for p in my_players_go:
        if p["name"] not in player_to_enemy_assignments and available_opponents:
            # 根据玩家编号分配敌人
            player_num = int(p["name"][-1]) if p["name"][-1].isdigit() else 0
            enemy_idx = player_num % len(available_opponents)
            assigned_enemy = available_opponents[enemy_idx]
            player_to_enemy_assignments[p["name"]] = assigned_enemy["name"]
            assigned_enemy_names.add(assigned_enemy["name"])
            available_opponents.remove(assigned_enemy)
    
    # 为没有flag目标的玩家分配flag（如果他们在寻找flag），确保不重复
    if enemy_flags:
        # 获取已分配的flag位置
        assigned_flag_positions = set(player_to_flag_assignments.values())
        # 获取可用的flag（未被分配的）
        available_flags = [f for f in enemy_flags if (f["posX"], f["posY"]) not in assigned_flag_positions]
        
        # 根据玩家name（{Team}0, {Team}1, {Team}2）分配不同的flag
        for p in my_players_go:
            if p["name"] not in player_to_flag_assignments and available_flags:
                # 根据玩家编号分配flag
                player_num = int(p["name"][-1]) if p["name"][-1].isdigit() else 0
                flag_idx = player_num % len(available_flags)
                assigned_flag = available_flags[flag_idx]
                flag_pos = (assigned_flag["posX"], assigned_flag["posY"])
                player_to_flag_assignments[p["name"]] = flag_pos
                assigned_flag_positions.add(flag_pos)
                available_flags.remove(assigned_flag)
    
    # 为在prison中的玩家分配救援者（确保不重复）
    assigned_rescue_names = set(player_to_rescue_assignments.values())
    available_prisoners = [prisoner for prisoner in my_players_in_prison if prisoner["name"] not in assigned_rescue_names]
    
    # 根据玩家name分配不同的救援任务
    for p in my_players_go:
        if p["name"] not in player_to_rescue_assignments and available_prisoners:
            # 根据玩家编号分配救援任务
            player_num = int(p["name"][-1]) if p["name"][-1].isdigit() else 0
            prisoner_idx = player_num % len(available_prisoners)
            assigned_prisoner = available_prisoners[prisoner_idx]
            player_to_rescue_assignments[p["name"]] = assigned_prisoner["name"]
            assigned_rescue_names.add(assigned_prisoner["name"])
            available_prisoners.remove(assigned_prisoner)
    
    # TODO:请在这里写下你的代码来控制小人
    # 处理拿着flag返回的玩家
    for p in my_players_return:
        start = (p["posX"], p["posY"])
        dest = my_targets[0]
        
        # 判断是否在敌方领地，如果在敌方领地，将对方玩家位置设为extra_obstacles
        extra_obstacles = []
        if is_in_enemy_territory(p, start):
            extra_obstacles = [(op["posX"], op["posY"]) for op in opponents]
        
        path = world.route_to(start, dest, extra_obstacles=extra_obstacles)
        if len(path) > 1:
            next_step = path[1]
            actions[p["name"]] = GameMap.get_direction(start, next_step)
    
    # 处理没有flag的玩家
    for p in my_players_go:
        start = (p["posX"], p["posY"])
        curr_pos = (p["posX"], p["posY"])
        
        # 获取分配给这个玩家的敌人
        assigned_enemy_name = player_to_enemy_assignments.get(p["name"])
        assigned_enemy = None
        if assigned_enemy_name:
            assigned_enemy = next((op for op in opponents if op["name"] == assigned_enemy_name), None)
        
        # 优先级1：防御（追击敌人）- 最高优先级
        if not is_in_enemy_territory(p, start) and assigned_enemy:
            # 预测敌人的路径
            enemy_start = (assigned_enemy["posX"], assigned_enemy["posY"])
            
            # 当敌人有flag时，假设敌人的终点为敌方营地（敌人的目标区域）
            if assigned_enemy.get("hasFlag", False):
                # 敌人有flag，目标是敌方营地
                enemy_target_zone = list(world.list_targets(mine=False))[0]
            else:
                # 敌人没有flag，目标是离他最近的己方旗子
                enemy_target_flag = None
                if my_flags:
                    min_flag_dist = float('inf')
                    for flag in my_flags:
                        flag_pos = (flag["posX"], flag["posY"])
                        dist = abs(enemy_start[0] - flag_pos[0]) + abs(enemy_start[1] - flag_pos[1])  # 曼哈顿距离
                        if dist < min_flag_dist:
                            min_flag_dist = dist
                            enemy_target_flag = flag_pos
                
                # 如果找不到己方旗子，使用默认目标区域
                if enemy_target_flag is None:
                    enemy_target_zone = list(world.list_targets(mine=True))[0]
                else:
                    enemy_target_zone = enemy_target_flag
            
            # 检查玩家和敌人之间的距离
            dist_to_enemy = abs(start[0] - enemy_start[0]) + abs(start[1] - enemy_start[1])
            
            # 如果离敌人距离小于等于2格，直接追击敌人
            if dist_to_enemy <= 2:
                # 直接追击敌人，但确保敌人在自己领地内（因为玩家只能在自己领地内）
                # 如果敌人在自己领地内（不在敌方领地），可以追击
                if not is_in_enemy_territory(p, enemy_start):
                    target_pos = enemy_start  # 直接追击敌人
                else:
                    target_pos = None  # 敌人在敌方领地，玩家不能进入，不追击
            else:
                # 距离较远，预测敌人路径并追击第3个路径点
                # 使用extra_obstacles预测路径（可以包含其他障碍物）
                extra_obstacles = []
                enemy_path = world.route_to(enemy_start, enemy_target_zone, extra_obstacles=extra_obstacles)
                
                # 保持追击敌人的第3个path（索引为2）
                target_pos = None
                if len(enemy_path) > 2:
                    target_pos = enemy_path[2]  # 第3个位置（索引从0开始，所以是2）
                elif len(enemy_path) > 1:
                    # 如果路径长度不足3，就移动到路径的最后一个位置
                    target_pos = enemy_path[-1]
                
                # 确保目标位置在自己领地内，如果不在，找到路径中在自己领地内的位置
                if target_pos:
                    if is_in_enemy_territory(p, target_pos):
                        # 如果目标位置在敌方领地，找到敌人路径中在自己领地内的位置
                        for pos in enemy_path:
                            if not is_in_enemy_territory(p, pos):
                                target_pos = pos
                                break
                        # 如果路径中没有任何位置在自己领地，就不移动
                        if is_in_enemy_territory(p, target_pos):
                            target_pos = None
            
            # 移动到目标位置（确保目标在自己领地内）
            if target_pos and not is_in_enemy_territory(p, target_pos):
                path = world.route_to(start, target_pos, extra_obstacles=[])
                if len(path) > 1:
                    next_step = path[1]
                    actions[p["name"]] = GameMap.get_direction(start, next_step)
                    continue  # 已处理防御任务，跳过其他逻辑
        
        # 优先级2：救人 - 第二优先级
        rescue_target_name = player_to_rescue_assignments.get(p["name"])
        if rescue_target_name:
            # 找到需要救援的玩家
            rescue_target = next((prisoner for prisoner in my_players_in_prison if prisoner["name"] == rescue_target_name), None)
            if rescue_target and my_prisons:
                # 去prison位置救援（找到最近的prison位置）
                rescue_pos = (rescue_target["posX"], rescue_target["posY"])
                min_prison_dist = float('inf')
                closest_prison = None
                for prison_pos in my_prisons:
                    dist = abs(rescue_pos[0] - prison_pos[0]) + abs(rescue_pos[1] - prison_pos[1])
                    if dist < min_prison_dist:
                        min_prison_dist = dist
                        closest_prison = prison_pos
                if closest_prison:
                    path = world.route_to(start, closest_prison, extra_obstacles=[])
                    if len(path) > 1:
                        next_step = path[1]
                        actions[p["name"]] = GameMap.get_direction(start, next_step)
                        continue  # 已处理救援任务，跳过其他逻辑
        
        # 优先级3：得旗 - 最低优先级
        # 无目标追击时，执行寻找flag并送回的逻辑
        # 确定目标：分配的flag
        if p["name"] in player_to_flag_assignments:
            dest = player_to_flag_assignments[p["name"]]
            
            # 判断是否在敌方领地，如果在敌方领地，将对方玩家位置设为extra_obstacles
            my_side_is_left = world.is_on_left(my_targets[0])
            is_safe = world.is_on_left(curr_pos) == my_side_is_left
            blockers = [] if is_safe else [(o["posX"], o["posY"]) for o in opponents]
            
            # 计算路径
            path = world.route_to(curr_pos, dest, extra_obstacles=blockers)
            
            if len(path) > 1:
                move = GameMap.get_direction(curr_pos, path[1])
                actions[p["name"]] = move

    
    return actions



async def main():
    import sys
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <port>")
        print(f"Example: python3 {sys.argv[0]} 8080")
        sys.exit(1)

    port = int(sys.argv[1])
    print(f"AI backend running on port {port} ...")

    try:
        await run_game_server(port, start_game, plan_next_actions, game_over)
    except Exception as e:
        print(f"Server Stopped: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())


#python3 pick_test.py $CTF_PORT_BACKEND1