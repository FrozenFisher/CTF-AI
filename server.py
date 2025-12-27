import importlib
import lib.game_engine

# Force the reload manually
importlib.reload(lib.game_engine)

# Re-import the specific classes/functions
from lib.game_engine import GameMap, run_game_server

# Now initialize your objects
world = GameMap()

# Import RL module
try:
    import RL
    RL_AVAILABLE = True
except ImportError:
    RL_AVAILABLE = False
    print("Warning: RL module not available, using rule-based strategy")

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
    
    # 计算敌人的势力范围（距离敌人一定范围内的区域都视为不可通过）
    enemy_influence_zone = set()
    opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
    INFLUENCE_RADIUS = 2  # 敌人势力范围半径（曼哈顿距离）
    
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
    
    # 合并所有障碍物（包括额外障碍物和敌人势力范围）
    all_obstacles = set()
    if extra_obstacles:
        all_obstacles.update(extra_obstacles)
    all_obstacles.update(enemy_influence_zone)
    
    # 检查起点和终点是否在障碍物或敌人势力范围内
    if srcXY in world.walls or srcXY in all_obstacles:
        return []
    if dstXY in world.walls or dstXY in all_obstacles:
        return []
    
    # 调用游戏引擎的route_to进行路径搜索
    # 将敌人势力范围作为extra_obstacles传递
    obstacle_list = list(all_obstacles) if all_obstacles else None
    return world.route_to(srcXY, dstXY, extra_obstacles=obstacle_list)


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
    计算防御专用的路径
    防御策略：在自己半场内尽可能撞击敌人，让敌人进入prison
    内部调用游戏引擎的route_to进行路径搜索
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
    
    # 优先尝试在己方领地内寻找路径
    # 如果起点和终点都在己方领地，直接调用route_to
    src_is_left = world.is_on_left(srcXY)
    dst_is_left = world.is_on_left(dstXY)
    src_in_my_territory = (my_side_is_left and src_is_left) or (not my_side_is_left and not src_is_left)
    dst_in_my_territory = (my_side_is_left and dst_is_left) or (not my_side_is_left and not dst_is_left)
    
    # 如果都在己方领地，直接调用route_to
    if src_in_my_territory and dst_in_my_territory:
        return world.route_to(srcXY, dstXY, extra_obstacles=extra_obstacles)
    
    # 否则，尝试找到一条路径（可能经过敌方领地）
    # 先尝试只使用己方领地的路径
    # 如果找不到，再尝试允许通过敌方领地的路径
    
    # 方法1：尝试只通过己方领地的路径
    # 计算敌方领地的所有位置作为临时障碍物
    enemy_territory_obstacles = set()
    for x in range(world.width):
        for y in range(world.height):
            is_left = world.is_on_left((x, y))
            in_enemy_territory = (my_side_is_left and not is_left) or (not my_side_is_left and is_left)
            if in_enemy_territory:
                enemy_territory_obstacles.add((x, y))
    
    # 合并所有障碍物
    all_obstacles = set()
    if extra_obstacles:
        all_obstacles.update(extra_obstacles)
    all_obstacles.update(enemy_territory_obstacles)
    
    # 尝试只通过己方领地的路径
    path = world.route_to(srcXY, dstXY, extra_obstacles=list(all_obstacles))
    if path:
        return path
    
    # 如果找不到只通过己方领地的路径，允许通过敌方领地
    # 只使用原始障碍物
    return world.route_to(srcXY, dstXY, extra_obstacles=extra_obstacles)


# ==================== 辅助函数 ====================

def is_in_my_territory(position):
    """
    判断位置是否在我方半场
    Args:
        position: 位置坐标 (x, y)
    Returns:
        bool: True表示在我方半场，False表示不在
    """
    my_targets = list(world.list_targets(mine=True))
    if not my_targets:
        return False
    
    my_side_is_left = world.is_on_left(my_targets[0])
    is_left = world.is_on_left(position)
    
    return (my_side_is_left and is_left) or (not my_side_is_left and not is_left)


