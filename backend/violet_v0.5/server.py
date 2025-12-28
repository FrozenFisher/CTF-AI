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
import math
import heapq
import collections


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


def build_weight_map(extra_obstacles=None):
    """
    构建权重地图
    Args:
        extra_obstacles: 额外的障碍物列表，默认为None
    Returns:
        权重矩阵，weight_map[x][y] 表示位置(x,y)的权重
    """
    width = world.width
    height = world.height
    
    # 初始化权重地图，默认权重为1.0（安全）
    weight_map = [[1.0 for _ in range(height)] for _ in range(width)]
    
    # 障碍物权重设为0（不可通过）
    for x, y in world.walls:
        if 0 <= x < width and 0 <= y < height:
            weight_map[x][y] = 0.0
    
    if extra_obstacles:
        for x, y in extra_obstacles:
            if 0 <= x < width and 0 <= y < height:
                weight_map[x][y] = 0.0
    
    # Target权重设为1（高优先级）
    for x, y in world.my_team_target:
        if 0 <= x < width and 0 <= y < height:
            weight_map[x][y] = 1.0
    
    for x, y in world.opponent_team_target:
        if 0 <= x < width and 0 <= y < height:
            weight_map[x][y] = 1.0
    
    # 敌人周围权重从0开始同心圆式递增{0, 0.25, 0.5, 0.75}
    # 使用BFS从敌人位置向外扩展，考虑障碍物
    opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
    
    # 创建障碍物集合（用于BFS检查）
    obstacles_set = world.walls.copy()
    if extra_obstacles:
        obstacles_set.update(extra_obstacles)
    
    for enemy in opponents:
        enemy_x = enemy["posX"]
        enemy_y = enemy["posY"]
        
        # 检查敌人位置是否有效
        if (enemy_x < 0 or enemy_x >= width or 
            enemy_y < 0 or enemy_y >= height):
            continue
        
        # 使用BFS从敌人位置向外扩展
        # 记录每个位置到敌人的实际距离（步数）
        distance_map = {}
        queue = collections.deque([(enemy_x, enemy_y, 0)])  # (x, y, distance)
        distance_map[(enemy_x, enemy_y)] = 0
        
        # 四个方向：上、下、左、右
        directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        
        # BFS扩展，最多扩展到距离2（缩小敌方权重范围）
        while queue:
            x, y, dist = queue.popleft()
            
            # 如果距离已经>=2，不需要继续扩展（因为距离>=3权重都是1.0）
            if dist >= 2:
                continue
            
            # 检查四个方向的邻居
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                
                # 检查边界
                if (nx < 0 or nx >= width or 
                    ny < 0 or ny >= height):
                    continue
                
                # 如果已经访问过，跳过
                if (nx, ny) in distance_map:
                    continue
                
                # 如果是障碍物，跳过
                if (nx, ny) in obstacles_set:
                    continue
                
                # 记录距离并加入队列
                new_dist = dist + 1
                distance_map[(nx, ny)] = new_dist
                queue.append((nx, ny, new_dist))
        
        # 根据实际距离设置权重（缩小范围：只考虑距离0-2）
        for (x, y), dist in distance_map.items():
            if dist == 0:
                enemy_weight = 0.0
            elif dist == 1:
                enemy_weight = 0.25
            elif dist == 2:
                enemy_weight = 0.5
            else:
                enemy_weight = 1.0  # 距离>=3，使用基础权重
            
            # 取最小值（最危险的权重），因为如果有多个敌人，取最危险的那个
            weight_map[x][y] = min(weight_map[x][y], enemy_weight)
    
    return weight_map


