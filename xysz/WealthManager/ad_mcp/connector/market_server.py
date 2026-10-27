"""本地市场 zip 托管服务（调试方式一）。

被 Windows 计划任务拉起，独立于会话存活；根目录固定为市场包所在目录。
用法：python market_server.py [端口]
"""
import os
import sys

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = r"D:\WealthManager\xysz\WealthManager\ad_mcp\connector\marketplace"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8130


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 不刷日志，避免撑爆计划任务日志
        pass


def main():
    # 不使用 os.chdir（避免进程 cwd 锁住目录导致无法删除/重建），
    # 改用 SimpleHTTPRequestHandler 的 directory 参数
    if not os.path.exists(os.path.join(ROOT, "connector-plugins.zip")):
        raise SystemExit("connector-plugins.zip not found in " + ROOT)
    handler = type("H", (SimpleHTTPRequestHandler,),
                   {"directory": ROOT, "log_message": lambda self, fmt, *a: None})
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    srv.serve_forever()


if __name__ == "__main__":
    main()