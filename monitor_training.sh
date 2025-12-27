#!/bin/bash
# 训练监控脚本
# 同时启动训练和可视化监控

PORT=${1:-8082}

echo "=========================================="
echo "启动训练监控系统"
echo "=========================================="
echo "训练端口: $PORT"
echo "=========================================="

# 创建models目录
mkdir -p models

# 启动训练（后台）
echo "启动训练进程..."
python3 train_self_play.py $PORT > training.log 2>&1 &
TRAIN_PID=$!

echo "训练进程 PID: $TRAIN_PID"
echo "日志文件: training.log"
echo ""

# 等待一下让训练开始
sleep 3

# 启动可视化监控
echo "启动可视化监控..."
echo "按 Ctrl+C 停止监控和训练"
echo "=========================================="

python3 visualize_training.py models/training_stats.json 5

# 停止训练进程
echo ""
echo "正在停止训练进程..."
kill $TRAIN_PID 2>/dev/null
wait $TRAIN_PID 2>/dev/null
echo "训练已停止"

