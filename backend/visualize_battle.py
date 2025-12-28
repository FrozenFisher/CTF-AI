#!/usr/bin/env python3
"""
可视化RL模型对抗脚本
启动两个服务器：一个使用训练好的RL模型，一个使用规则策略
可以通过前端观察对抗过程
"""

import subprocess
import time
import os
import sys
import signal
import threading

# 配置
PORT_RL = 34712  # RL模型服务器端口（L队）
PORT_RULE = 34713  # 规则策略服务器端口（R队）
MODEL_PATH = "./lib/models/dqn_model_latest.pth"  # RL模型路径

def check_port(port):
    """检查端口是否被占用"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0

def print_output(pipe, prefix):
    """实时打印进程输出"""
    try:
        for line in iter(pipe.readline, ''):
            if line:
                print(f"[{prefix}] {line.rstrip()}")
        pipe.close()
    except Exception as e:
        print(f"[{prefix}] 输出读取错误: {e}")

def kill_port(port):
    """终止占用端口的进程"""
    try:
        if os.name == 'nt':  # Windows
            # 使用 netstat 和 findstr 查找占用端口的进程
            result = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True,
                text=True
            )
            # 查找占用指定端口的进程
            for line in result.stdout.split('\n'):
                if f':{port}' in line and 'LISTENING' in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        try:
                            subprocess.run(['taskkill', '/F', '/PID', pid], 
                                         capture_output=True)
                            print(f"  已终止进程 {pid} (端口 {port})")
                        except:
                            pass
        else:  # Unix/Linux/Mac
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'],
                capture_output=True,
                text=True
            )
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                        print(f"  已终止进程 {pid} (端口 {port})")
                        time.sleep(0.5)  # 等待进程终止
                    except ProcessLookupError:
                        # 进程已经不存在
                        pass
                    except Exception as e:
                        print(f"  警告：无法终止进程 {pid}: {e}")
    except FileNotFoundError:
        print(f"  警告：无法找到 lsof 命令，请手动终止占用端口 {port} 的进程")
    except Exception as e:
        print(f"  警告：清理端口 {port} 时出错: {e}")

def main():
    print("=" * 60)
    print("RL模型对抗可视化")
    print("=" * 60)
    
    # 检查模型文件
    if not os.path.exists(MODEL_PATH):
        print(f"❌ 错误：模型文件不存在: {MODEL_PATH}")
        print("   请先训练模型或检查模型路径")
        sys.exit(1)
    
    print(f"✅ 模型文件: {MODEL_PATH}")
    
    # 检查端口
    if check_port(PORT_RL):
        print(f"⚠️  端口 {PORT_RL} 已被占用，正在清理...")
        kill_port(PORT_RL)
        time.sleep(2)  # 等待进程完全终止
        # 再次检查端口是否已释放
        if check_port(PORT_RL):
            print(f"❌ 错误：端口 {PORT_RL} 仍被占用，请手动终止相关进程")
            sys.exit(1)
    
    if check_port(PORT_RULE):
        print(f"⚠️  端口 {PORT_RULE} 已被占用，正在清理...")
        kill_port(PORT_RULE)
        time.sleep(2)  # 等待进程完全终止
        # 再次检查端口是否已释放
        if check_port(PORT_RULE):
            print(f"❌ 错误：端口 {PORT_RULE} 仍被占用，请手动终止相关进程")
            sys.exit(1)
    
    # 创建models目录
    os.makedirs("models", exist_ok=True)
    
    print(f"\n启动服务器...")
    print(f"  L队 (RL模型): 端口 {PORT_RL}")
    print(f"  R队 (规则策略): 端口 {PORT_RULE}")
    print(f"\n前端配置:")
    print(f"  L队: ws://localhost:{PORT_RL}")
    print(f"  R队: ws://0.0.0.0:{PORT_RULE}")
    print("\n" + "=" * 60)
    
    # 启动RL模型服务器（L队）
    print(f"\n[1/2] 启动L队 - RL模型服务器 (端口 {PORT_RL})...")
    try:
        rl_server = subprocess.Popen(
            [sys.executable, "server.py", str(PORT_RL)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 将stderr合并到stdout
            text=True,
            bufsize=1
        )
        print(f"  PID: {rl_server.pid}")
        
        # 启动线程实时打印输出
        rl_output_thread = threading.Thread(
            target=print_output,
            args=(rl_server.stdout, "L队"),
            daemon=True
        )
        rl_output_thread.start()
        
        # 等待服务器启动并检查是否成功
        time.sleep(3)
        if rl_server.poll() is not None:
            # 进程已退出
            print(f"❌ L队服务器启动失败 (退出码: {rl_server.returncode})")
            sys.exit(1)
        
        # 检查端口是否真的在监听
        if not check_port(PORT_RL):
            print(f"⚠️  警告：端口 {PORT_RL} 似乎未在监听，但进程仍在运行")
        else:
            print(f"  ✅ L队已启动（使用RL模型: {MODEL_PATH}）")
    except Exception as e:
        print(f"❌ 启动L队服务器时出错: {e}")
        sys.exit(1)
    
    # 启动规则策略服务器（R队）
    print(f"\n[2/2] 启动R队 - 规则策略服务器 (端口 {PORT_RULE})...")
    try:
        # 使用server_rule.py（纯规则策略，不使用RL）
        rule_server = subprocess.Popen(
            [sys.executable, "server_rule.py", str(PORT_RULE)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 将stderr合并到stdout
            text=True,
            bufsize=1
        )
        print(f"  PID: {rule_server.pid}")
        
        # 启动线程实时打印输出
        r_output_thread = threading.Thread(
            target=print_output,
            args=(rule_server.stdout, "R队"),
            daemon=True
        )
        r_output_thread.start()
        
        # 等待服务器启动并检查是否成功
        time.sleep(3)
        if rule_server.poll() is not None:
            # 进程已退出
            print(f"❌ R队服务器启动失败 (退出码: {rule_server.returncode})")
            # 清理已启动的L队服务器
            rl_server.terminate()
            sys.exit(1)
        
        # 检查端口是否真的在监听
        if not check_port(PORT_RULE):
            print(f"⚠️  警告：端口 {PORT_RULE} 似乎未在监听，但进程仍在运行")
        else:
            print(f"  ✅ R队已启动（使用规则策略，RL已禁用）")
    except Exception as e:
        print(f"❌ 启动R队服务器时出错: {e}")
        # 清理已启动的L队服务器
        rl_server.terminate()
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("两个服务器已启动")
    print("=" * 60)
    print(f"L队 (RL模型) PID: {rl_server.pid}")
    print(f"R队 (规则策略) PID: {rule_server.pid}")
    print("\n前端访问:")
    print(f"  1. 启动前端服务器:")
    print(f"     cd ../frontend && python3 -m http.server 8000")
    print(f"  2. 在浏览器打开:")
    print(f"     http://localhost:8000/index.html")
    print("\n按 Ctrl+C 停止服务器")
    print("=" * 60)
    
    def cleanup():
        print("\n\n正在停止服务器...")
        rl_server.terminate()
        rule_server.terminate()
        try:
            rl_server.wait(timeout=5)
            rule_server.wait(timeout=5)
        except:
            rl_server.kill()
            rule_server.kill()
        print("服务器已停止")
    
    try:
        # 等待用户中断
        while True:
            time.sleep(1)
            # 检查进程是否还在运行
            if rl_server.poll() is not None:
                print(f"\n⚠️  L队服务器已停止 (退出码: {rl_server.returncode})")
                break
            if rule_server.poll() is not None:
                print(f"\n⚠️  R队服务器已停止 (退出码: {rule_server.returncode})")
                break
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()

if __name__ == "__main__":
    main()