def find_closest_my_territory_on_path(path, player_pos):
    """
    在路径上找到距离玩家最近的己方半场位置
    Args:
        path: 路径列表 [(x1, y1), (x2, y2), ...]
        player_pos: 玩家位置 (x, y)
    Returns:
        位置坐标 (x, y) 或 None
    """
    if not path:
        return None
    
    closest_pos = None
    min_dist = float('inf')
    
    for pos in path:
        if is_in_my_territory(pos):
            dist = abs(pos[0] - player_pos[0]) + abs(pos[1] - player_pos[1])
            if dist < min_dist:
                min_dist = dist
                closest_pos = pos
    
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
        return None
    
    closest_pos = None
    min_dist_to_middle = float('inf')
    
    for pos in path:
        dist_to_middle = abs(pos[0] - world.middle_line)
        if dist_to_middle < min_dist_to_middle:
            min_dist_to_middle = dist_to_middle
            closest_pos = pos
    
    return closest_pos


def find_closest_my_territory_on_route(route, player_pos):
    """
    在路径上找到离玩家路线最近的己方半场格子
    Args:
        route: 路径列表 [(x1, y1), (x2, y2), ...]
        player_pos: 玩家位置 (x, y)
    Returns:
        位置坐标 (x, y) 或 None
    """
    return find_closest_my_territory_on_path(route, player_pos)


# ==================== 策略函数 ====================

def defence(player, opponent):
    """
    防守函数：在自己半场内尽可能撞击敌人，让敌人进入prison
    根据路径长度和对方状态进行智能拦截
    
    Args:
        player: 玩家对象
        opponent: 敌人对象
    Returns:
        方向字符串 ("up", "down", "left", "right", "")
    """
    player_pos = (player["posX"], player["posY"])
    opponent_pos = (opponent["posX"], opponent["posY"])
    
    # 计算初始路径：直接以敌人为目标
    path = defence_route(player_pos, opponent_pos)
    
    # 如果路径长度 >= 3，进行预测和拦截
    if len(path) >= 3:
        # 如果对方有旗帜
        if opponent.get("hasFlag", False):
            # 计算对方回到营地的路径
            opponent_targets = list(world.list_targets(mine=False))
            if opponent_targets:
                opponent_target = opponent_targets[0]
                opponent_path = improved_route(opponent_pos, opponent_target)
                
                if opponent_path:
                    # 在对方路径上找到距离自己最短的我方半场位置作为追击目标
                    chase_target = find_closest_my_territory_on_path(opponent_path, player_pos)
                    
                    if chase_target:
                        # 重新计算路径：以拦截点为目标
                        path = defence_route(player_pos, chase_target)
        
        else:
            # 对方无旗帜，计算对方去每个己方旗子的路径
            my_flags = world.list_flags(mine=True, canPickup=None)
            best_intersection = None
            min_dist_to_opponent = float('inf')
            
            for flag in my_flags:
                flag_pos = (flag["posX"], flag["posY"])
                # 计算对方去旗子的路径
                flag_path = improved_route(opponent_pos, flag_pos)
                
                if flag_path:
                    # 找到路径上与中轴的交点
                    intersection = find_intersection_with_middle_line(flag_path)
                    
                    if intersection:
                        # 计算交点到对方的距离（距离对方最近的交点）
                        dist = abs(intersection[0] - opponent_pos[0]) + abs(intersection[1] - opponent_pos[1])
                        if dist < min_dist_to_opponent:
                            min_dist_to_opponent = dist
                            best_intersection = intersection
            
            # 如果找到最佳交点，重新计算路径：以中轴交点为目标
            if best_intersection:
                path = defence_route(player_pos, best_intersection)
    
    # 如果路径长度 < 3，直接使用初始路径（以敌人为目标）
    # 如果路径存在且长度>1，返回第一步的方向
    if len(path) > 1:
        next_step = path[1]
        return GameMap.get_direction(player_pos, next_step)
    
    return ""


