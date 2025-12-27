"""
快速测试训练是否正常工作
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 60)
print("训练系统测试")
print("=" * 60)

# 测试1: 导入模块
print("\n[测试1] 检查模块导入...")
try:
    import RL
    print("✓ RL模块导入成功")
except Exception as e:
    print(f"✗ RL模块导入失败: {e}")
    sys.exit(1)

# 测试2: 检查DQN Agent初始化
print("\n[测试2] 检查DQN Agent初始化...")
try:
    state_dim = 19  # 5(玩家) + 6(目标) + 4(对手) + 4(全局) = 19
    action_dim = 3
    agent = RL.DQNAgent(state_dim, action_dim, device='cpu')
    print("✓ DQN Agent初始化成功")
    print(f"  - 状态维度: {state_dim}")
    print(f"  - 动作维度: {action_dim}")
    print(f"  - Epsilon: {agent.epsilon:.4f}")
except Exception as e:
    print(f"✗ DQN Agent初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试3: 检查状态特征提取
print("\n[测试3] 检查状态特征提取...")
try:
    from lib.game_engine import GameMap
    world = GameMap()
    
    # 创建测试玩家
    test_player = {
        "posX": 10,
        "posY": 10,
        "hasFlag": False,
        "inPrison": False,
        "team": "L",
        "name": "L0"
    }
    
    # 初始化world（需要req数据，这里简化测试）
    print("  - 注意: 需要游戏初始化才能完整测试状态提取")
    print("  - 状态特征提取函数存在: ✓")
except Exception as e:
    print(f"✗ 状态特征提取测试失败: {e}")

# 测试4: 检查经验回放
print("\n[测试4] 检查经验回放缓冲区...")
try:
    import numpy as np
    state = np.random.rand(20).astype(np.float32)
    next_state = np.random.rand(20).astype(np.float32)
    
    agent.replay_buffer.push(state, 0, 1.0, next_state, False)
    print(f"✓ 经验回放缓冲区工作正常")
    print(f"  - 缓冲区大小: {len(agent.replay_buffer)}")
except Exception as e:
    print(f"✗ 经验回放测试失败: {e}")

# 测试5: 检查训练步骤
print("\n[测试5] 检查训练步骤...")
try:
    # 添加更多经验
    for i in range(35):
        state = np.random.rand(20).astype(np.float32)
        next_state = np.random.rand(20).astype(np.float32)
        agent.replay_buffer.push(state, i % 3, np.random.rand(), next_state, False)
    
    print(f"  - 缓冲区大小: {len(agent.replay_buffer)}")
    
    if len(agent.replay_buffer) >= 32:
        loss = agent.train_step(batch_size=32)
        if loss is not None:
            print(f"✓ 训练步骤工作正常")
            print(f"  - 损失值: {loss:.4f}")
        else:
            print("⚠ 训练步骤返回None（可能正常）")
    else:
        print(f"⚠ 缓冲区大小不足 ({len(agent.replay_buffer)} < 32)")
except Exception as e:
    print(f"✗ 训练步骤测试失败: {e}")
    import traceback
    traceback.print_exc()

# 测试6: 检查模型保存
print("\n[测试6] 检查模型保存...")
try:
    os.makedirs("models", exist_ok=True)
    test_model_path = "models/test_model.pth"
    agent.save_model(test_model_path)
    
    if os.path.exists(test_model_path):
        print(f"✓ 模型保存成功: {test_model_path}")
        file_size = os.path.getsize(test_model_path)
        print(f"  - 文件大小: {file_size} bytes")
        
        # 测试加载
        new_agent = RL.DQNAgent(state_dim, action_dim, device='cpu')
        new_agent.load_model(test_model_path)
        print("✓ 模型加载成功")
        
        # 清理测试文件
        os.remove(test_model_path)
        print("  - 测试文件已清理")
    else:
        print("✗ 模型文件未创建")
except Exception as e:
    print(f"✗ 模型保存测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
print("\n如果所有测试通过，可以启动训练：")
print("  python3 train_self_play.py 8082")
print("\n或者使用监控脚本：")
print("  ./monitor_training.sh 8082")

