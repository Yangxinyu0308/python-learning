"""
程序入口：默认打开图形界面；加 --nogui 就走命令行。

    python main.py                      # 打开窗口
    python main.py --nogui 狂飙 -p 3     # 命令行抓 3 页

在 VSCode 里直接按 F5，用的是 .vscode/launch.json 里配好的启动方式。
"""

import sys


def main():
    if "--nogui" in sys.argv or "--cli" in sys.argv:
        args = [arg for arg in sys.argv[1:] if arg not in ("--nogui", "--cli")]
        import cli
        return cli.main(args)

    try:
        import gui
    except ImportError as error:
        print(f"打不开图形界面：{error}")
        print("这台电脑的 Python 好像没带 tkinter。可以改用命令行：")
        print("    python main.py --nogui 狂飙")
        return 1
    gui.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
