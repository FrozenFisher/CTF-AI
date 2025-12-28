# Capture the Flag

Your job is to implement your own algorithm (see `backend/server.py`) to control
a team to compete in "Capture the Flag" Game.

## Game Rules
Capture the Flag is a popular outdoor game where two teams compete in an open field.
Each team has a territory and a set of flags located within the territory. Each team's
goal is to collect flags of the opponent team and bring them back to the target area.

A player can tag the opponent team's player within his territory.
When tagged, the opponent team's player will be put into the prison.
The player will stay in the prison for a period of time, unless he is saved by
his teammate earlier.
The initial positions of flags, the target area and the prison are within the team's
territory.
A player can only pick the flags of the opponent team. That is, he cannot pick up
his team's flag and put it in a different place.

Our game has two teams: "L" and "R" team. The field is a rectangle area,
where the left half is "L" team's territory and the other is "R" team's.
There are obstacles and walls within the map.

![Capture The Flag Map](./fixed_map_example.png)

## 快速开始

### 环境要求
- Python 3.7+
- 推荐使用虚拟环境（项目已包含 `.venv`）

### 启动游戏

#### 1. 启动前端服务器

```bash
cd frontend
python3 -m http.server ${CTF_PORT_FRONTEND} --bind 0.0.0.0
```

或者使用环境变量指定端口（默认 8000）：
```bash
export CTF_PORT_FRONTEND=8000
cd frontend
python3 -m http.server ${CTF_PORT_FRONTEND} --bind 0.0.0.0
```

#### 2. 启动后端服务器（L 队）

```bash
cd backend
python3 server.py 34712
```

#### 3. 启动后端服务器（R 队）

```bash
cd backend
python3 server.py 34713
```

#### 4. 访问游戏

在浏览器中打开：`http://localhost:${CTF_PORT_FRONTEND}/index.html`

### 配置说明

前端服务器通过 `frontend/game_config.json` 配置文件连接后端服务器：

```json
{
  "teams": [
    { "name": "L", "who": "user48-1"},
    { "name": "R", "who": "user48-2"}
  ],
  "servers": {
    "user48-1": "ws://0.0.0.0:34712",
    "user48-2": "ws://0.0.0.0:34713"
  }
}
```

- `teams` 字段指定每个队伍对应的服务器ID
- `servers` 字段配置每个服务器ID对应的 WebSocket URL
- 确保后端端口与配置中的端口一致

## 开发教程

### 修改后端 AI

后端 AI 的核心逻辑在 `backend/server.py` 文件中。主要需要实现以下函数：

#### 1. `start_game(req)` - 游戏初始化
在游戏开始时调用一次，用于初始化游戏状态。

```python
def start_game(req):
    """Called when the game begins."""
    global world
    world.init(req)
    print(f"Map initialized: {world.width}x{world.height}")
```

#### 2. `plan_next_actions(req)` - 决策函数（核心）
每个游戏 tick 都会调用，返回每个玩家的移动方向。

```python
def plan_next_actions(req):
    """
    Called every tick. 
    Return a dictionary: {"playerName": "direction"}
    direction is "up", "down", "right", "left", "" (空字符串表示不动)
    """
    actions = {}
    # 你的 AI 逻辑在这里
    # ...
    return actions
```

#### 3. 关键数据结构

- **`world`**: `GameMap` 对象，包含地图信息
  - `world.width`, `world.height`: 地图尺寸
  - `world.middle_line`: 中线位置
  - `world.walls`: 障碍物集合
  - `world.my_team_target`: 己方目标区域
  - `world.opponent_team_target`: 敌方目标区域
  - `world.my_team_prison`: 己方监狱位置
  - `world.opponent_team_prison`: 敌方监狱位置

- **`req`**: 请求数据，包含当前游戏状态
  - `req["players"]`: 所有玩家信息（位置、是否在监狱、是否持旗等）
  - `req["flags"]`: 所有旗子信息（位置、是否被拾取等）
  - `req["map"]`: 地图信息

#### 4. 常用工具函数

项目提供了以下辅助函数（在 `server.py` 中定义）：

- **`is_in_enemy_territory(player, position)`**: 判断位置是否在敌方领地
- **`is_in_my_territory(player, position)`**: 判断位置是否在己方领地
- **`world.route_to(start, end)`**: 基础路径规划（BFS）
- **`improved_route(start, end, obstacles, enemy_influence)`**: 改进的路径规划（A*，考虑敌方影响）

#### 5. AI 策略示例

当前实现包含以下策略：

1. **防守策略 (`defence`)**: 在己方领地内拦截敌方玩家
2. **得分策略 (`scoring`)**: 前往敌方领地拾取旗子并返回
3. **救援策略 (`saving`)**: 前往监狱救援队友
4. **动态任务分配**: 根据得分差和敌方监狱人数动态调整策略

#### 6. 调试技巧

- 使用 `print()` 输出调试信息（会在后端控制台显示）
- 检查 `world` 对象的状态
- 验证路径规划结果
- 测试边界情况（如玩家在监狱、持旗等状态）

### 修改前端

前端使用 Phaser 3 游戏引擎开发，主要文件结构：

```
frontend/
├── index.html          # 主页面
├── game_config.json    # 游戏配置（服务器连接等）
├── src/
│   ├── main.js        # 游戏入口
│   ├── scenes/        # 游戏场景
│   │   ├── Boot.js    # 启动场景
│   │   ├── Preloader.js  # 预加载场景
│   │   ├── Game.js    # 主游戏场景
│   │   └── GameOver.js # 游戏结束场景
│   └── gameObjects/   # 游戏对象
│       ├── Player.js  # 玩家对象
│       └── Flag.js    # 旗子对象
└── assets/            # 游戏资源（图片、地图等）
```