def scoring(player, target_flag):
    """
    得分函数：处理拿旗和送旗逻辑
    逻辑：
    - 没有旗时优先采用defence逻辑
    - 有旗时优先回到己方半场
    - 回到己方半场后优先防御（不前往敌方半场），后回到基地
    Args:
        player: 玩家对象
        target_flag: 目标旗子对象（当玩家无旗子时使用）
    Returns:
        方向字符串 ("up", "down", "left", "right", "")
    """
    player_pos = (player["posX"], player["posY"])
    
    # 如果玩家有旗子
    if player.get("hasFlag", False):
        my_targets = list(world.list_targets(mine=True))
        if not my_targets:
            return ""
        
        my_target = my_targets[0]
        
        # 判断是否在敌方领地
        if is_in_enemy_territory(player, player_pos):
            # 在敌方领地：优先回到己方半场
            route_to_target = improved_route(player_pos, my_target)
            
            if route_to_target:
                # 在路径上找到离自己路线最近的己方半场格子作为目标
                target = find_closest_my_territory_on_route(route_to_target, player_pos)
                
                if target:
                    path = improved_route(player_pos, target)
                else:
                    # 如果找不到，直接使用营地
                    path = improved_route(player_pos, my_target)
            else:
                path = improved_route(player_pos, my_target)
        else:
            # 在己方半场：优先防御（不前往敌方半场），后回到基地
            opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
            
            # 优先检查是否有敌人需要防御
            if opponents:
                # 检查是否有敌人在己方半场或距离很近
                for opponent in opponents:
                    opponent_pos = (opponent["posX"], opponent["posY"])
                    dist = abs(player_pos[0] - opponent_pos[0]) + abs(player_pos[1] - opponent_pos[1])
                    
                    # 如果敌人在己方半场或距离很近（<=5），优先防御
                    is_opponent_in_my_territory = not is_in_enemy_territory(player, opponent_pos)
                    if is_opponent_in_my_territory or dist <= 5:
                        defence_direction = defence(player, opponent)
                        if defence_direction:
                            return defence_direction
            
            # 如果没有需要防御的敌人，返回基地
            path = improved_route(player_pos, my_target)
        
        # 返回方向
        if len(path) > 1:
            next_step = path[1]
            return GameMap.get_direction(player_pos, next_step)
    
    else:
        # 玩家无旗子：优先采用defence逻辑
        opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
        
        if opponents:
            # 优先检查是否有敌人需要防御
            for opponent in opponents:
                opponent_pos = (opponent["posX"], opponent["posY"])
                dist = abs(player_pos[0] - opponent_pos[0]) + abs(player_pos[1] - opponent_pos[1])
                
                # 如果敌人在己方半场或距离很近（<=5），优先防御
                is_opponent_in_my_territory = not is_in_enemy_territory(player, opponent_pos)
                if is_opponent_in_my_territory or dist <= 5:
                    defence_direction = defence(player, opponent)
                    if defence_direction:
                        return defence_direction
        
        # 如果没有需要防御的敌人，才去拿旗
        if target_flag:
            flag_pos = (target_flag["posX"], target_flag["posY"])
            path = improved_route(player_pos, flag_pos)
            
            if len(path) > 1:
                next_step = path[1]
                return GameMap.get_direction(player_pos, next_step)
    
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

# RL相关全局变量
rl_agent = None
prev_game_state = {}  # 存储上一帧状态用于奖励计算
USE_RL = True  # 是否使用RL（在此处配置：True=使用RL，False=使用规则策略）
RL_MODEL_PATH = "./models/dqn_model_latest.pth"  # 模型路径（如果为None则不加载模型，否则加载指定路径的模型）
player_defence_targets = {}  # 跟踪每个玩家当前正在追击的目标敌人 {player_name: enemy_name}
player_flag_targets = {}  # 跟踪每个玩家当前正在追击的目标旗子 {player_name: (flag_posX, flag_posY)}