def improved_route(srcXY, dstXY, extra_obstacles=None):
    """
    计算从起点到终点的路径，避开障碍物和敌人的势力范围
    内部调用游戏引擎的route_to进行路径搜索
    Args:
        srcXY: 起点坐标 (x, y)
        dstXY: 终点坐标 (x, y)
        extra_obstacles: 额外的障碍物列表，默认为None
    Returns:
        路径列表，格式与 route_to() 相同: [(x1, y1), (x2, y2), ...]
    """
    # 检查边界条件
    if (srcXY[0] < 0 or srcXY[0] >= world.width or 
        srcXY[1] < 0 or srcXY[1] >= world.height):
        return []
    
    if (dstXY[0] < 0 or dstXY[0] >= world.width or 
        dstXY[1] < 0 or dstXY[1] >= world.height):
        return []
    
    # 如果起点和终点相同，直接返回
    if srcXY == dstXY:
        return [srcXY]
    
    # 创建障碍物集合
    obstacles_set = set()
    if extra_obstacles:
        obstacles_set.update(extra_obstacles)
    
    # 计算敌人的势力范围（距离敌人一定范围内的区域都视为不可通过）
    enemy_influence_zone = set()
    opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
    INFLUENCE_RADIUS = 1  # 敌人势力范围半径（仅包括上下左右紧邻位置）
    
    for enemy in opponents:
        enemy_x = enemy["posX"]
        enemy_y = enemy["posY"]
        
        # 检查敌人位置是否有效
        if (enemy_x < 0 or enemy_x >= world.width or 
            enemy_y < 0 or enemy_y >= world.height):
            continue
        
        # 使用BFS从敌人位置向外扩展，标记势力范围
        queue = collections.deque([(enemy_x, enemy_y, 0)])
        visited_zone = set([(enemy_x, enemy_y)])
        
        directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        
        while queue:
            x, y, dist = queue.popleft()
            
            # 如果距离已经>=INFLUENCE_RADIUS，不需要继续扩展
            if dist >= INFLUENCE_RADIUS:
                continue
            
            # 将当前位置加入势力范围
            enemy_influence_zone.add((x, y))
            
            # 检查四个方向的邻居
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                
                # 检查边界
                if (nx < 0 or nx >= world.width or 
                    ny < 0 or ny >= world.height):
                    continue
                
                # 如果已经访问过，跳过
                if (nx, ny) in visited_zone:
                    continue
                
                # 如果是障碍物，跳过（但障碍物本身也在势力范围内）
                if (nx, ny) in world.walls:
                    continue
                
                # 记录距离并加入队列
                new_dist = dist + 1
                visited_zone.add((nx, ny))
                queue.append((nx, ny, new_dist))
    
    # 将敌人势力范围加入额外障碍物
    combined_obstacles = list(obstacles_set) + list(enemy_influence_zone)
    
    # 检查起点和终点是否在障碍物或敌人势力范围内
    if srcXY in world.walls:
        print(f"      [improved_route] 起点 {srcXY} 在障碍物中")
        return []
    if srcXY in enemy_influence_zone:
        print(f"      [improved_route] 起点 {srcXY} 在敌人势力范围内")
        return []
    if dstXY in world.walls:
        print(f"      [improved_route] 终点 {dstXY} 在障碍物中")
        return []
    if dstXY in enemy_influence_zone:
        print(f"      [improved_route] 终点 {dstXY} 在敌人势力范围内")
        return []
    
    # 调用游戏引擎的route_to进行路径搜索
    result_path = world.route_to(srcXY, dstXY, extra_obstacles=combined_obstacles if combined_obstacles else None)
    if not result_path or len(result_path) <= 1:
        print(f"      [improved_route] route_to 返回空路径或无效路径 (起点: {srcXY}, 终点: {dstXY}, 敌人势力范围大小: {len(enemy_influence_zone)})")
    return result_path


def build_defence_weight_map(extra_obstacles=None):
    """
    构建防御专用的权重地图
    防御策略：在自己半场内尽可能撞击敌人，让敌人进入prison
    - 在自己领地内，敌人周围的位置权重更高（更容易接近和撞击敌人）
    - 敌人位置本身权重最高（可以直接撞击）
    - 距离敌人越近，权重越高（更容易撞击）
    - 敌方领地权重设为0（不可通过，进入敌方领地撞击敌人会导致自己死亡）
    Args:
        extra_obstacles: 额外的障碍物列表，默认为None
    Returns:
        权重矩阵，weight_map[x][y] 表示位置(x,y)的权重
    """
    width = world.width
    height = world.height
    
    # 判断己方在哪一侧
    my_targets = list(world.list_targets(mine=True))
    if my_targets:
        my_side_is_left = world.is_on_left(my_targets[0])
    else:
        my_side_is_left = True  # 默认假设在左侧
    
    # 初始化权重地图
    # 先设置敌方领地为0.1（低权重），己方领地为1.0
    weight_map = [[0.1 for _ in range(height)] for _ in range(width)]
    for x in range(width):
        for y in range(height):
            is_left = world.is_on_left((x, y))
            in_my_territory = (my_side_is_left and is_left) or (not my_side_is_left and not is_left)
            if in_my_territory:
                weight_map[x][y] = 1.0  # 己方领地初始权重为1.0
    
    # 障碍物权重设为0（不可通过）
    for x, y in world.walls:
        if 0 <= x < width and 0 <= y < height:
            weight_map[x][y] = 0.0
    
    if extra_obstacles:
        for x, y in extra_obstacles:
            if 0 <= x < width and 0 <= y < height:
                weight_map[x][y] = 0.0
    
    # 创建障碍物集合（用于BFS检查）
    obstacles_set = world.walls.copy()
    if extra_obstacles:
        obstacles_set.update(extra_obstacles)
    
    # 敌人周围权重：在自己领地内，距离敌人越近权重越高（更容易撞击）
    opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
    
    for enemy in opponents:
        enemy_x = enemy["posX"]
        enemy_y = enemy["posY"]
        
        if (enemy_x < 0 or enemy_x >= width or 
            enemy_y < 0 or enemy_y >= height):
            continue
        
        # 使用BFS从敌人位置向外扩展
        distance_map = {}
        queue = collections.deque([(enemy_x, enemy_y, 0)])
        distance_map[(enemy_x, enemy_y)] = 0
        
        directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        
        # 扩展到距离2的区域（缩小敌方权重范围）
        while queue:
            x, y, dist = queue.popleft()
            
            if dist >= 2:
                continue
            
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                
                if (nx < 0 or nx >= width or 
                    ny < 0 or ny >= height):
                    continue
                
                if (nx, ny) in distance_map:
                    continue
                
                if (nx, ny) in obstacles_set:
                    continue
                
                new_dist = dist + 1
                distance_map[(nx, ny)] = new_dist
                queue.append((nx, ny, new_dist))
        
        # 根据距离设置权重：在自己领地内，距离敌人越近权重越高
        for (x, y), dist in distance_map.items():
            is_left = world.is_on_left((x, y))
            in_my_territory = (my_side_is_left and is_left) or (not my_side_is_left and not is_left)
            
            # 只在自己领地内提高权重（更容易接近敌人进行撞击）
            # 缩小范围：只考虑距离0-2
            if in_my_territory:
                if dist == 0:
                    enemy_weight = 1.5  # 敌人位置权重最高（可以直接撞击）
                elif dist == 1:
                    enemy_weight = 1.4  # 紧邻位置权重高（容易撞击）
                elif dist == 2:
                    enemy_weight = 1.3  # 中等距离权重较高
                else:
                    enemy_weight = 1.0  # 距离>=3，使用基础权重
                
                # 取最大值（权重越高越好，更容易接近敌人）
                weight_map[x][y] = max(weight_map[x][y], enemy_weight)
    
    # 敌方领地权重设为0.1（低权重，尽量避免但允许通过）
    for x in range(width):
        for y in range(height):
            is_left = world.is_on_left((x, y))
            in_enemy_territory = (my_side_is_left and not is_left) or (not my_side_is_left and is_left)
            
            if in_enemy_territory:
                weight_map[x][y] = 0.1  # 敌方领地权重0.1（低权重，尽量避免）
    
    return weight_map


