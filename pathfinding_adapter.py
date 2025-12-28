"""
路径规划适配器
将server.py中的路径规划函数适配为可以接受world对象作为参数
根据server.py的新寻路逻辑更新
"""

import collections
from lib.game_engine import GameMap


def is_in_my_territory(world, position):
    """
    判断位置是否在我方半场（适配版本）
    Args:
        world: world对象
        position: 位置坐标 (x, y)
    Returns:
        bool: True表示在我方半场，False表示不在
    """
    my_targets = world.list_targets(mine=True)
    if not my_targets:
        return False
    
    # my_targets 可能是集合，取第一个元素
    if isinstance(my_targets, set):
        first_target = next(iter(my_targets))
    else:
        first_target = my_targets[0] if isinstance(my_targets, list) else next(iter(my_targets))
    
    my_side_is_left = world.is_on_left(first_target)
    is_left = world.is_on_left(position)
    
    return (my_side_is_left and is_left) or (not my_side_is_left and not is_left)


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


def find_closest_my_territory_on_path(world, path, player_pos):
    """
    在路径上找到距离玩家最近的己方半场位置（适配版本）
    Args:
        world: world对象
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
        if is_in_my_territory(world, pos):
            dist = abs(pos[0] - player_pos[0]) + abs(pos[1] - player_pos[1])
            if dist < min_dist:
                min_dist = dist
                closest_pos = pos
    
    return closest_pos


def find_intersection_with_middle_line(world, path):
    """
    找到路径上与中轴的交点（距离中轴线最近的点）（适配版本）
    Args:
        world: world对象
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


def find_closest_my_territory_on_route(world, route, player_pos):
    """
    在路径上找到离玩家路线最近的己方半场格子（适配版本）
    Args:
        world: world对象
        route: 路径列表 [(x1, y1), (x2, y2), ...]
        player_pos: 玩家位置 (x, y)
    Returns:
        位置坐标 (x, y) 或 None
    """
    return find_closest_my_territory_on_path(world, route, player_pos)


def improved_route(world, srcXY, dstXY, extra_obstacles=None):
    """
    计算从起点到终点的路径，避开障碍物和敌人的势力范围
    内部调用游戏引擎的route_to进行路径搜索（适配版本）
    Args:
        world: world对象
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
                walls_set = world.walls if hasattr(world, 'walls') else set()
                obstacles_set_world = world.obstacles if hasattr(world, 'obstacles') else set()
                if (nx, ny) in walls_set or (nx, ny) in obstacles_set_world:
                    continue
                
                # 记录距离并加入队列
                new_dist = dist + 1
                visited_zone.add((nx, ny))
                queue.append((nx, ny, new_dist))
    
    # 将敌人势力范围加入额外障碍物
    combined_obstacles = list(obstacles_set) + list(enemy_influence_zone)
    
    # 检查起点和终点是否在障碍物或敌人势力范围内
    walls_set = world.walls if hasattr(world, 'walls') else set()
    obstacles_set_world = world.obstacles if hasattr(world, 'obstacles') else set()
    
    if srcXY in walls_set or srcXY in obstacles_set_world:
        return []
    if srcXY in enemy_influence_zone:
        return []
    if dstXY in walls_set or dstXY in obstacles_set_world:
        return []
    if dstXY in enemy_influence_zone:
        return []
    
    # 调用游戏引擎的route_to进行路径搜索
    return world.route_to(srcXY, dstXY, extra_obstacles=combined_obstacles if combined_obstacles else None)


def defence_route(world, srcXY, dstXY, extra_obstacles=None):
    """
    计算防御专用的路径，优先选择己方领地的路径
    内部调用游戏引擎的route_to进行路径搜索（适配版本）
    防御策略：在自己半场内尽可能撞击敌人，让敌人进入prison
    - 避开障碍物
    - 尽量避免进入敌方领地（但允许通过）
    Args:
        world: world对象
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
    my_targets = world.list_targets(mine=True)
    if my_targets:
        # my_targets 可能是集合，取第一个元素
        if isinstance(my_targets, set):
            first_target = next(iter(my_targets))
        else:
            first_target = my_targets[0] if isinstance(my_targets, list) else next(iter(my_targets))
        my_side_is_left = world.is_on_left(first_target)
    else:
        my_side_is_left = True  # 默认假设在左侧
    
    # 检查起点和终点是否为障碍物
    walls_set = world.walls if hasattr(world, 'walls') else set()
    obstacles_set_world = world.obstacles if hasattr(world, 'obstacles') else set()
    
    if srcXY in walls_set or srcXY in obstacles_set_world:
        return []
    if dstXY in walls_set or dstXY in obstacles_set_world:
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