## 这是你要编写的策略
def start_game(req):
    """Called when the game begins."""
    global player_to_enemy_assignments, player_to_flag_assignments, player_to_rescue_assignments
    global rl_agent, prev_game_state, USE_RL, RL_MODEL_PATH, player_defence_targets, player_flag_targets
    
    world.init(req)
    print(f"Map initialized: {world.width}x{world.height}")
    player_to_enemy_assignments = {}
    player_to_flag_assignments = {}
    player_to_rescue_assignments = {}
    prev_game_state = {}
    player_defence_targets = {}  # 重置防御目标追踪
    player_flag_targets = {}  # 重置旗子目标追踪
    
    # 初始化RL agent
    if RL_AVAILABLE and USE_RL:
        # 计算状态维度（根据extract_state_features的实现）
        state_dim = 19  # 5(玩家) + 6(目标) + 4(对手) + 4(全局) = 19
        action_dim = 3  # defence, scoring, saving
        
        # 加载模型（如果指定了路径）
        model_path = RL_MODEL_PATH
        if model_path and os.path.exists(model_path):
            rl_agent = RL.initialize_rl(state_dim, action_dim, model_path)
            print(f"✅ RL agent initialized with model: {model_path}")
        elif model_path:
            print(f"⚠️  警告：模型文件不存在 {model_path}，使用随机初始化")
            rl_agent = RL.initialize_rl(state_dim, action_dim, None)
        else:
            rl_agent = RL.initialize_rl(state_dim, action_dim, None)
            print("ℹ️  RL agent initialized (no model loaded, using random initialization)")
    elif not RL_AVAILABLE:
        print("Warning: RL module not available, using rule-based strategy")
    else:
        print("RL disabled in configuration, using rule-based strategy")

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
    global rl_agent, prev_game_state, USE_RL, player_defence_targets, player_flag_targets
    
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
    
    # 使用RL进行决策
    if USE_RL and rl_agent is not None:
        try:
            # 获取RL决策表
            schedule = rl_agent.predict_schedule(my_players_all, world, training=False)
            
            # 如果schedule为空，打印提示信息
            if not schedule:
                print(f"\n⚠️  RL决策表为空（可能所有敌方都在prison，或所有玩家都在prison）")
                print(f"   活跃玩家数: {len([p for p in my_players_all if not p.get('inPrison', False)])}")
                print(f"   敌方活跃数: {len(world.list_players(mine=False, inPrison=False, hasFlag=None))}")
                print()
            
            # 打印RL决策输出
            if schedule:
                print(f"\n🤖 RL决策输出 (共 {len(schedule)} 个决策):")
                for schedule_key, schedule_value in schedule.items():
                    if isinstance(schedule_value, (list, tuple)) and len(schedule_value) == 3:
                        action_type, player, target = schedule_value
                        if isinstance(player, dict) and "name" in player:
                            player_name = player["name"]
                            player_pos = f"({player.get('posX', '?')}, {player.get('posY', '?')})"
                            has_flag = "有旗" if player.get("hasFlag", False) else "无旗"
                            in_prison = "在监狱" if player.get("inPrison", False) else "自由"
                            
                            target_info = ""
                            if target:
                                if isinstance(target, dict):
                                    if "name" in target:
                                        target_info = f"目标: {target['name']} @ ({target.get('posX', '?')}, {target.get('posY', '?')})"
                                    elif "posX" in target:
                                        target_info = f"目标位置: ({target.get('posX', '?')}, {target.get('posY', '?')})"
                                    else:
                                        target_info = f"目标: {target}"
                                else:
                                    target_info = f"目标: {target}"
                            else:
                                target_info = "目标: 无"
                            
                            print(f"  {player_name} @ {player_pos} [{has_flag}, {in_prison}] -> {action_type} | {target_info}")
                print()  # 空行分隔
            
            # 记录已处理的玩家（避免重复处理）
            processed_players = set()
            
            # 根据决策表执行动作
            for schedule_key, schedule_value in schedule.items():
                if not isinstance(schedule_value, (list, tuple)) or len(schedule_value) != 3:
                    continue
                
                action_type, player, target = schedule_value
                
                # 验证player对象
                if not isinstance(player, dict) or "name" not in player:
                    continue
                
                player_name = player["name"]
                
                # 跳过已处理的玩家
                if player_name in processed_players:
                    continue
                
                # 跳过在prison中的玩家（predict_schedule应该已经过滤，但双重检查）
                if player.get("inPrison", False):
                    continue
                
                direction = ""
                
                try:
                    if action_type == "defence":
                        # 防御动作：直接寻路分配，不使用RL提供的target
                        # 优先继续追击当前目标，避免频繁更换目标
                        opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
                        if opponents:
                            player_pos = (player["posX"], player["posY"])
                            closest_opponent = None
                            
                            # 检查是否有正在追击的目标
                            current_target_name = player_defence_targets.get(player_name)
                            if current_target_name:
                                # 查找当前目标是否仍然有效
                                for opp in opponents:
                                    if opp["name"] == current_target_name:
                                        # 目标仍然有效，继续追击（不更换目标）
                                        closest_opponent = opp
                                        break
                            
                            # 只有在当前目标无效时，才选择新的目标
                            if not closest_opponent:
                                min_path_length = float('inf')
                                
                                for opp in opponents:
                                    opp_pos = (opp["posX"], opp["posY"])
                                    # 使用defence_route计算实际路径长度
                                    path = defence_route(player_pos, opp_pos)
                                    if path and len(path) > 0:
                                        path_length = len(path)
                                        if path_length < min_path_length:
                                            min_path_length = path_length
                                            closest_opponent = opp
                                
                                # 只有找到新目标时才更新记录
                                if closest_opponent:
                                    player_defence_targets[player_name] = closest_opponent["name"]
                            
                            # 执行防御动作
                            if closest_opponent:
                                direction = defence(player, closest_opponent)
                            else:
                                # 没有可追击的敌人，清除目标记录
                                if player_name in player_defence_targets:
                                    del player_defence_targets[player_name]
                    
                    elif action_type == "scoring":
                        # 得分动作
                        if player.get("hasFlag", False):
                            # 玩家有flag，返回目标区域
                            if target:
                                # target应该是目标区域位置
                                direction = scoring(player, target)
                            else:
                                # 没有指定target，使用默认目标区域
                                if my_targets:
                                    direction = scoring(player, my_targets[0])
                        else:
                            # 玩家没有flag，找敌方flag
                            # 使用和defence一样的逻辑：优先继续追击当前目标，使用路径搜索
                            if enemy_flags:
                                player_pos = (player["posX"], player["posY"])
                                closest_flag = None
                                
                                # 检查是否有正在追击的目标旗子
                                current_target_flag_pos = player_flag_targets.get(player_name)
                                if current_target_flag_pos:
                                    # 查找当前目标是否仍然有效（flag仍然可拾取）
                                    for flag in enemy_flags:
                                        flag_pos = (flag["posX"], flag["posY"])
                                        if flag_pos == current_target_flag_pos:
                                            # 目标仍然有效，继续追击（不更换目标）
                                            closest_flag = flag
                                            break
                                
                                # 只有在当前目标无效时，才选择新的目标
                                if not closest_flag:
                                    min_path_length = float('inf')
                                    
                                    for flag in enemy_flags:
                                        flag_pos = (flag["posX"], flag["posY"])
                                        # 使用improved_route计算实际路径长度
                                        path = improved_route(player_pos, flag_pos)
                                        if path and len(path) > 0:
                                            path_length = len(path)
                                            if path_length < min_path_length:
                                                min_path_length = path_length
                                                closest_flag = flag
                                    
                                    # 只有找到新目标时才更新记录
                                    if closest_flag:
                                        player_flag_targets[player_name] = (closest_flag["posX"], closest_flag["posY"])
                                
                                # 执行scoring动作
                                if closest_flag:
                                    direction = scoring(player, closest_flag)
                                else:
                                    # 没有可追击的旗子，清除目标记录
                                    if player_name in player_flag_targets:
                                        del player_flag_targets[player_name]
                    
                    elif action_type == "saving":
                        # 营救动作：不需要target
                        direction = saving(player)
                    
                except Exception as e:
                    # 如果执行动作时出错，记录但不中断
                    print(f"⚠️  执行动作 {action_type} 时出错 (玩家: {player_name}): {e}")
                    direction = ""
                
                # 如果获得了有效方向，添加到actions
                #if direction and direction in ["up", "down", "left", "right"]:
                #    actions[player_name] = direction
                #    processed_players.add(player_name)
                #    # 打印执行的动作
                #    print(f"  ✅ {player_name}: {action_type} -> {direction}")
                #else:
                # 打印未获得有效方向的情况
                print(f"  ⚠️  {player_name}: {action_type} -> 无有效方向")
            
            # 处理未在schedule中的玩家（在prison中的玩家已经在predict_schedule中过滤）
            # 但为了完整性，检查是否有遗漏的玩家
            for player in my_players_all:
                player_name = player["name"]
                if player_name not in processed_players and not player.get("inPrison", False):
                    # 如果玩家没有被分配动作，使用默认策略（找最近的flag）
                    if player_name not in actions:
                        if enemy_flags:
                            player_pos = (player["posX"], player["posY"])
                            min_dist = float('inf')
                            closest_flag = None
                            for flag in enemy_flags:
                                flag_pos = (flag["posX"], flag["posY"])
                                dist = abs(player_pos[0] - flag_pos[0]) + abs(player_pos[1] - flag_pos[1])
                                if dist < min_dist:
                                    min_dist = dist
                                    closest_flag = flag
                            if closest_flag:
                                try:
                                    direction = scoring(player, closest_flag)
                                    if direction:
                                        actions[player_name] = direction
                                except:
                                    pass
        
        except Exception as e:
            # RL决策出错，回退到规则策略
            print(f"⚠️  RL决策出错，回退到规则策略: {e}")
            # 清空已添加的actions，使用规则策略
            actions = {}
            # 继续执行规则策略逻辑（在else分支中）
        
    # 如果RL未启用或出错，使用规则策略
    if not USE_RL or rl_agent is None:
        # 使用规则策略（原有逻辑）
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
                # 防御任务：找最近的敌人（不重复）
                available_opponents = [op for op in opponents if op["name"] not in assigned_enemies]
                if available_opponents:
                    min_dist = float('inf')
                    closest_opponent = None
                    for opp in available_opponents:
                        opp_pos = (opp["posX"], opp["posY"])
                        dist = abs(start[0] - opp_pos[0]) + abs(start[1] - opp_pos[1])
                        if dist < min_dist:
                            min_dist = dist
                            closest_opponent = opp
                    
                    if closest_opponent:
                        direction = defence(p, closest_opponent)
                        if direction:
                            actions[player_name] = direction
                            assigned_enemies.add(closest_opponent["name"])
            
            elif task_type == "scoring":
                # 得分任务：找最近的flag（不重复）
                if enemy_flags:
                    available_flags = [f for f in enemy_flags if (f["posX"], f["posY"]) not in assigned_flags]
                    if available_flags:
                        min_dist = float('inf')
                        closest_flag = None
                        for flag in available_flags:
                            flag_pos = (flag["posX"], flag["posY"])
                            dist = abs(start[0] - flag_pos[0]) + abs(start[1] - flag_pos[1])
                            if dist < min_dist:
                                min_dist = dist
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
    
    # 更新上一帧状态（用于奖励计算）
    if rl_agent is not None:
        for player in my_players_all:
            player_name = player["name"]
            prev_game_state[player_name] = {
                "hasFlag": player.get("hasFlag", False),
                "inPrison": player.get("inPrison", False),
                "posX": player["posX"],
                "posY": player["posY"]
            }
    
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