"""
CTF Game AI - Defensive Strategy with State Machine
核心策略：以防守为主，寻找机会进攻，确保不败

=== 策略概览 ===

1. 状态机驱动：
   - ABSOLUTE_DEFENSE：绝对防守，在己方中线附近盯人
   - OPPORTUNITY_ATTACK：找机会进攻，安全夺旗
   - DISTRACTION：拉扯对手，将其引向边缘
   - RESCUE：救援被关队友

2. 游戏阶段判断：
   - LEADING：领先 -> 绝对防守
   - TIED_NO_ADVANTAGE：平分且无人数优势 -> 绝对防守
   - TIED_WITH_ADVANTAGE：平分且有人数优势 -> 拉扯+找机会
   - DISADVANTAGE：人数劣势 -> 优先救人

3. 防守策略：
   - 在己方领土最靠近中线的列防守
   - 特判：领先时防守线往后退3格，避免贴着中线被抓
   - 每人盯一个对手，始终保持同一行
   - 对方至少两人进监狱前不越过中线

4. 进攻策略：
   - 人数优势时，部分人拉扯对手，其他人寻找安全的旗帜
   - 安全条件：到旗帜的路径 + 安全边际 < 最近自由对手到旗帜的距离
   - 确保不重复分配旗帜

5. 路径规划优化：
   - 仅在敌方领土时，将敌人的十字形区域（上下左右）视为障碍
   - 在己方领地时不用加载敌人的十字形区域，因为不会被抓
   - 带旗回家时，避障范围扩大到十字形+对角线（仅在敌方领土）
   - 防守和拉扯时，强制检查目标位置，绝对不跨越中线
   - 利用 world.route_to(extra_obstacles=...) 实现智能避障

6. 实时监控：
   - 人数优势/劣势（决定战术切换）
   - 比分情况（决定防守强度）
   - 玩家状态（实时更新任务分配）

=== 使用方法 ===
python3 defensive_ai_outline.py <port>
"""

import asyncio
import random
from lib.game_engine import GameMap, run_game_server
import threading
from enum import Enum
from typing import Dict, List, Tuple, Optional


class PlayerState(Enum):
    """玩家状态枚举"""
    ABSOLUTE_DEFENSE = "absolute_defense"  # 绝对防守：盯人
    OPPORTUNITY_ATTACK = "opportunity_attack"  # 找机会进攻：去夺旗
    DISTRACTION = "distraction"  # 拉扯：将对手往边缘带
    RESCUE = "rescue"  # 救援：去救被关的队友


class GamePhase(Enum):
    """游戏阶段枚举"""
    LEADING = "leading"  # 领先
    TIED_NO_ADVANTAGE = "tied_no_advantage"  # 平分且无优势
    TIED_WITH_ADVANTAGE = "tied_with_advantage"  # 平分且有人数优势
    DISADVANTAGE = "disadvantage"  # 人数劣势


# 全局变量
world = GameMap(show_gap_in_msec=1000.0)
lock = threading.Lock()

# 玩家状态管理
player_states: Dict[str, PlayerState] = {}
player_targets: Dict[str, Tuple[int, int]] = {}  # 玩家的目标位置
player_assigned_flags: Dict[str, Tuple[int, int]] = {}  # 进攻时分配的旗帜
player_tracking_opponents: Dict[str, str] = {}  # 防守时跟踪的对手
previous_player_states: Dict[str, PlayerState] = {}  # 上一轮的玩家状态，用于检测状态切换

# 游戏状态
my_side_is_left: bool = True
my_score: int = 0
enemy_score: int = 0
previous_phase: Optional[GamePhase] = None  # 上一轮的游戏阶段


def start_game(req):
    """游戏开始回调"""
    global player_states, player_targets, player_assigned_flags, player_tracking_opponents
    global my_side_is_left, my_score, enemy_score, previous_player_states, previous_phase

    world.init(req)
    print(req)
    print("Game Started!")

    # 重置所有状态
    player_states = {}
    player_targets = {}
    player_assigned_flags = {}
    player_tracking_opponents = {}
    previous_player_states = {}
    previous_phase = None
    my_score = 0
    enemy_score = 0

    # 确定我方领地方向
    my_targets = list(world.list_targets(mine=True))
    my_side_is_left = world.is_on_left(my_targets[0]) if my_targets else True

    print(f"My side: {'Left' if my_side_is_left else 'Right'}")


