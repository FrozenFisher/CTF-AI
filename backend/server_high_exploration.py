"""
高探索度RL服务器
从server.py导入，使用RL模型但设置高探索率（epsilon）
用于增加策略多样性
"""
import server

# 使用RL模型
server.USE_RL = True

# 保存原始的start_game函数
original_start_game = server.start_game

def start_game_with_high_exploration(req):
    """修改后的start_game，设置高探索率"""
    # 调用原始函数初始化
    original_start_game(req)
    
    # 如果RL agent已初始化，设置高探索率
    if server.rl_agent is not None:
        # 设置高探索率（0.3 = 30%随机探索）
        server.rl_agent.epsilon = 0.3
        server.rl_agent.epsilon_end = 0.3  # 保持高探索，不衰减
        # 禁用epsilon衰减，保持高探索
        server.rl_agent.epsilon_decay = 1.0  # 不衰减
        print(f"✅ R队RL模型已加载，设置高探索率: epsilon={server.rl_agent.epsilon:.2f} (不衰减)")

# 替换start_game函数
server.start_game = start_game_with_high_exploration

# 导入main函数以便运行
if __name__ == "__main__":
    import asyncio
    import sys
    
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <port>")
        print(f"Example: python3 {sys.argv[0]} 8080")
        sys.exit(1)

    port = int(sys.argv[1])
    print(f"High-exploration RL AI backend running on port {port} ...")
    print("⚠️  使用RL模型，但设置高探索率（epsilon=0.3）以增加策略多样性")

    try:
        asyncio.run(server.main())
    except Exception as e:
        print(f"Server Stopped: {e}")
        sys.exit(1)

