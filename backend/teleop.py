import importlib
import lib.game_engine
importlib.reload(lib.game_engine)

from lib.game_engine import GameMap, run_game_server
import os
import json
import asyncio
import sys
import termios
import tty
import select

# 初始化world
world = GameMap()

# 键盘映射
KEY_MAP = {
    # L0: jikl
    'j': ('L0', 'left'),
    'i': ('L0', 'up'),
    'k': ('L0', 'down'),
    'l': ('L0', 'right'),
    
    # L1: tfgh
    't': ('L1', 'left'),
    'f': ('L1', 'up'),
    'g': ('L1', 'down'),
    'h': ('L1', 'right'),
    
    # L2: 方向键（需要特殊处理）
    # 方向键在终端中通常是转义序列，这里用wasd代替，或者用方向键的转义序列
    'w': ('L2', 'up'),
    's': ('L2', 'down'),
    'a': ('L2', 'left'),
    'd': ('L2', 'right'),
}

# 当前动作状态
current_actions = {}

def get_key():
    """获取单个按键输入（非阻塞）"""
    if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
        return sys.stdin.read(1)
    return None

def get_key_blocking():
    """获取按键输入（阻塞）"""
    return sys.stdin.read(1)

def setup_terminal():
    """设置终端为非阻塞模式"""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setraw(sys.stdin.fileno())
    return old_settings

def restore_terminal(old_settings):
    """恢复终端设置"""
    fd = sys.stdin.fileno()
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def handle_direction_key(key):
    """处理方向键转义序列"""
    # 方向键通常是 \x1b[A (上), \x1b[B (下), \x1b[C (右), \x1b[D (左)
    if key == '\x1b':  # ESC键
        next_key = get_key_blocking()
        if next_key == '[':
            arrow_key = get_key_blocking()
            if arrow_key == 'A':  # 上
                return ('L2', 'up')
            elif arrow_key == 'B':  # 下
                return ('L2', 'down')
            elif arrow_key == 'C':  # 右
                return ('L2', 'right')
            elif arrow_key == 'D':  # 左
                return ('L2', 'left')
    return None

def start_game(req):
    """Called when the game begins."""
    world.init(req)
    global current_actions
    current_actions = {}
    print(f"Map initialized: {world.width}x{world.height}")
    print("\n=== 手动控制模式 ===")
    print("L0: j(左) i(上) k(下) l(右)")
    print("L1: t(左) f(上) g(下) h(右)")
    print("L2: w(上) s(下) a(左) d(右) 或 方向键")
    print("按 'q' 退出\n")

def game_over(req):
    """Called when the game ends."""
    print("\nGame Over!")
    world.show(force=True)

def plan_next_actions(req):
    """
    Called every tick. 
    Return a dictionary: {"playerName": "direction"}
    """
    world.update(req)
    
    # 检查键盘输入
    old_settings = setup_terminal()
    try:
        key = get_key()
        if key:
            # 处理方向键
            if key == '\x1b':
                result = handle_direction_key(key)
                if result:
                    player_name, direction = result
                    current_actions[player_name] = direction
                    print(f"  {player_name}: {direction}")
            # 处理普通按键
            elif key in KEY_MAP:
                player_name, direction = KEY_MAP[key]
                current_actions[player_name] = direction
                print(f"  {player_name}: {direction}")
            elif key == 'q':
                print("\n退出游戏...")
                sys.exit(0)
    finally:
        restore_terminal(old_settings)
    
    # 显示当前地图
    try:
        world.show(flag_over_target=True, player_over_prison=True)
    except:
        pass
    
    # 返回当前动作（如果没有按键，保持不动）
    actions = current_actions.copy()
    
    # 确保所有玩家都有动作（如果没有按键，保持不动）
    my_players = world.list_players(mine=True, inPrison=False, hasFlag=None)
    for p in my_players:
        if p["name"] not in actions:
            actions[p["name"]] = ""  # 保持不动
    
    return actions

async def main():
    import sys
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <port>")
        print(f"Example: python3 {sys.argv[0]} 8080")
        sys.exit(1)

    port = int(sys.argv[1])
    print(f"Manual control backend running on port {port} ...")
    print("Waiting for game to start...")

    try:
        await run_game_server(port, start_game, plan_next_actions, game_over)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        restore_terminal(termios.tcgetattr(sys.stdin.fileno()))
    except Exception as e:
        print(f"Server Stopped: {e}")
        restore_terminal(termios.tcgetattr(sys.stdin.fileno()))
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