def analyze_game_situation() -> Dict:
    """分析当前游戏局势"""
    my_players = world.list_players(mine=True, inPrison=False, hasFlag=None)
    my_imprisoned = world.list_players(mine=True, inPrison=True, hasFlag=None)
    opponents = world.list_players(mine=False, inPrison=False, hasFlag=None)
    enemy_imprisoned = world.list_players(mine=False, inPrison=True, hasFlag=None)
    enemy_flags = world.list_flags(mine=False, canPickup=True)

    my_active_count = len(my_players)
    enemy_active_count = len(opponents)

    # 计算人数优势
    player_advantage = my_active_count - enemy_active_count

    # 判断游戏阶段
    if my_score > enemy_score:
        phase = GamePhase.LEADING
    elif my_score == enemy_score:
        if player_advantage > 0:
            phase = GamePhase.TIED_WITH_ADVANTAGE
        else:
            phase = GamePhase.TIED_NO_ADVANTAGE
    else:
        phase = GamePhase.LEADING  # 即使落后也以防守为主

    # 如果有人数劣势，优先考虑救援
    if my_imprisoned and player_advantage < 0:
        phase = GamePhase.DISADVANTAGE

    return {
        "phase": phase,
        "my_players": my_players,
        "my_imprisoned": my_imprisoned,
        "opponents": opponents,
        "enemy_imprisoned": enemy_imprisoned,
        "enemy_flags": enemy_flags,
        "player_advantage": player_advantage,
        "my_active_count": my_active_count,
        "enemy_active_count": enemy_active_count
    }