def defence_route(srcXY, dstXY, extra_obstacles=None):
    """
    计算防御专用的路径，优先选择己方领地的路径
    内部调用游戏引擎的route_to进行路径搜索
    防御策略：在自己半场内尽可能撞击敌人，让敌人进入prison
    - 避开障碍物
    - 尽量避免进入敌方领地（但允许通过）
    Args:
        srcXY: 起点坐标 (x, y)
        dstXY: 终点坐标 (x, y)
        extra_obstacles: 额外的障碍物列表，默认为None
    Returns:
        路径列表，格式与 route_to() 相同: [(x1, y1), (x2, y2), ...]
    """
    # 检查边界条件
    if (srcXY[0] < 0 or srcXY[0] >= world.width or 
        srcXY[1] < 0 or srcXY[1] >= world.height):
        return []
    
    if (dstXY[0] < 0 or dstXY[0] >= world.width or 
        dstXY[1] < 0 or dstXY[1] >= world.height):
        return []
    
    # 如果起点和终点相同，直接返回
    if srcXY == dstXY:
        return [srcXY]
    
    # 创建障碍物集合
    obstacles_set = set()
    if extra_obstacles:
        obstacles_set.update(extra_obstacles)
    
    # 判断己方在哪一侧（用于判断敌方领地）
    my_targets = list(world.list_targets(mine=True))
    if my_targets:
        my_side_is_left = world.is_on_left(my_targets[0])
    else:
        my_side_is_left = True  # 默认假设在左侧
    
    # 检查起点和终点是否为障碍物
    if srcXY in world.walls:
        return []
    if dstXY in world.walls:
        return []
    
    # 优先尝试只通过己方领地的路径
    # 如果起点和终点都在己方领地，尝试限制路径只在己方领地
    src_is_left = world.is_on_left(srcXY)
    dst_is_left = world.is_on_left(dstXY)
    src_in_my_territory = (my_side_is_left and src_is_left) or (not my_side_is_left and not src_is_left)
    dst_in_my_territory = (my_side_is_left and dst_is_left) or (not my_side_is_left and not dst_is_left)
    
    # 如果起点和终点都在己方领地，尝试限制路径只在己方领地
    if src_in_my_territory and dst_in_my_territory:
        # 将敌方领地的所有位置作为额外障碍物
        enemy_territory_obstacles = list(obstacles_set)
        for x in range(world.width):
            for y in range(world.height):
                is_left = world.is_on_left((x, y))
                in_enemy_territory = (my_side_is_left and not is_left) or (not my_side_is_left and is_left)
                if in_enemy_territory:
                    enemy_territory_obstacles.append((x, y))
        
        # 尝试只在己方领地的路径
        path = world.route_to(srcXY, dstXY, extra_obstacles=enemy_territory_obstacles if enemy_territory_obstacles else None)
        if path:
            return path
    
    # 如果无法只在己方领地找到路径，或者起点/终点不在己方领地，使用普通路径
    return world.route_to(srcXY, dstXY, extra_obstacles=list(obstacles_set) if obstacles_set else None)


# ==================== 辅助函数 ====================

