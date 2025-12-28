#!/bin/bash
# 自对弈训练启动脚本
# 同时启动两个服务器进行对战训练

# 配置
PORT1=${1:-8080}  # 第一个服务器端口（RL训练agent）
PORT2=${2:-8081}  # 第二个服务器端口（对手agent）

echo "=========================================="
echo "启动自对弈训练"
echo "=========================================="
echo "训练Agent端口: $PORT1"
echo "对手Agent端口: $PORT2"
echo "=========================================="

# 切换到backend目录（脚本的父目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BACKEND_DIR"

# 创建models目录
mkdir -p models

# 启动训练agent（使用train_self_play.py）
echo "启动训练Agent (端口 $PORT1)..."
python3 training/train_self_play.py $PORT1 &
TRAIN_PID=$!

# 等待一下确保第一个服务器启动
sleep 2

# 启动对手agent（使用server.py，规则策略）
echo "启动对手Agent (端口 $PORT2)..."
# 修改server.py中的USE_RL=False来使用规则策略
USE_RL=false python3 server.py $PORT2 &
OPPONENT_PID=$!

echo ""
echo "两个服务器已启动"
echo "训练Agent PID: $TRAIN_PID"
echo "对手Agent PID: $OPPONENT_PID"
echo ""
echo "按 Ctrl+C 停止训练"
echo "=========================================="

# 等待用户中断
trap "echo ''; echo '正在停止服务器...'; kill $TRAIN_PID $OPPONENT_PID 2>/dev/null; wait; echo '服务器已停止'; exit" INT TERM

# 等待进程
wait