def assign_absolute_defense(situation: Dict):
    """
    绝对防守模式：每个己方玩家盯一个对手
    在己方领地最靠近中线的那一列，始终和跟踪目标保持同一行
    特判：领先时防守线往后退2-3格，避免贴着中线被抓
    关键：对方两人进监狱前我方绝对不越过中线
    """
    global player_tracking_opponents, player_states, player_targets

    my_players = situation["my_players"]
    opponents = situation["opponents"]
    enemy_imprisoned = situation["enemy_imprisoned"]

    # 确定己方最靠近中线的防守列
    map_width = world.width
    middle_x = map_width // 2

    # 基础防守线（贴近中线）
    if my_side_is_left:
        base_defense_x = middle_x - 1  # 左侧领地靠近中线的列
    else:
        base_defense_x = middle_x  # 右侧领地靠近中线的列

    # 特判：领先时往后退，增加安全边际
    defense_offset = 0
    if my_score > enemy_score:
        defense_offset = 3  # 领先时后退3格
        print(f"  [LEADING] Defense retreating by {defense_offset} columns")

    if my_side_is_left:
        defense_x = base_defense_x - defense_offset  # 左侧往左退
    else:
        defense_x = base_defense_x + defense_offset  # 右侧往右退

    # 确保防守线在有效范围内
    defense_x = max(0, min(map_width - 1, defense_x))

    print(f"  Defense line: x={defense_x} (base={base_defense_x}, offset={defense_offset})")

    # 如果没有对手在场，防守中线中心位置
    if not opponents:
        for player in my_players:
            player_targets[player["name"]] = (defense_x, world.height // 2)
            player_states[player["name"]] = PlayerState.ABSOLUTE_DEFENSE
            print(f"  {player['name']}: DEFENSE (no enemies) -> ({defense_x}, {world.height // 2})")
        return

    # 为每个玩家分配对手进行盯防
    # 优先保持之前的分配，避免频繁切换目标
    available_opponents = [opp["name"] for opp in opponents]
    assigned_players = []

    # 第一轮：保持已有的跟踪关系
    for player in my_players:
        player_name = player["name"]

        # 如果已有跟踪目标且该目标仍在场上，继续跟踪
        if player_name in player_tracking_opponents:
            tracked_opp = player_tracking_opponents[player_name]
            if tracked_opp in available_opponents:
                # 继续跟踪该对手
                opp_data = next(o for o in opponents if o["name"] == tracked_opp)
                target_y = opp_data["posY"]

                # 确保防守位置在己方领地
                player_targets[player_name] = (defense_x, target_y)
                player_states[player_name] = PlayerState.ABSOLUTE_DEFENSE
                available_opponents.remove(tracked_opp)
                assigned_players.append(player_name)
                print(f"  {player_name}: DEFENSE (tracking {tracked_opp}) -> ({defense_x}, {target_y})")

    # 第二轮：为未分配的玩家分配对手
    unassigned_players = [p for p in my_players if p["name"] not in assigned_players]

    for player in unassigned_players:
        player_name = player["name"]

        if available_opponents:
            # 选择距离最近的对手
            closest_opp = min(
                available_opponents,
                key=lambda opp_name: calculate_distance(
                    (player["posX"], player["posY"]),
                    next(o for o in opponents if o["name"] == opp_name)
                )
            )
            player_tracking_opponents[player_name] = closest_opp
            opp_data = next(o for o in opponents if o["name"] == closest_opp)
            target_y = opp_data["posY"]

            player_targets[player_name] = (defense_x, target_y)
            player_states[player_name] = PlayerState.ABSOLUTE_DEFENSE
            available_opponents.remove(closest_opp)
            print(f"  {player_name}: DEFENSE (new target {closest_opp}) -> ({defense_x}, {target_y})")
        else:
            # 如果对手数量少于己方玩家，剩余玩家防守中间位置
            player_targets[player_name] = (defense_x, world.height // 2)
            player_states[player_name] = PlayerState.ABSOLUTE_DEFENSE
            print(f"  {player_name}: DEFENSE (extra player) -> ({defense_x}, {world.height // 2})")


def calculate_distance(pos1: Tuple[int, int], pos2_data: Dict) -> int:
    """计算曼哈顿距离"""
    return abs(pos1[0] - pos2_data["posX"]) + abs(pos1[1] - pos2_data["posY"])


def assign_distraction_and_opportunity(situation: Dict):
    """
    拉扯与找机会模式：人数优势时
    1. 让部分玩家将对手往边缘拉扯
    2. 其他玩家寻找可以安全夺取的旗帜
    3. 进攻时分配目标不要重叠
    """
    global player_states, player_targets, player_assigned_flags

    my_players = situation["my_players"]
    opponents = situation["opponents"]
    enemy_flags = situation["enemy_flags"]
    player_advantage = situation["player_advantage"]

    # 如果没有对手，全员进攻
    if not opponents:
        if enemy_flags:
            assign_all_attack(my_players, enemy_flags)
        return

    # 计算每个己方玩家距离对手的最短距离，用于分配拉扯任务
    player_to_nearest_opponent = {}
    for player in my_players:
        if opponents:
            nearest_opp = min(
                opponents,
                key=lambda opp: calculate_distance((player["posX"], player["posY"]), opp)
            )
            player_to_nearest_opponent[player["name"]] = (
                nearest_opp,
                calculate_distance((player["posX"], player["posY"]), nearest_opp)
            )

    # 分配拉扯任务：让与对手距离最近的玩家负责拉扯
    # 确保每个对手都有人盯防
    distraction_players = []
    used_opponents = set()

    # 按距离排序，优先分配距离最近的玩家
    for player_name, (opp, dist) in sorted(
        player_to_nearest_opponent.items(),
        key=lambda x: x[1][1]
    ):
        if opp["name"] not in used_opponents and len(distraction_players) < len(opponents):
            distraction_players.append(player_name)
            used_opponents.add(opp["name"])

            # 拉扯策略：将对手往地图边缘带，但不越过中线
            player = next(p for p in my_players if p["name"] == player_name)

            # 根据对手的Y坐标决定往哪个边缘拉
            target_y = 0 if opp["posY"] < world.height // 2 else world.height - 1

            # 在己方领地靠近中线的位置拉扯（始终在己方领地，不越线）
            map_width = world.width
            middle_x = map_width // 2

            if my_side_is_left:
                defense_x = middle_x - 1  # 左侧，贴近中线但不越过
            else:
                defense_x = middle_x  # 右侧，贴近中线但不越过

            player_targets[player_name] = (defense_x, target_y)
            player_states[player_name] = PlayerState.DISTRACTION
            print(f"  {player_name}: DISTRACTION, pulling {opp['name']} to edge Y={target_y} at x={defense_x}")

    # 其余玩家寻找机会夺旗
    attack_players = [p for p in my_players if p["name"] not in distraction_players]

    if attack_players and enemy_flags:
        assign_safe_flags(attack_players, enemy_flags, opponents, used_opponents)
    elif attack_players:
        # 没有旗帜可夺，继续防守
        for player in attack_players:
            assign_defense_position(player, opponents)


def assign_all_attack(my_players: List[Dict], enemy_flags: List[Dict]):
    """
    全员进攻模式：没有对手时，所有玩家都去夺旗
    确保不重复分配旗帜
    """
    global player_states, player_targets, player_assigned_flags

    assigned_flags_set = set()

    for player in my_players:
        player_pos = (player["posX"], player["posY"])

        # 找到最近的未分配旗帜
        best_flag = None
        best_dist = float('inf')

        for flag in enemy_flags:
            flag_pos = (flag["posX"], flag["posY"])

            if flag_pos in assigned_flags_set:
                continue

            # 计算曼哈顿距离
            dist = abs(player_pos[0] - flag_pos[0]) + abs(player_pos[1] - flag_pos[1])

            if dist < best_dist:
                best_dist = dist
                best_flag = flag_pos

        if best_flag:
            player_assigned_flags[player["name"]] = best_flag
            player_targets[player["name"]] = best_flag
            player_states[player["name"]] = PlayerState.OPPORTUNITY_ATTACK
            assigned_flags_set.add(best_flag)
            print(f"  {player['name']}: ALL_ATTACK -> {best_flag}")


def assign_safe_flags(attack_players: List[Dict], enemy_flags: List[Dict],
                      opponents: List[Dict], used_opponents: set):
    """
    为进攻玩家分配安全的旗帜
    安全条件：到旗帜的路径长度 < 最近自由对手到旗帜的距离
    确保不重复分配旗帜
    """
    global player_states, player_targets, player_assigned_flags

    assigned_flags_set = set()

    # 计算自由对手（没有被拉扯的对手）
    free_opponents = [
        opp for opp in opponents
        if opp["name"] not in used_opponents
    ]

    for player in attack_players:
        player_pos = (player["posX"], player["posY"])

        # 找到最安全的旗帜
        best_flag = None
        best_score = float('inf')

        for flag in enemy_flags:
            flag_pos = (flag["posX"], flag["posY"])

            # 避免分配已被分配的旗帜
            if flag_pos in assigned_flags_set:
                continue

            # 计算到旗帜的路径长度
            path_to_flag = world.route_to(player_pos, flag_pos)
            if not path_to_flag:
                continue

            path_length = len(path_to_flag)

            # 计算最近的自由对手到旗帜的距离
            min_enemy_dist = float('inf')
            if free_opponents:
                min_enemy_dist = min(
                    calculate_distance(flag_pos, opp)
                    for opp in free_opponents
                )

            # 安全条件：路径长度 < 敌人距离，且留有安全边际
            safety_margin = 2  # 安全边际
            if path_length + safety_margin < min_enemy_dist:
                # 评分：路径越短越好
                score = path_length
                if score < best_score:
                    best_score = score
                    best_flag = flag_pos

        if best_flag:
            player_assigned_flags[player["name"]] = best_flag
            player_targets[player["name"]] = best_flag
            player_states[player["name"]] = PlayerState.OPPORTUNITY_ATTACK
            assigned_flags_set.add(best_flag)
            print(f"  {player['name']}: SAFE_ATTACK -> {best_flag} (path={best_score})")
        else:
            # 没有安全的旗帜，继续防守
            assign_defense_position(player, opponents)
            print(f"  {player['name']}: No safe flag, defending")


def assign_defense_position(player: Dict, opponents: List[Dict]):
    """为单个玩家分配防守位置（考虑领先时的后退逻辑）"""
    global player_states, player_targets

    map_width = world.width
    middle_x = map_width // 2

    # 基础防守线
    if my_side_is_left:
        base_defense_x = middle_x - 1
    else:
        base_defense_x = middle_x

    # 特判：领先时往后退
    defense_offset = 0
    if my_score > enemy_score:
        defense_offset = 3

    if my_side_is_left:
        defense_x = base_defense_x - defense_offset
    else:
        defense_x = base_defense_x + defense_offset

    # 确保在有效范围内
    defense_x = max(0, min(map_width - 1, defense_x))

    if opponents:
        nearest_opp = min(
            opponents,
            key=lambda opp: calculate_distance((player["posX"], player["posY"]), opp)
        )
        target_y = nearest_opp["posY"]
        player_targets[player["name"]] = (defense_x, target_y)
    else:
        player_targets[player["name"]] = (defense_x, world.height // 2)

    player_states[player["name"]] = PlayerState.ABSOLUTE_DEFENSE


def assign_rescue_mission(situation: Dict):
    """
    救援模式：人数劣势时优先救人
    让距离监狱最近的玩家去救人
    """
    global player_states, player_targets

    my_players = situation["my_players"]
    my_imprisoned = situation["my_imprisoned"]
    opponents = situation["opponents"]

    if not my_imprisoned:
        return []

    # 获取对方监狱位置（对方的target区域）
    enemy_targets = list(world.list_targets(mine=False))
    if not enemy_targets:
        return []

    prison_pos = enemy_targets[0]

    # 找到距离监狱最近的自由玩家
    rescuers = []
    for imprisoned in my_imprisoned:
        if not my_players:
            break

        nearest_player = min(
            my_players,
            key=lambda p: abs(p["posX"] - prison_pos[0]) + abs(p["posY"] - prison_pos[1])
        )

        player_states[nearest_player["name"]] = PlayerState.RESCUE
        player_targets[nearest_player["name"]] = prison_pos
        rescuers.append(nearest_player["name"])
        print(f"  {nearest_player['name']}: RESCUE -> prison at {prison_pos}")
        my_players = [p for p in my_players if p["name"] != nearest_player["name"]]

    return rescuers


def plan_next_actions(req):
    """主控制逻辑：根据游戏局势决定策略"""
    if not world.update(req):
        return

    global my_score, enemy_score, player_states, player_targets
    global previous_player_states, previous_phase

    # 更新比分
    my_score = req.get("myScore", 0)
    enemy_score = req.get("enemyScore", 0)

    print(f"\n{'='*60}")
    print(f"Turn {req.get('turn', 0)}")
    print(f"{'='*60}")
    print(f"Score: {my_score} - {enemy_score}")

    # 分析当前局势
    situation = analyze_game_situation()
    current_phase = situation['phase']

    print(f"Phase: {current_phase.value}")
    print(f"Player Advantage: {situation['player_advantage']} ({situation['my_active_count']} vs {situation['enemy_active_count']})")

    # 检测游戏阶段切换
    if previous_phase is not None and previous_phase != current_phase:
        print(f"\n*** PHASE CHANGE: {previous_phase.value} -> {current_phase.value} ***")

    previous_phase = current_phase

    if situation['my_imprisoned']:
        print(f"Imprisoned: {len(situation['my_imprisoned'])} player(s)")
    if situation['enemy_imprisoned']:
        print(f"Enemy Imprisoned: {len(situation['enemy_imprisoned'])} player(s)")

    # 保存上一轮状态用于对比
    previous_player_states = player_states.copy()

    # 重置状态
    player_states = {}
    player_targets = {}

    print(f"\n--- Strategy Assignment ---")

    # 1. 人数劣势：优先救人
    if situation["phase"] == GamePhase.DISADVANTAGE:
        print(f"[DISADVANTAGE] Priority: RESCUE")
        rescuers = assign_rescue_mission(situation)
        # 剩余玩家防守
        remaining_players = [
            p for p in situation["my_players"]
            if p["name"] not in rescuers
        ]
        if remaining_players:
            for player in remaining_players:
                assign_defense_position(player, situation["opponents"])

    # 2. 领先或平分无优势：绝对防守
    elif situation["phase"] in [GamePhase.LEADING, GamePhase.TIED_NO_ADVANTAGE]:
        print(f"[{situation['phase'].value.upper()}] Strategy: ABSOLUTE DEFENSE")
        assign_absolute_defense(situation)

    # 3. 平分有优势：拉扯+找机会
    elif situation["phase"] == GamePhase.TIED_WITH_ADVANTAGE:
        print(f"[ADVANTAGE] Strategy: DISTRACTION + OPPORTUNITY ATTACK")
        assign_distraction_and_opportunity(situation)

    # 检测玩家状态切换
    print(f"\n--- Player State Changes ---")
    state_changes = []
    for player_name, new_state in player_states.items():
        if player_name in previous_player_states:
            old_state = previous_player_states[player_name]
            if old_state != new_state:
                state_changes.append(f"{player_name}: {old_state.value} -> {new_state.value}")
        else:
            state_changes.append(f"{player_name}: [NEW] -> {new_state.value}")

    # 检测消失的玩家（可能被抓或其他原因）
    for player_name, old_state in previous_player_states.items():
        if player_name not in player_states:
            state_changes.append(f"{player_name}: {old_state.value} -> [REMOVED]")

    if state_changes:
        for change in state_changes:
            print(f"  {change}")
    else:
        print(f"  (No state changes)")

    print(f"\n--- Move Execution ---")
    # 4. 生成移动指令
    return generate_moves(situation)


def generate_moves(situation: Dict) -> Dict[str, str]:
    """
    根据玩家状态和目标生成移动指令
    核心优化：
    1. 仅在敌方领土时，将敌人的十字形位置视为障碍
    2. 在己方领地时不用加载敌人的十字形区域，因为不会被抓
    3. 带旗回家时优先避开敌人（仅在敌方领土）
    4. 防守和拉扯状态时，强制检查不跨越中线
    """
    player_moves = {}
    my_players = situation["my_players"]
    opponents = situation["opponents"]
    my_targets = list(world.list_targets(mine=True))

    if not my_targets:
        return {}

    for player in my_players:
        player_name = player["name"]
        curr_pos = (player["posX"], player["posY"])

        # 判断当前位置是否在己方领地
        is_in_home_territory = world.is_on_left(curr_pos) == my_side_is_left

        # 优先处理：如果玩家有旗帜，直接回家
        if player["hasFlag"]:
            dest = my_targets[0]

            # 带旗时，仅在敌方领土需要避开敌人
            extra_obstacles = []

            if not is_in_home_territory:
                # 在敌方领土，避开敌人的更大范围（十字形+对角线）
                for opp in opponents:
                    opp_x, opp_y = opp["posX"], opp["posY"]
                    # 十字形加对角线：更安全的避障范围
                    extra_obstacles.extend([
                        (opp_x, opp_y),  # 中心
                        (opp_x - 1, opp_y), (opp_x + 1, opp_y),  # 左右
                        (opp_x, opp_y - 1), (opp_x, opp_y + 1),  # 上下
                        (opp_x - 1, opp_y - 1), (opp_x + 1, opp_y - 1),  # 对角
                        (opp_x - 1, opp_y + 1), (opp_x + 1, opp_y + 1)
                    ])
            # 在己方领地时，extra_obstacles 保持为空列表，不避开敌人

            path = world.route_to(curr_pos, dest, extra_obstacles=extra_obstacles)

            if path and len(path) > 1:
                move = world.get_direction(curr_pos, path[1])
                player_moves[player_name] = move
                territory_info = "HOME" if is_in_home_territory else "ENEMY"
                print(f"{player_name}: RETURNING_FLAG [{territory_info}] -> {dest} (move: {move})")
            continue

        # 根据状态决定目标
        if player_name not in player_states or player_name not in player_targets:
            continue

        state = player_states[player_name]
        dest = player_targets[player_name]

        # 关键安全检查：防守和拉扯时，绝对不跨过中线
        dest_in_home_territory = world.is_on_left(dest) == my_side_is_left

        if state in [PlayerState.ABSOLUTE_DEFENSE, PlayerState.DISTRACTION]:
            # 如果目标在敌方领地，强制调整到中线边缘
            if not dest_in_home_territory:
                map_width = world.width
                middle_x = map_width // 2

                if my_side_is_left:
                    # 左侧，最右边的列是 middle_x - 1
                    dest = (middle_x - 1, dest[1])
                else:
                    # 右侧，最左边的列是 middle_x
                    dest = (middle_x, dest[1])

                print(f"  WARNING: {player_name} target adjusted to stay in home territory: {dest}")

        # 仅在敌方领土时，将敌人的十字形位置视为障碍
        extra_obstacles = []

        if not is_in_home_territory:
            # 在敌方领土，避开敌人的十字形区域
            for opp in opponents:
                opp_x, opp_y = opp["posX"], opp["posY"]
                # 十字形：中心+上下左右
                extra_obstacles.extend([
                    (opp_x, opp_y),
                    (opp_x - 1, opp_y),
                    (opp_x + 1, opp_y),
                    (opp_x, opp_y - 1),
                    (opp_x, opp_y + 1)
                ])
        # 在己方领地时，extra_obstacles 保持为空列表，不需要避开敌人

        # 路径规划
        path = world.route_to(curr_pos, dest, extra_obstacles=extra_obstacles)

        # 生成移动指令
        if path and len(path) > 1:
            move = world.get_direction(curr_pos, path[1])
            player_moves[player_name] = move
            territory_info = "HOME" if is_in_home_territory else "ENEMY"
            print(f"{player_name}: {state.value} [{territory_info}] -> {dest} (move: {move})")

    return player_moves


def game_over(req):
    """游戏结束回调"""
    print("\n=== Game Over ===")
    print(f"Final Score: {my_score} - {enemy_score}")
    world.show(force=True)


async def main():
    """主函数"""
    import sys
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <port>")
        print(f"Example: python3 {sys.argv[0]} 8080")
        sys.exit(1)

    port = int(sys.argv[1])
    print(f"Defensive AI backend running on port {port}...")

    try:
        await run_game_server(port, start_game, plan_next_actions, game_over)
    except Exception as e:
        print(f"Server Stopped: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