def defence(world, player, opponent):
    """
    防守函数：在自己半场内尽可能撞击敌人，让敌人进入prison
    根据路径长度和对方状态进行智能拦截
    基于初始路径进行过滤，避免路径跳变（适配版本）
    
    Args:
        world: world对象
        player: 玩家对象
        opponent: 敌人对象
    Returns:
        方向字符串 ("up", "down", "left", "right", "")
    """
    player_pos = (player["posX"], player["posY"])
    opponent_pos = (opponent["posX"], opponent["posY"])
    
    # 计算初始路径：直接以敌人为目标
    initial_path = defence_route(world, player_pos, opponent_pos)
    
    if not initial_path or len(initial_path) < 2:
        return ""
    
    # 如果路径长度 >= 3，进行预测和拦截
    if len(initial_path) >= 3:
        target_pos = None
        
        # 如果对方有旗帜
        if opponent.get("hasFlag", False):
            # 计算对方回到营地的路径
            # 注意：这里应该使用 world.route_to 而不是 improved_route
            # 因为这是对方的路径，不需要避开己方的敌人势力范围
            opponent_targets = world.list_targets(mine=False)
            if opponent_targets:
                # opponent_targets 可能是集合，取第一个元素
                if isinstance(opponent_targets, set):
                    opponent_target = next(iter(opponent_targets))
                else:
                    opponent_target = opponent_targets[0] if isinstance(opponent_targets, list) else next(iter(opponent_targets))
                opponent_path = world.route_to(opponent_pos, opponent_target)
                
                if opponent_path:
                    # 在初始路径中找到在对方路径上且在我方半场的位置
                    # 遍历初始路径，找到既在对方路径上又在我方半场的位置
                    opponent_path_set = set(opponent_path)
                    for pos in initial_path:
                        if pos in opponent_path_set and is_in_my_territory(world, pos):
                            target_pos = pos
                            break
                    
                    # 如果没找到，则在初始路径中找到距离自己最短的我方半场位置
                    if not target_pos:
                        target_pos = find_closest_my_territory_on_path(world, initial_path, player_pos)
        
        else:
            # 对方无旗帜
            opponent_in_my_territory = is_in_my_territory(world, opponent_pos)
            
            if opponent_in_my_territory:
                # 对手在己方半场，直接使用初始路径（不需要修改）
                target_pos = None
            else:
                # 对手不在己方半场，计算对方去每个己方旗子的路径，找到中轴交点
                my_flags = world.list_flags(mine=True, canPickup=None)
                best_intersection = None
                min_dist_to_opponent = float('inf')
                
                for flag in my_flags:
                    flag_pos = (flag["posX"], flag["posY"])
                    # 计算对方去旗子的路径
                    # 注意：这里应该使用 world.route_to 而不是 improved_route
                    # 因为这是对方的路径，我们要预测对方的真实路径，而不是避开对方势力范围的路径
                    flag_path = world.route_to(opponent_pos, flag_pos)
                    
                    if flag_path:
                        # 找到路径上与中轴的交点
                        intersection = find_intersection_with_middle_line(world, flag_path)
                        
                        if intersection:
                            # 检查交点是否在初始路径上
                            if intersection in initial_path:
                                # 计算交点到对方的距离（距离对方最近的交点）
                                dist = abs(intersection[0] - opponent_pos[0]) + abs(intersection[1] - opponent_pos[1])
                                if dist < min_dist_to_opponent:
                                    min_dist_to_opponent = dist
                                    best_intersection = intersection
                
                # 如果找到最佳交点且在初始路径上，使用该交点
                if best_intersection:
                    target_pos = best_intersection
                else:
                    # 如果没找到交点，不动路径（使用完整初始路径）
                    target_pos = None
        
        # 过滤初始路径，去除敌方半场的部分
        # 遍历初始路径，只保留到我方半场目标位置的部分（去除敌方半场的部分）
        filtered_path = []
        
        # 如果目标点在敌方半场，不使用目标点，只保留到我方半场的部分
        if target_pos and not is_in_my_territory(world, target_pos):
            target_pos = None
        
        for pos in initial_path:
            # 如果找到了目标位置且目标点在我方半场，包含目标位置后停止
            if target_pos and pos == target_pos:
                filtered_path.append(pos)
                break
            
            # 只保留我方半场的部分
            if is_in_my_territory(world, pos):
                filtered_path.append(pos)
            else:
                # 遇到敌方半场，停止（去除敌方半场部分）
                # 如果还没找到目标位置，也停止
                break
        
        # 如果过滤后的路径为空，使用初始路径
        path = filtered_path if filtered_path else initial_path
    else:
        # 路径长度 < 3，直接使用初始路径
        path = initial_path
    
    # 如果路径存在且长度>1，返回第一步的方向
    if len(path) > 1:
        next_step = path[1]
        return GameMap.get_direction(player_pos, next_step)
    
    return ""