def is_in_my_territory(player, position):
    """
    判断位置是否在我方半场
    Args:
        player: 玩家对象，包含team信息
        position: 位置坐标 (x, y)
    Returns:
        bool: True表示在我方半场，False表示不在
    """
    # 使用is_in_enemy_territory的逻辑：如果不在敌方领地，就在我方半场
    return not is_in_enemy_territory(player, position)


def find_closest_my_territory_on_path(path, player, player_pos):
    """
    在路径上找到距离玩家最近的己方半场位置
    Args:
        path: 路径列表 [(x1, y1), (x2, y2), ...]
        player: 玩家对象，包含team信息
        player_pos: 玩家位置 (x, y)
    Returns:
        位置坐标 (x, y) 或 None
    """
    if not path:
        print(f"      [find_closest_my_territory_on_path] 路径为空")
        return None
    
    closest_pos = None
    min_dist = float('inf')
    my_territory_count = 0
    
    for pos in path:
        if is_in_my_territory(player, pos):
            my_territory_count += 1
            dist = abs(pos[0] - player_pos[0]) + abs(pos[1] - player_pos[1])
            if dist < min_dist:
                min_dist = dist
                closest_pos = pos
    
    if closest_pos:
        print(f"      [find_closest_my_territory_on_path] 路径长度: {len(path)}, 我方半场位置数: {my_territory_count}, 最近位置: {closest_pos}, 距离: {min_dist}")
    else:
        print(f"      [find_closest_my_territory_on_path] 路径长度: {len(path)}, 我方半场位置数: {my_territory_count}, 未找到我方半场位置")
    
    return closest_pos


def find_intersection_with_middle_line(path):
    """
    找到路径上与中轴的交点（距离中轴线最近的点）
    Args:
        path: 路径列表 [(x1, y1), (x2, y2), ...]
    Returns:
        位置坐标 (x, y) 或 None
    """
    if not path:
        print(f"      [find_intersection_with_middle_line] 路径为空")
        return None
    
    closest_pos = None
    min_dist_to_middle = float('inf')
    
    for pos in path:
        dist_to_middle = abs(pos[0] - world.middle_line)
        if dist_to_middle < min_dist_to_middle:
            min_dist_to_middle = dist_to_middle
            closest_pos = pos
    
    if closest_pos:
        print(f"      [find_intersection_with_middle_line] 路径长度: {len(path)}, 中轴交点: {closest_pos}, 距离中轴: {min_dist_to_middle}")
    else:
        print(f"      [find_intersection_with_middle_line] 路径长度: {len(path)}, 未找到交点")
    
    return closest_pos


def find_closest_my_territory_on_route(route, player, player_pos):
    """
    在路径上找到离玩家路线最近的己方半场格子
    Args:
        route: 路径列表 [(x1, y1), (x2, y2), ...]
        player: 玩家对象，包含team信息
        player_pos: 玩家位置 (x, y)
    Returns:
        位置坐标 (x, y) 或 None
    """
    return find_closest_my_territory_on_path(route, player, player_pos)


# ==================== 策略函数 ====================

