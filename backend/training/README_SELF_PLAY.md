# 自对抗训练使用指南

## 快速启动

使用配置好的端口（34712和34713）启动自对抗训练：

```bash
cd saved/CTF/backend
./training/start_self_play_training.sh
```

## 配置说明

### 端口配置

根据 `game_config.json`：
- **L队 (训练Agent)**: 端口 `34712` (user48-1)
- **R队 (对手Agent)**: 端口 `34713` (user48-2)

### 前端连接

前端会自动连接到这两个端口，无需手动配置。

## 训练模式

### 当前配置

- **L队**: 使用RL训练agent（`training/train_self_play.py`）
  - 收集经验并训练模型
  - 每10个episode保存模型
  - 显示训练统计

- **R队**: 使用规则策略（`server.py` with `USE_RL=false`）
  - 简单的规则策略作为对手
  - 用于训练RL agent

### 修改对手类型

如果想使用另一个RL agent作为对手，修改 `training/train_self_play.py`：

```python
USE_OPPONENT_RL = True  # 改为True
OPPONENT_MODEL_PATH = "./models/dqn_model_latest.pth"  # 指定对手模型
```

## 训练输出

### 日志文件

- `training_l.log` - L队（训练agent）的日志
- `training_r.log` - R队（对手agent）的日志

### 实时查看

```bash
# 查看L队训练日志
tail -f training_l.log

# 查看R队日志
tail -f training_r.log

# 同时查看两个日志
tail -f training_l.log training_r.log
```

### 模型保存

训练过程中会自动保存：
- `models/dqn_model_latest.pth` - 最新模型
- `models/dqn_model_ep{N}.pth` - 每10个episode的检查点
- `models/training_stats.json` - 训练统计

## 前端观察

1. 启动前端服务器：
```bash
cd saved/CTF/frontend
python3 -m http.server 8000
```

2. 在浏览器打开：
```
http://localhost:8000/index.html
```

3. 前端会自动连接到两个后端服务器，可以实时观察训练过程。

## 停止训练

按 `Ctrl+C` 停止训练，脚本会自动：
- 停止两个服务器进程
- 保存最终模型
- 保存训练统计

## 训练监控

启动可视化监控（另一个终端）：

```bash
python3 training/visualize_training.py lib/models/training_stats.json 5
```

## 注意事项

1. 确保端口34712和34713未被占用
2. 如果端口被占用，脚本会自动尝试停止占用进程
3. 训练需要PyTorch等依赖，确保已安装
4. 前端会自动连接，无需手动配置

