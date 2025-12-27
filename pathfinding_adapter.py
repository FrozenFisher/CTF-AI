"""
路径规划适配器
将server.py中的路径规划函数适配为可以接受world对象作为参数
"""

import heapq
import collections
from lib.game_engine import GameMap


def build_weight_map(world, extra_obstacles=None):
    """
    构建权重地图（适配版本）
    """
    width = world.width
    height = world.height
    
    # 初始化权重地图，默认权重为1.0（安全）
    weight_map = [[1.0 for _ in range(height)] for _ in range(width)]
    
    # 障碍物权重设为0（不可通过）
    for x, y in world.walls:
        if 0 <= x < width and 0 <= y < height:
            weight_map[x][y] = 0.0
    
    # 添加额外障碍物
    if extra_obstacles:
        for x, y in extra_obstacles:
            if 0 <= x < width and 0 <= y < height:
                weight_map[x][y] = 0.0
    
    # 添加simulator的障碍物
    if hasattr(world, 'obstacles'):
        for x, y in world.obstacles:
            if 0 <= x < width and 0 <= y < height:
                weight_map[x][y] = 0.0
    
    # Target权重设为1（高优先级）
    if hasattr(world, 'my_team_target'):
        for x, y in world.my_team_target:
            if 0 <= x < width and 0 <= y < height:
                weight_map[x][y] = 1.0
    
    if hasattr(world, 'opponent_team_target'):
        for x, y in world.opponent_team_target:
            if 0 <= x < width and 0 <= y < height:
                weight_map[x][y] = 1.0
    
    # 敌人周围权重从0开始同心圆式递增{0, 0.25, 0.5, 0.75}
    opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
    
    # 创建障碍物集合（用于BFS检查）
    obstacles_set = world.walls.copy()
    if extra_obstacles:
        obstacles_set.update(extra_obstacles)
    if hasattr(world, 'obstacles'):
        obstacles_set.update(world.obstacles)
    
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
        
        while queue:
            x, y, dist = queue.popleft()
            
            if dist >= 3:
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
        
        # 根据实际距离设置权重
        for (x, y), dist in distance_map.items():
            if dist == 0:
                enemy_weight = 0.0
            elif dist == 1:
                enemy_weight = 0.25
            elif dist == 2:
                enemy_weight = 0.5
            elif dist == 3:
                enemy_weight = 0.75
            else:
                enemy_weight = 1.0
            
            weight_map[x][y] = min(weight_map[x][y], enemy_weight)
    
    return weight_map


def improved_route(world, srcXY, dstXY, extra_obstacles=None):
    """
    使用加权A*算法计算从起点到终点的最优路径（适配版本）
    """
    # 检查边界条件
    if (srcXY[0] < 0 or srcXY[0] >= world.width or 
        srcXY[1] < 0 or srcXY[1] >= world.height):
        return []
    
    if (dstXY[0] < 0 or dstXY[0] >= world.width or 
        dstXY[1] < 0 or dstXY[1] >= world.height):
        return []
    
    if srcXY == dstXY:
        return [srcXY]
    
    # 构建权重地图
    weight_map = build_weight_map(world, extra_obstacles)
    
    # 检查起点和终点是否为障碍物
    if weight_map[srcXY[0]][srcXY[1]] == 0.0:
        return []
    if weight_map[dstXY[0]][dstXY[1]] == 0.0:
        return []
    
    # A*算法实现
    open_set = []
    heapq.heappush(open_set, (0, 0, srcXY[0], srcXY[1]))
    
    g_score = {}
    g_score[srcXY] = 0
    
    came_from = {}
    closed_set = set()
    
    def heuristic(pos1, pos2):
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])
    
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    
    while open_set:
        current_f, current_g, current_x, current_y = heapq.heappop(open_set)
        current = (current_x, current_y)
        
        if current in closed_set:
            continue
        
        closed_set.add(current)
        
        if current == dstXY:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(srcXY)
            path.reverse()
            return path
        
        for dx, dy in directions:
            neighbor = (current_x + dx, current_y + dy)
            neighbor_x, neighbor_y = neighbor
            
            if (neighbor_x < 0 or neighbor_x >= world.width or 
                neighbor_y < 0 or neighbor_y >= world.height):
                continue
            
            if neighbor in closed_set:
                continue
            
            neighbor_weight = weight_map[neighbor_x][neighbor_y]
            
            if neighbor_weight == 0.0:
                continue
            
            move_cost = 1.0 - neighbor_weight
            tentative_g = g_score.get(current, float('inf')) + move_cost
            
            if tentative_g < g_score.get(neighbor, float('inf')):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score = tentative_g + heuristic(neighbor, dstXY)
                heapq.heappush(open_set, (f_score, tentative_g, neighbor_x, neighbor_y))
    
    return []  # 没有找到路径


def is_in_enemy_territory(world, player, position):
    """判断玩家是否在敌方领地（适配版本）"""
    team = player.get("team", "")
    is_left = world.is_on_left(position)
    
    if team == "L":
        return not is_left
    elif team == "R":
        return is_left
    else:
        return False


def defence(world, player, opponent):
    """
    防守函数（适配版本，简化版）
    """
    player_pos = (player["posX"], player["posY"])
    opponent_pos = (opponent["posX"], opponent["posY"])
    
    # 使用improved_route计算路径
    path = improved_route(world, player_pos, opponent_pos)
    
    if len(path) > 1:
        next_step = path[1]
        return GameMap.get_direction(player_pos, next_step)
    
    return ""


def scoring(world, player, target_flag=None):
    """
    得分函数（适配版本，简化版）
    """
    player_pos = (player["posX"], player["posY"])
    
    if player.get("hasFlag", False):
        # 返回目标
        my_targets = list(world.list_targets(mine=True))
        if not my_targets:
            return ""
        
        my_target = my_targets[0]
        path = improved_route(world, player_pos, my_target)
        
        if len(path) > 1:
            next_step = path[1]
            return GameMap.get_direction(player_pos, next_step)
    else:
        # 追击敌方旗子
        if target_flag:
            flag_pos = (target_flag["posX"], target_flag["posY"])
            path = improved_route(world, player_pos, flag_pos)
            
            if len(path) > 1:
                next_step = path[1]
                return GameMap.get_direction(player_pos, next_step)
    
    return ""


def saving(world, player):
    """
    营救函数（适配版本）
    """
    player_pos = (player["posX"], player["posY"])
    
    my_players_in_prison = world.list_players(mine=True, inPrison=True, hasFlag=None)
    
    if not my_players_in_prison:
        return ""
    
    my_prisons = list(world.list_prisons(mine=True))
    if not my_prisons:
        return ""
    
    # 找到最近的prison
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
        path = improved_route(world, player_pos, closest_prison)
        
        if len(path) > 1:
            next_step = path[1]
            return GameMap.get_direction(player_pos, next_step)
    
    return ""