#### 1. 修改游戏配置

编辑 `frontend/game_config.json`：

- **修改队伍配置**:
```json
{
  "teams": [
    { "name": "L", "who": "user48-1"},
    { "name": "R", "who": "user48-2"}
  ]
}
```

- **修改服务器连接**:
```json
{
  "servers": {
    "user48-1": "ws://0.0.0.0:34712",
    "user48-2": "ws://0.0.0.0:34713"
  }
}
```

- **修改游戏设置**:
```json
{
  "setup": {
    "numPlayers": 3,      // 每队玩家数量
    "numFlags": 9,        // 每队旗子数量
    "useRandomFlags": true // 是否随机生成旗子位置
  }
}
```

#### 2. 修改游戏逻辑

主要游戏逻辑在 `frontend/src/scenes/Game.js` 中：

- **修改玩家移动速度**: 查找 `playerSpeed` 相关代码
- **修改游戏规则**: 查找碰撞检测、得分逻辑等
- **修改 UI 显示**: 查找 HUD（抬头显示）相关代码

#### 3. 修改视觉效果

- **修改地图**: 编辑 `frontend/assets/tilemap.json` 或使用 Tiled 编辑器
- **修改角色外观**: 替换 `frontend/assets/characters.png`
- **修改旗子外观**: 替换 `frontend/assets/*_flag*.png`

#### 4. 调试前端

- 打开浏览器开发者工具（F12 或 Cmd+Option+I）
- 查看 Console 标签页查看日志
- 查看 Network 标签页检查 WebSocket 连接
- 确保禁用缓存（Disable cache）以加载最新代码

## 项目结构

```
CTF/
├── backend/           # 后端服务器（AI 逻辑）
│   ├── server.py     # 主服务器文件（AI 实现）
│   ├── lib/          # 游戏引擎库
│   │   ├── game_engine.py  # 游戏地图和路径规划
│   │   └── __init__.py
│   ├── teleop.py     # 手动控制脚本
│   └── ...
├── frontend/         # 前端游戏界面
│   ├── index.html    # 主页面
│   ├── game_config.json  # 游戏配置
│   ├── src/          # 源代码
│   └── assets/       # 游戏资源
└── README.md         # 本文件
```

## 手动控制

项目提供了手动控制脚本 `backend/teleop.py`，允许通过键盘控制玩家：

```bash
cd backend
python3 teleop.py <端口号>
```

控制键位：
- **L0**: `j`(左) `i`(上) `k`(下) `l`(右)
- **L1**: `t`(左) `f`(上) `g`(下) `h`(右)
- **L2**: `w`(上) `s`(下) `a`(左) `d`(右) 或方向键

按 `q` 退出手动控制。

## 原版说明（C++ 版本）

> 以下内容为原版 C++ 实现的说明，Python 版本已迁移到 `backend/server.py`

### Play

The game consists of 2 parts:
- __frontend/__: starts the game web server, written in Javascript. It optionally connects to 2 backend servers to move the players. You should NOT change the code, but you may read the code to understand how it generates the map and communicates with the backend.
- __backend/__: is the backend server which sends back instructions to frontend to move players. This is where you implement your algorithms. Note that in real competition, your server controls one team and the other is your opponent team's implementation.

To play it manually, you can use `w a s d` keys to control L team and `↑ ← ↓ →` keys to control R team. The keys override backend server's decisions. Note that the pressed keys move all players in one direction while your code can move each player independently.

Press SPACE KEY to start, pause or continue the game.

1. Install dependency
  ```
  brew update;
  brew install boost nlohmann-json
  ```
2. Compile server.cpp
  ```
  cd backend/;
  g++ -std=c++17 server.cpp -I/opt/homebrew/include -L/opt/homebrew/lib -lpthread -o server
  ```
3. Run server on port 8081 (can run on other ports)
  ```
  ./server 8081
  ```
4. Update `assets/remote_config.json` to the local port. Update `ws_url` with your port.
  ```
  {
    "teams": [
      { "name": "L", "ws_url": "ws://localhost:8080" },
      { "name": "R", "ws_url": "ws://localhost:8081" }
    ]
  }
  ```
5. Start frontend website
  ```
  cd frontend/;
  python3 -m http.server 8000
  ```
6. In your browser, open "http://localhost:8000/index.html" to play.
   - Press (Cmd + Option + I on macOS) to open DevTools
   - Go to the Network tab
   - Check ✅ "Disable cache" (upper-left toolbar) to ensure all your updated remote_config.json is loaded properly.

## Your Job

In `backend/server.py`, your need to implement `start_game(req)` and `plan_next_actions(req)` functions.
  - `start_game(req)` is called once when the game starts. `req` contains the game information, such as map (e.g., height, width, obstacle positions) and team (e.g., name, number of players and number of flags).
  - `plan_next_actions(req)` is called periodically to update you all the player and flags' information. You should use the return value to send back the actions taken for your team player. The current implementation uses rule-based AI with dynamic strategy adaptation.
  - `game_over(req)` is called once the game finishes and a winner is determined. You may clean up the state for the next `start_game`.

## Write up (Important!)

You must submit a markdown writeup consisting of the following:
1. The top 3-5 "strategic" decisions to compete against the opponents? Explain the intuition,
   the core idea and the technical details (such as the data structure & algorithms).
2. Some interesting and funny moments when you are testing your implementations, or competing
   with your friends. What changes did you make after the test?