def defence(player, opponent):
    """
    防守函数：在自己半场内尽可能撞击敌人，让敌人进入prison
    根据路径长度和对方状态进行智能拦截
    基于初始路径进行过滤，避免路径跳变
    
    Args:
        player: 玩家对象
        opponent: 敌人对象
    Returns:
        方向字符串 ("up", "down", "left", "right", "")
    """
    player_pos = (player["posX"], player["posY"])
    opponent_pos = (opponent["posX"], opponent["posY"])
    
    # 计算初始路径：直接以敌人为目标
    initial_path = defence_route(player_pos, opponent_pos)
    
    print(f"🛡️  [defence] {player.get('name', 'unknown')} -> {opponent.get('name', 'unknown')}")
    print(f"   玩家位置: {player_pos}, 敌人位置: {opponent_pos}")
    print(f"   初始路径长度: {len(initial_path) if initial_path else 0}")
    
    if not initial_path or len(initial_path) < 2:
        print(f"   ⚠️  初始路径无效，返回空方向")
        return ""
    
    # 如果路径长度 >= 3，进行预测和拦截
    if len(initial_path) >= 3:
        target_pos = None
        
        # 如果对方有旗帜
        if opponent.get("hasFlag", False):
            print(f"   🚩 对方有旗帜")
            # 计算对方回到营地的路径
            # 注意：这里应该使用 world.route_to 而不是 improved_route
            # 因为这是对方的路径，不需要避开己方的敌人势力范围
            opponent_targets = list(world.list_targets(mine=False))
            if opponent_targets:
                opponent_target = opponent_targets[0]
                opponent_path = world.route_to(opponent_pos, opponent_target)
                
                print(f"   对方目标: {opponent_target}, 对方路径长度: {len(opponent_path) if opponent_path else 0}")
                
                if opponent_path:
                    # 在初始路径中找到在对方路径上且在我方半场的位置
                    # 遍历初始路径，找到既在对方路径上又在我方半场的位置
                    opponent_path_set = set(opponent_path)
                    for pos in initial_path:
                        if pos in opponent_path_set and is_in_my_territory(player, pos):
                            target_pos = pos
                            print(f"   ✅ 找到目标点（在对方路径上且在我方半场）: {target_pos}")
                            break
                    
                    # 如果没找到，则在初始路径中找到距离自己最短的我方半场位置
                    if not target_pos:
                        target_pos = find_closest_my_territory_on_path(initial_path, player, player_pos)
                        if target_pos:
                            print(f"   ✅ 找到目标点（初始路径中最近的我方半场位置）: {target_pos}")
                        else:
                            print(f"   ⚠️  未找到目标点（初始路径中无我方半场位置）")
        
        else:
            # 对方无旗帜
            # 创建一个临时player对象用于判断对方是否在我方半场
            temp_player = {"team": player.get("team", "")}
            opponent_in_my_territory = is_in_my_territory(temp_player, opponent_pos)
            print(f"   🚩 对方无旗帜, 对方在我方半场: {opponent_in_my_territory}")
            
            if opponent_in_my_territory:
                # 对手在己方半场，直接使用初始路径（不需要修改）
                target_pos = None
                print(f"   ✅ 对手在己方半场，不使用目标点")
            else:
                # 对手不在己方半场，计算对方去每个己方旗子的路径，找到中轴交点
                my_flags = world.list_flags(mine=True, canPickup=None)
                best_intersection = None
                min_dist_to_opponent = float('inf')
                
                print(f"   检查 {len(my_flags)} 个己方旗子")
                for flag in my_flags:
                    flag_pos = (flag["posX"], flag["posY"])
                    # 计算对方去旗子的路径
                    # 注意：这里应该使用 world.route_to 而不是 improved_route
                    # 因为这是对方的路径，我们要预测对方的真实路径，而不是避开对方势力范围的路径
                    flag_path = world.route_to(opponent_pos, flag_pos)
                    
                    if flag_path:
                        # 找到路径上与中轴的交点
                        intersection = find_intersection_with_middle_line(flag_path)
                        
                        if intersection:
                            # 检查交点是否在初始路径上
                            if intersection in initial_path:
                                # 计算交点到对方的距离（距离对方最近的交点）
                                dist = abs(intersection[0] - opponent_pos[0]) + abs(intersection[1] - opponent_pos[1])
                                print(f"     旗子 {flag_pos}: 交点 {intersection} 在初始路径上, 距离: {dist}")
                                if dist < min_dist_to_opponent:
                                    min_dist_to_opponent = dist
                                    best_intersection = intersection
                            else:
                                print(f"     旗子 {flag_pos}: 交点 {intersection} 不在初始路径上")
                
                # 如果找到最佳交点且在初始路径上，使用该交点
                if best_intersection:
                    target_pos = best_intersection
                    print(f"   ✅ 找到目标点（中轴交点）: {target_pos}, 距离: {min_dist_to_opponent}")
                else:
                    # 如果没找到交点，不动路径（使用完整初始路径）
                    target_pos = None
                    print(f"   ✅ 未找到交点，使用完整初始路径")
        
        # 打印目标点信息
        if target_pos:
            print(f"   🎯 最终目标点: {target_pos}, 是否在初始路径: {target_pos in initial_path}")
            print(f"   目标点是否在我方半场: {is_in_my_territory(player, target_pos)}")
        else:
            print(f"   🎯 最终目标点: None（使用完整初始路径）")
        
        # 过滤初始路径，去除敌方半场的部分
        # 遍历初始路径，只保留到我方半场目标位置的部分（去除敌方半场的部分）
        filtered_path = []
        
        # 如果目标点在敌方半场，不使用目标点，只保留到我方半场的部分
        if target_pos and not is_in_my_territory(player, target_pos):
            print(f"   ⚠️  目标点在敌方半场，不使用目标点，只保留到我方半场的部分")
            target_pos = None
        
        for pos in initial_path:
            # 如果找到了目标位置且目标点在我方半场，包含目标位置后停止
            if target_pos and pos == target_pos:
                filtered_path.append(pos)
                print(f"   ✅ 找到目标点，停止过滤")
                break
            
            # 只保留我方半场的部分
            if is_in_my_territory(player, pos):
                filtered_path.append(pos)
            else:
                # 遇到敌方半场，停止（去除敌方半场部分）
                # 如果还没找到目标位置，也停止
                print(f"   ⚠️  遇到敌方半场位置 {pos}，停止过滤")
                break
        
        print(f"   过滤后路径长度: {len(filtered_path)}, 初始路径长度: {len(initial_path)}")
        
        # 如果过滤后的路径为空，使用初始路径
        path = filtered_path if filtered_path else initial_path
    else:
        # 路径长度 < 3，直接使用初始路径
        print(f"   路径长度 < 3，直接使用初始路径")
        path = initial_path
    
    # 如果路径存在且长度>1，返回第一步的方向
    if len(path) > 1:
        next_step = path[1]
        direction = GameMap.get_direction(player_pos, next_step)
        print(f"   ➡️  下一步: {next_step} -> {direction}")
        return direction
    
    print(f"   ⚠️  路径无效，返回空方向")
    return ""


