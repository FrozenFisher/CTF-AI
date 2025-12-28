# 训练模块目录

本目录包含所有模型训练相关的脚本、工具和文档。

## 目录结构

```
training/
├── README.md                    # 本文件
├── README_TRAINING.md           # 训练使用指南
├── README_SELF_PLAY.md          # 自对抗训练指南
├── TRAINING_ANALYSIS.md         # 训练分析文档
│
├── train_rl.py                  # DQN模型训练脚本
├── train_self_play.py            # 自对弈训练脚本
├── train_direct.py               # 直接训练脚本（不依赖游戏服务器）
│
├── test_training.py             # 训练系统测试脚本
├── test_state_dim.py            # 状态维度测试脚本
├── visualize_training.py        # 训练可视化脚本
├── clear_training_data.py       # 清除训练数据脚本
│
├── start_self_play_training.sh  # 自对抗训练启动脚本
├── start_self_play.sh           # 自对弈启动脚本
└── monitor_training.sh          # 训练监控脚本
```

## 快速开始

### 1. 安装依赖

```bash
cd saved/CTF/backend
./install_dependencies.sh
```

### 2. 启动训练

**方法1：使用监控脚本（推荐）**
```bash
./training/monitor_training.sh 8082
```

**方法2：自对抗训练**
```bash
./training/start_self_play_training.sh
```

**方法3：直接训练（最快）**
```bash
python3 training/train_direct.py
```

## 训练脚本说明

### train_rl.py
- DQN模型训练脚本
- 需要游戏服务器运行
- 适合与规则策略对战训练

### train_self_play.py
- 自对弈训练脚本
- 可以与规则策略或另一个RL agent对战
- 支持自动保存模型和统计

### train_direct.py
- 直接训练脚本，不依赖游戏服务器
- 直接模拟游戏环境，训练速度最快
- 适合大规模训练

## 工具脚本

### test_training.py
测试训练系统是否正常工作

### test_state_dim.py
测试状态特征向量维度是否正确

### visualize_training.py
实时显示训练进度和统计信息

### clear_training_data.py
清除所有训练记录（模型、统计、日志等）

## 文档

- `README_TRAINING.md` - 详细的训练使用指南
- `README_SELF_PLAY.md` - 自对抗训练详细说明
- `TRAINING_ANALYSIS.md` - 训练分析和优化建议

## 注意事项

1. 所有训练脚本需要从 `backend/` 目录运行（不是从 `training/` 目录）
2. 训练脚本会自动访问父目录的 `lib/` 模块
3. 模型文件保存在 `lib/models/` 目录
4. 训练日志保存在 `backend/` 目录（如 `training_l.log`）

## 路径说明

训练脚本使用相对路径访问：
- `lib/` - 游戏引擎和RL模块
- `lib/models/` - 模型文件存储目录
- `pathfinding_adapter.py` - 路径规划适配器（train_direct.py需要）
- `server.py` - 游戏服务器（用于对战训练）