def scoring(world, player, target_flag=None):
    """
    得分函数：处理拿旗和送旗逻辑（适配版本）
    逻辑：
    - 如果有旗子：
      - 在敌方领地：使用improved_route，以离自己路线最近的己方半场格子作为目标
      - 在己方半场：如果距离最近敌人路程<=3，进行defence；否则使用improved_route，以己方营地作为目标
    - 如果没有旗子：使用improved_route，以敌方旗子为目标
    Args:
        world: world对象
        player: 玩家对象
        target_flag: 目标旗子对象（当玩家无旗子时使用）
    Returns:
        方向字符串 ("up", "down", "left", "right", "")
    """
    player_pos = (player["posX"], player["posY"])
    
    # 如果玩家有旗子
    if player.get("hasFlag", False):
        my_targets = world.list_targets(mine=True)
        if not my_targets:
            return ""
        
        # my_targets 可能是集合，取第一个元素
        if isinstance(my_targets, set):
            my_target = next(iter(my_targets))
        else:
            my_target = my_targets[0] if isinstance(my_targets, list) else next(iter(my_targets))
        
        # 判断是否在敌方领地
        if is_in_enemy_territory(world, player, player_pos):
            # 在敌方领地：使用improved_route，以离自己路线最近的己方半场格子作为目标
            route_to_target = improved_route(world, player_pos, my_target)
            
            if route_to_target:
                # 在路径上找到离自己路线最近的己方半场格子作为目标
                target = find_closest_my_territory_on_route(world, route_to_target, player_pos)
                
                if target:
                    path = improved_route(world, player_pos, target)
                else:
                    # 如果找不到，直接使用营地
                    path = improved_route(world, player_pos, my_target)
            else:
                path = improved_route(world, player_pos, my_target)
        else:
            # 在己方半场
            opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
            
            # 检查距离最近敌人的路程
            if opponents:
                closest_opponent = None
                min_path_length = float('inf')
                
                for opponent in opponents:
                    opponent_pos = (opponent["posX"], opponent["posY"])
                    # 使用defence_route计算实际路径长度
                    path_to_opponent = defence_route(world, player_pos, opponent_pos)
                    if path_to_opponent and len(path_to_opponent) > 0:
                        path_length = len(path_to_opponent)
                        if path_length < min_path_length:
                            min_path_length = path_length
                            closest_opponent = opponent
                
                # 如果距离最近敌人路程<=3，进行defence
                if closest_opponent and min_path_length <= 3:
                    defence_direction = defence(world, player, closest_opponent)
                    if defence_direction:
                        return defence_direction
            
            # 否则，使用improved_route，以己方营地作为目标
            path = improved_route(world, player_pos, my_target)
        
        # 返回方向
        if len(path) > 1:
            next_step = path[1]
            return GameMap.get_direction(player_pos, next_step)
    
    else:
        # 玩家无旗子：使用improved_route，以敌方旗子为目标
        # 获取所有可用的敌方旗子
        enemy_flags = world.list_flags(mine=False, canPickup=True)
        
        if not enemy_flags:
            return ""
        
        # 如果提供了目标旗子，先尝试它
        selected_flag = target_flag
        best_flag = None
        best_path = None
        min_path_length = float('inf')
        
        # 如果提供了目标旗子，先尝试它
        if selected_flag and selected_flag in enemy_flags:
            flag_pos = (selected_flag["posX"], selected_flag["posY"])
            
            # 先尝试使用 improved_route（避开敌人势力范围）
            path = improved_route(world, player_pos, flag_pos)
            
            # 如果 improved_route 失败，尝试 world.route_to
            if not path or len(path) <= 1:
                path = world.route_to(player_pos, flag_pos)
            
            # 如果路径有效，记录为最佳选择
            if path and len(path) > 1:
                best_flag = selected_flag
                best_path = path
                min_path_length = len(path)
        
        # 如果目标旗子失败或未提供，尝试所有其他旗子，选择路径最短的
        if not best_path:
            for flag in enemy_flags:
                # 如果已经尝试过这个旗子，跳过
                if selected_flag and flag == selected_flag:
                    continue
                
                flag_pos = (flag["posX"], flag["posY"])
                
                # 先尝试使用 improved_route
                path = improved_route(world, player_pos, flag_pos)
                
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
        
        # 使用最佳旗子
        if best_path and len(best_path) > 1:
            next_step = best_path[1]
            direction = GameMap.get_direction(player_pos, next_step)
            return direction
    
    return ""


def saving(world, player):
    """
    营救函数：营救在prison中的队友（适配版本）
    Args:
        world: world对象
        player: 玩家对象
    Returns:
        方向字符串 ("up", "down", "left", "right", "")
    """
    player_pos = (player["posX"], player["posY"])
    
    # 找到需要营救的队友（在prison中的玩家）
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
        # 使用 improved_route 计算路径
        path = improved_route(world, player_pos, closest_prison)
        
        if len(path) > 1:
            next_step = path[1]
            return GameMap.get_direction(player_pos, next_step)
    
    return ""