def scoring(player, target_flag):
    """
    得分函数：处理拿旗和送旗逻辑
    逻辑：
    - 如果有旗子：
      - 在敌方领地：使用improved_route，以离自己路线最近的己方半场格子作为目标
      - 在己方半场：如果距离最近敌人路程<=3，进行defence；否则使用improved_route，以己方营地作为目标
    - 如果没有旗子：使用improved_route，以敌方旗子为目标
    Args:
        player: 玩家对象
        target_flag: 目标旗子对象（当玩家无旗子时使用）
    Returns:
        方向字符串 ("up", "down", "left", "right", "")
    """
    player_pos = (player["posX"], player["posY"])
    
    print(f"⚽ [scoring] {player.get('name', 'unknown')}")
    print(f"   玩家位置: {player_pos}, 有旗: {player.get('hasFlag', False)}")
    
    # 如果玩家有旗子
    if player.get("hasFlag", False):
        my_targets = list(world.list_targets(mine=True))
        if not my_targets:
            print(f"   ⚠️  无己方目标，返回空方向")
            return ""
        
        my_target = my_targets[0]
        print(f"   己方目标: {my_target}")
        
        # 判断是否在敌方领地
        if is_in_enemy_territory(player, player_pos):
            print(f"   🏃 在敌方领地")
            # 在敌方领地：使用improved_route，以离自己路线最近的己方半场格子作为目标
            route_to_target = improved_route(player_pos, my_target)
            
            print(f"   到目标的路径长度: {len(route_to_target) if route_to_target else 0}")
            
            if route_to_target:
                # 在路径上找到离自己路线最近的己方半场格子作为目标
                target = find_closest_my_territory_on_route(route_to_target, player, player_pos)
                
                print(f"   🎯 找到的己方半场目标点: {target}")
                
                if target:
                    path = improved_route(player_pos, target)
                    print(f"   到目标点的路径长度: {len(path) if path else 0}")
                else:
                    # 如果找不到，直接使用营地
                    print(f"   ⚠️  未找到己方半场目标点，使用营地")
                    path = improved_route(player_pos, my_target)
            else:
                print(f"   ⚠️  到目标的路径无效，使用营地")
                path = improved_route(player_pos, my_target)
        else:
            # 在己方半场
            print(f"   🏠 在己方半场")
            opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
            
            # 检查距离最近敌人的路程
            if opponents:
                closest_opponent = None
                min_path_length = float('inf')
                
                for opponent in opponents:
                    opponent_pos = (opponent["posX"], opponent["posY"])
                    # 使用defence_route计算实际路径长度
                    path_to_opponent = defence_route(player_pos, opponent_pos)
                    if path_to_opponent and len(path_to_opponent) > 0:
                        path_length = len(path_to_opponent)
                        if path_length < min_path_length:
                            min_path_length = path_length
                            closest_opponent = opponent
                
                print(f"   最近敌人: {closest_opponent.get('name', 'unknown') if closest_opponent else None}, 路径长度: {min_path_length}")
                
                # 如果距离最近敌人路程<=3，进行defence
                if closest_opponent and min_path_length <= 3:
                    print(f"   🛡️  敌人距离<=3，执行defence")
                    defence_direction = defence(player, closest_opponent)
                    if defence_direction:
                        return defence_direction
            
            # 否则，使用improved_route，以己方营地作为目标
            print(f"   🎯 使用己方营地作为目标")
            path = improved_route(player_pos, my_target)
            print(f"   到营地的路径长度: {len(path) if path else 0}")
        
        # 返回方向
        if len(path) > 1:
            next_step = path[1]
            direction = GameMap.get_direction(player_pos, next_step)
            print(f"   ➡️  下一步: {next_step} -> {direction}")
            return direction
        else:
            print(f"   ⚠️  路径无效，返回空方向")
    
    else:
        # 玩家无旗子：使用improved_route，以敌方旗子为目标
        print(f"   🚩 无旗，去拿敌方旗子")
        
        # 获取所有可用的敌方旗子
        enemy_flags = world.list_flags(mine=False, canPickup=True)
        
        if not enemy_flags:
            print(f"   ⚠️  无可用敌方旗子，返回空方向")
            return ""
        
        # 如果提供了目标旗子，先尝试它
        selected_flag = target_flag
        best_flag = None
        best_path = None
        min_path_length = float('inf')
        
        # 如果提供了目标旗子，先尝试它
        if selected_flag and selected_flag in enemy_flags:
            flag_pos = (selected_flag["posX"], selected_flag["posY"])
            print(f"   尝试目标旗子位置: {flag_pos}")
            
            # 先尝试使用 improved_route（避开敌人势力范围）
            path = improved_route(player_pos, flag_pos)
            print(f"   improved_route 路径长度: {len(path) if path else 0}")
            
            # 如果 improved_route 失败，尝试 world.route_to
            if not path or len(path) <= 1:
                print(f"   ⚠️  improved_route 失败，尝试 world.route_to")
                path = world.route_to(player_pos, flag_pos)
                print(f"   world.route_to 路径长度: {len(path) if path else 0}")
            
            # 如果路径有效，记录为最佳选择
            if path and len(path) > 1:
                best_flag = selected_flag
                best_path = path
                min_path_length = len(path)
                print(f"   ✅ 目标旗子路径有效，路径长度: {min_path_length}")
            else:
                print(f"   ⚠️  目标旗子路径无效，尝试其他旗子")
        
        # 如果目标旗子失败或未提供，尝试所有其他旗子，选择路径最短的
        if not best_path:
            print(f"   尝试其他 {len(enemy_flags)} 个敌方旗子")
            for flag in enemy_flags:
                # 如果已经尝试过这个旗子，跳过
                if selected_flag and flag == selected_flag:
                    continue
                
                flag_pos = (flag["posX"], flag["posY"])
                
                # 先尝试使用 improved_route
                path = improved_route(player_pos, flag_pos)
                
                # 如果 improved_route 失败，尝试 world.route_to
                if not path or len(path) <= 1:
                    path = world.route_to(player_pos, flag_pos)
                
                # 如果路径有效，且比当前最佳路径更短，更新最佳选择
                if path and len(path) > 1:
                    path_length = len(path)
                    if path_length < min_path_length:
                        min_path_length = path_length
                        best_flag = flag
                        best_path = path
                        print(f"   ✅ 找到更好的旗子: {flag_pos}, 路径长度: {path_length}")
        
        # 使用最佳旗子
        if best_path and len(best_path) > 1:
            next_step = best_path[1]
            direction = GameMap.get_direction(player_pos, next_step)
            best_flag_pos = (best_flag["posX"], best_flag["posY"])
            print(f"   ➡️  选择旗子: {best_flag_pos}, 下一步: {next_step} -> {direction}")
            return direction
        else:
            print(f"   ⚠️  所有旗子都无法到达，返回空方向")
            # 添加更详细的调试信息
            print(f"   起点是否在障碍物: {player_pos in world.walls}")
            opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
            print(f"   敌人数量: {len(opponents)}")
            for opp in opponents:
                opp_pos = (opp["posX"], opp["posY"])
                dist = abs(player_pos[0] - opp_pos[0]) + abs(player_pos[1] - opp_pos[1])
                print(f"     敌人 {opp.get('name', 'unknown')} 位置: {opp_pos}, 距离: {dist}")
    
    return ""


