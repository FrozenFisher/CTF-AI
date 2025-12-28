#!/bin/bash
# 安装训练所需的依赖

echo "=========================================="
echo "安装DQN训练依赖"
echo "=========================================="

# 检查pip
if ! command -v pip3 &> /dev/null; then
    echo "错误: 未找到pip3，请先安装Python"
    exit 1
fi

echo "正在安装依赖..."
echo ""

# 安装PyTorch (CPU版本，如果需要GPU版本请修改)
echo "[1/3] 安装PyTorch..."
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

echo ""
echo "[2/3] 安装NumPy..."
pip3 install numpy

echo ""
echo "[3/3] 安装Matplotlib..."
pip3 install matplotlib

echo ""
echo "=========================================="
echo "依赖安装完成！"
echo "=========================================="
echo ""
echo "验证安装..."
python3 -c "import torch; print(f'✓ PyTorch {torch.__version__}')"
python3 -c "import numpy; print(f'✓ NumPy {numpy.__version__}')"
python3 -c "import matplotlib; print(f'✓ Matplotlib {matplotlib.__version__}')"
echo ""
echo "现在可以运行训练了："
echo "  python3 training/train_self_play.py 8082"
echo "  或"
echo "  ./training/monitor_training.sh 8082"

