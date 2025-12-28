#!/usr/bin/env python3
"""
改进的 HTTP 服务器，确保正确处理根路径和静态文件
"""
import http.server
import socketserver
import os
import sys

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义请求处理器，确保根路径返回 index.html"""
    
    def end_headers(self):
        # 添加 CORS 头，允许跨域请求
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()
    
    def do_GET(self):
        # 如果请求根路径，重定向到 index.html
        if self.path == '/' or self.path == '':
            self.path = '/index.html'
        
        # 检查文件是否存在
        file_path = self.path.lstrip('/')
        if file_path and os.path.exists(file_path):
            # 文件存在，使用父类方法处理
            return super().do_GET()
        elif self.path == '/index.html' and not os.path.exists('index.html'):
            # index.html 不存在，返回 404
            self.send_error(404, "File not found: index.html")
            return
        
        # 使用父类方法处理其他请求
        return super().do_GET()
    
    def log_message(self, format, *args):
        """自定义日志格式"""
        # 过滤掉 favicon.ico 等常见请求的日志
        if 'favicon.ico' not in args[0]:
            super().log_message(format, *args)

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    
    # 检查 index.html 是否存在
    if not os.path.exists('index.html'):
        print(f"⚠️  警告：index.html 不存在！")
        print(f"   当前目录: {os.getcwd()}")
        print(f"   请确保在 frontend 目录下运行此脚本")
        sys.exit(1)
    
    # 检查 game_config.json 是否存在
    if not os.path.exists('game_config.json'):
        print(f"⚠️  警告：game_config.json 不存在！")
    
    print("=" * 60)
    print(f"启动 HTTP 服务器")
    print("=" * 60)
    print(f"端口: {port}")
    print(f"目录: {os.getcwd()}")
    print(f"访问: http://localhost:{port}/")
    print(f"      http://localhost:{port}/index.html")
    print("=" * 60)
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)
    
    try:
        with socketserver.TCPServer(("0.0.0.0", port), CustomHTTPRequestHandler) as httpd:
            httpd.serve_forever()
    except OSError as e:
        if e.errno == 48:  # Address already in use
            print(f"❌ 错误：端口 {port} 已被占用")
            print(f"   请使用其他端口或终止占用该端口的进程")
        else:
            print(f"❌ 错误：{e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n服务器已停止")
        sys.exit(0)

if __name__ == "__main__":
    main()