def saving(player):
    """
    营救函数：营救在prison中的队友
    Args:
        player: 玩家对象
    Returns:
        方向字符串 ("up", "down", "left", "right", "")
    """
    player_pos = (player["posX"], player["posY"])
    
    # 找到需要营救的队友（在prison中的玩家）
    my_players_in_prison = world.list_players(mine=True, inPrison=True, hasFlag=None)
    
    if not my_players_in_prison:
        return ""
    
    # 找到最近的prison位置
    my_prisons = list(world.list_prisons(mine=True))
    if not my_prisons:
        return ""
    
    # 找到最近的prison位置（基于第一个在prison中的玩家）
    prisoner = my_players_in_prison[0]
    prisoner_pos = (prisoner["posX"], prisoner["posY"])
    
    min_prison_dist = float('inf')
    closest_prison = None
    
    for prison_pos in my_prisons:
        dist = abs(prisoner_pos[0] - prison_pos[0]) + abs(prisoner_pos[1] - prison_pos[1])
        if dist < min_prison_dist:
            min_prison_dist = dist
            closest_prison = prison_pos
    
    if closest_prison:
        # 使用 improved_route 计算路径
        path = improved_route(player_pos, closest_prison)
        
        if len(path) > 1:
            next_step = path[1]
            return GameMap.get_direction(player_pos, next_step)
    
    return ""


# 全局变量：玩家到敌人的分配
player_to_enemy_assignments = {}
player_to_flag_assignments = {}
player_to_rescue_assignments = {}

# 规则决策相关全局变量
player_defence_targets = {}  # 跟踪每个玩家当前正在追击的目标敌人 {player_name: enemy_name}
player_flag_targets = {}  # 跟踪每个玩家当前正在追击的目标旗子 {player_name: (flag_posX, flag_posY)}

