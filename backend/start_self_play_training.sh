#!/bin/bash
# 自对抗训练启动脚本
# 使用game_config.json中配置的端口：34712 (L队) 和 34713 (R队)
# 只启动AI后端，前端会自动连接

PORT1=34712  # L队 - RL训练agent
PORT2=34713  # R队 - 对手agent（规则策略或RL）

echo "=========================================="
echo "启动自对抗训练系统"
echo "=========================================="
echo "L队 (训练Agent): 端口 $PORT1"
echo "R队 (对手Agent): 端口 $PORT2"
echo "前端配置: game_config.json (user48-1, user48-2)"
echo "=========================================="

# 创建models目录
mkdir -p models

# 检查端口是否被占用
check_port() {
    if lsof -i :$1 > /dev/null 2>&1; then
        echo "⚠ 警告: 端口 $1 已被占用"
        echo "   正在尝试停止占用进程..."
        lsof -ti :$1 | xargs kill -9 2>/dev/null
        sleep 1
    fi
}

check_port $PORT1
check_port $PORT2

# 启动L队 - RL训练agent（使用train_self_play.py）
echo ""
echo "[1/2] 启动L队 - RL训练Agent (端口 $PORT1)..."
python3 train_self_play.py $PORT1 > training_l.log 2>&1 &
TRAIN_PID=$!
echo "  PID: $TRAIN_PID"
echo "  日志: training_l.log"

# 等待一下确保第一个服务器启动
sleep 2

# 启动R队 - 对手agent（使用server.py，规则策略）
echo ""
echo "[2/2] 启动R队 - 对手Agent (端口 $PORT2)..."
# 临时修改USE_RL为False（使用规则策略）
USE_RL=false python3 server.py $PORT2 > training_r.log 2>&1 &
OPPONENT_PID=$!
echo "  PID: $OPPONENT_PID"
echo "  日志: training_r.log"

echo ""
echo "=========================================="
echo "两个服务器已启动"
echo "=========================================="
echo "训练Agent PID: $TRAIN_PID (L队)"
echo "对手Agent PID: $OPPONENT_PID (R队)"
echo ""
echo "前端会自动连接到:"
echo "  L队: ws://localhost:$PORT1"
echo "  R队: ws://0.0.0.0:$PORT2"
echo ""
echo "查看训练日志:"
echo "  tail -f training_l.log  # L队训练日志"
echo "  tail -f training_r.log  # R队日志"
echo ""
echo "按 Ctrl+C 停止训练"
echo "=========================================="

# 清理函数
cleanup() {
    echo ""
    echo "正在停止服务器..."
    kill $TRAIN_PID $OPPONENT_PID 2>/dev/null
    wait $TRAIN_PID $OPPONENT_PID 2>/dev/null
    echo "服务器已停止"
    exit
}

# 捕获中断信号
trap cleanup INT TERM

# 等待进程
wait

