"""
PORTAL STRIKE 2042 — Python 第一人称射击游戏 (战地风格)

运行:
    pip install pygame PyOpenGL numpy
    python main.py                         单人 (主菜单)
    python main.py --connect 1.2.3.4:27960 直接连接专用服务器
    python -m net.server --bots 3          启动专用服务器 (无渲染)
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    from core import settings as S
    ap = argparse.ArgumentParser(description="PORTAL STRIKE 2042")
    ap.add_argument("--width", type=int, default=S.SCREEN_WIDTH)
    ap.add_argument("--height", type=int, default=S.SCREEN_HEIGHT)
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--connect", type=str, default=None, help="host:port")
    ap.add_argument("--autotest", type=str, default=None, help=argparse.SUPPRESS)
    a = ap.parse_args()
    connect = None
    if a.connect:
        host, _, port = a.connect.partition(":")
        connect = (host, int(port or S.DEFAULT_PORT))
    autotest = None
    if a.autotest:
        from tools.autotest import AutoTest
        autotest = AutoTest(a.autotest)
    from client.app import App
    App(a.width, a.height, a.fullscreen, autotest, connect).run()


if __name__ == "__main__":
    main()
