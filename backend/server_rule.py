"""
规则策略服务器
从server.py导入，但强制使用规则策略（USE_RL=False）
"""
import server

# 强制使用规则策略
server.USE_RL = False

# 导入main函数以便运行
if __name__ == "__main__":
    import asyncio
    import sys
    
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <port>")
        print(f"Example: python3 {sys.argv[0]} 8080")
        sys.exit(1)

    port = int(sys.argv[1])
    print(f"Rule-based AI backend running on port {port} ...")
    print("⚠️  使用规则策略（RL已禁用）")

    try:
        asyncio.run(server.main())
    except Exception as e:
        print(f"Server Stopped: {e}")
        sys.exit(1)