## 这是你要编写的策略
def start_game(req):
    """Called when the game begins."""
    global player_to_enemy_assignments, player_to_flag_assignments, player_to_rescue_assignments
    global player_defence_targets, player_flag_targets
    
    world.init(req)
    print(f"Map initialized: {world.width}x{world.height}")
    player_to_enemy_assignments = {}
    player_to_flag_assignments = {}
    player_to_rescue_assignments = {}
    player_defence_targets = {}  # 重置防御目标追踪
    player_flag_targets = {}  # 重置旗子目标追踪

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
    global player_defence_targets, player_flag_targets
    
    # List all players that can move freely (set `hasFlag=True`)
    my_players_go = world.list_players(mine=True, inPrison=False, hasFlag=False)
    my_players_return = world.list_players(mine=True, inPrison=False, hasFlag=True)
    my_players_in_prison = world.list_players(mine=True, inPrison=True, hasFlag=None)  # 在prison中的玩家
    my_players_all = world.list_players(mine=True, inPrison=None, hasFlag=None)  # 所有己方玩家
    # List a
    opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
    enemy_flags = world.list_flags(mine=False, canPickup=True)  # 可以拾取的敌方旗子
    my_flags = world.list_flags(mine=True, canPickup=None)  # 己方旗子
    my_targets = list(world.list_targets(mine=True))
    my_prisons = list(world.list_prisons(mine=True))  # 己方prison位置
    
    # 使用规则策略
    # 处理拿着flag返回的玩家
    for p in my_players_return:
        start = (p["posX"], p["posY"])
        dest = my_targets[0] if my_targets else None
        
        if dest:
            # 判断是否在敌方领地，如果在敌方领地，将对方玩家位置设为extra_obstacles
            extra_obstacles = []
            if is_in_enemy_territory(p, start):
                extra_obstacles = [(op["posX"], op["posY"]) for op in opponents]
            
            path = world.route_to(start, dest, extra_obstacles=extra_obstacles)
            if len(path) > 1:
                next_step = path[1]
                actions[p["name"]] = GameMap.get_direction(start, next_step)
    
    # 统计敌方在prison中的数量
    enemy_players_in_prison = world.list_players(mine=False, inPrison=True, hasFlag=None)
    enemy_prison_count = len(enemy_players_in_prison)
    
    # 根据敌方在prison中的数量分配任务
    # 假设L为己方，玩家名为L0, L1, L2
    player_assignments = {}  # {player_name: "defence" or "scoring"}
    
    if enemy_prison_count <= 1:
        # 当敌方in prison <= 1时：L0和L1都defence，L2是scoring
        player_assignments = {"L0": "defence", "L1": "defence", "L2": "scoring"}
    elif enemy_prison_count == 2:
        # 当敌方in prison == 2时：L0是defence，L1和L2是scoring
        player_assignments = {"L0": "defence", "L1": "scoring", "L2": "scoring"}
    else:  # enemy_prison_count >= 3
        # 当敌方in prison >= 3时：L0、L1、L2都是scoring
        player_assignments = {"L0": "scoring", "L1": "scoring", "L2": "scoring"}
    
    # 处理没有flag的玩家，根据分配执行任务
    # 记录已分配的敌人和flag，避免重复（参考pick_test.py）
    assigned_enemies = set()
    assigned_flags = set()
    
    for p in my_players_go:
        if p["name"] in actions:  # 已分配动作，跳过
            continue
        
        player_name = p["name"]
        start = (p["posX"], p["posY"])
        
        # 获取该玩家的任务类型（如果不在分配表中，默认scoring）
        task_type = player_assignments.get(player_name, "scoring")
        
        if task_type == "defence":
            # 防御任务：找路径最近的敌人（不重复）
            available_opponents = [op for op in opponents if op["name"] not in assigned_enemies]
            if available_opponents:
                min_path_length = float('inf')
                closest_opponent = None
                for opp in available_opponents:
                    opp_pos = (opp["posX"], opp["posY"])
                    # 使用defence_route计算实际路径长度
                    path = defence_route(start, opp_pos)
                    if path and len(path) > 0:
                        path_length = len(path)
                        if path_length < min_path_length:
                            min_path_length = path_length
                            closest_opponent = opp
                
                if closest_opponent:
                    direction = defence(p, closest_opponent)
                    if direction:
                        actions[player_name] = direction
                        assigned_enemies.add(closest_opponent["name"])
        
        elif task_type == "scoring":
            # 得分任务：找路径最近的flag（不重复）
            if enemy_flags:
                available_flags = [f for f in enemy_flags if (f["posX"], f["posY"]) not in assigned_flags]
                if available_flags:
                    min_path_length = float('inf')
                    closest_flag = None
                    for flag in available_flags:
                        flag_pos = (flag["posX"], flag["posY"])
                        # 使用improved_route计算实际路径长度
                        path = improved_route(start, flag_pos)
                        if path and len(path) > 0:
                            path_length = len(path)
                            if path_length < min_path_length:
                                min_path_length = path_length
                                closest_flag = flag
                    
                    if closest_flag:
                        direction = scoring(p, closest_flag)
                        if direction:
                            actions[player_name] = direction
                            assigned_flags.add((closest_flag["posX"], closest_flag["posY"]))
        
        # 如果玩家还没有动作，检查是否有队友在prison中需要救援
        if player_name not in actions:
            my_players_in_prison = world.list_players(mine=True, inPrison=True, hasFlag=None)
            if my_players_in_prison:
                direction = saving(p)
                if direction:
                    actions[player_name] = direction
    
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


#python3 server.py $CTF_PORT_BACKEND1