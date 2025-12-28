# RL模型对抗可视化指南

## 快速开始

### 方法1：使用可视化脚本（推荐）

```bash
cd saved/CTF/backend
python3 visualize_battle.py
```

这会自动：
- 检查模型文件是否存在
- 清理占用端口的进程
- 启动两个服务器：
  - **L队**：使用训练好的RL模型 (`models/dqn_model_latest.pth`)，标准探索率
  - **R队**：使用训练好的RL模型，但设置高探索率（epsilon=0.3）以增加策略多样性
- 显示前端访问信息

### 方法2：手动启动

**终端1 - 启动RL模型服务器（L队）：**
```bash
cd saved/CTF/backend
python3 server.py 34712
```

**终端2 - 启动高探索度RL服务器（R队）：**
```bash
cd saved/CTF/backend
python3 server_high_exploration.py 34713
```

## 前端观察

1. **启动前端服务器：**
```bash
cd saved/CTF/frontend
python3 -m http.server 8000
```

2. **在浏览器打开：**
```
http://localhost:8000/index.html
```

前端会自动连接到两个后端服务器，可以实时观察：
- RL模型（L队，标准探索）vs RL模型（R队，高探索率）的对抗
- 双方的移动策略差异
- 高探索率带来的策略多样性
- 得分情况
- 游戏进程

## 配置说明

### 模型路径

默认使用 `./models/dqn_model_latest.pth`

可以在 `server.py` 中修改：
```python
RL_MODEL_PATH = "./models/dqn_model_latest.pth"
```

### 端口配置

默认端口：
- L队（RL模型）：34712
- R队（规则策略）：34713

这些端口与 `frontend/game_config.json` 中的配置对应：
- `user48-1`: ws://0.0.0.0:34712
- `user48-2`: ws://0.0.0.0:34713

### 服务器类型

有三种服务器类型可选：

1. **server.py** - 标准RL模型（标准探索率）
   ```bash
   python3 server.py 34712
   ```

2. **server_high_exploration.py** - RL模型但高探索率（epsilon=0.3，不衰减）
   ```bash
   python3 server_high_exploration.py 34713
   ```

3. **server_rule.py** - 规则策略（不使用RL）
   ```bash
   python3 server_rule.py 34713
   ```

## 观察要点

### RL模型表现

观察两个RL模型的以下行为：

**L队（标准探索）：**
- **探索策略**：是否主动寻找敌方旗帜
- **防御策略**：是否有效拦截敌方玩家
- **协作能力**：多个玩家是否协调行动
- **路径规划**：是否避开障碍物和敌人

**R队（高探索率）：**
- **策略多样性**：是否尝试更多不同的策略
- **探索行为**：是否更频繁地尝试新动作
- **适应性**：是否能应对不同情况

### 对比分析

对比标准探索和高探索率：
- **策略稳定性**：标准探索更稳定，高探索更随机
- **策略多样性**：高探索率带来更多变化
- **学习效果**：观察不同探索率对游戏结果的影响

## 停止服务器

按 `Ctrl+C` 停止 `visualize_battle.py`，脚本会自动：
- 停止两个服务器进程
- 清理资源

## 故障排除

### 端口被占用

如果提示端口被占用：
```bash
# 查找占用端口的进程
lsof -i :34712
lsof -i :34713

# 终止进程
kill -9 <PID>
```

或者直接运行 `visualize_battle.py`，它会自动清理。

### 模型文件不存在

如果提示模型文件不存在：
1. 检查模型路径是否正确
2. 确认模型文件是否存在：
```bash
ls -lh models/dqn_model_latest.pth
```
3. 如果不存在，需要先训练模型：
```bash
python3 training/train_direct.py
```

### 前端无法连接

1. 检查后端服务器是否正常运行
2. 检查端口是否正确
3. 检查 `frontend/game_config.json` 中的端口配置
4. 检查浏览器控制台是否有错误信息

## 高级用法

### 使用不同的模型

修改 `visualize_battle.py` 中的模型路径：
```python
MODEL_PATH = "./models/dqn_model_ep1000.pth"  # 使用特定episode的模型
```

### 两个RL模型对抗

修改 `visualize_battle.py`，让R队也使用RL模型：
```python
# 在启动R队时，不设置 USE_RL=false
# 并确保R队加载不同的模型
```

### 记录对抗结果

可以修改脚本添加统计功能，记录：
- 胜率
- 平均得分
- 游戏时长
- 策略分析

