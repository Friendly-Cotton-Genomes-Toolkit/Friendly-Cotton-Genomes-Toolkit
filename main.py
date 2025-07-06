# main.py
# 这是应用程序的主入口文件
import sys
import traceback
from tkinter import messagebox
import tkinter as tk  # 仍然保留tkinter用于messagebox和Toplevel


# 移除了国际化函数占位符，因为不再使用gettext机制

# 1. --- 定义全局异常处理函数 ---
def show_uncaught_exception(exc_type, exc_value, exc_tb):
    """
    捕获所有未被处理的异常，并用弹窗显示详细信息。
    这是调试闪退问题的关键。
    """
    # 将详细的错误回溯信息格式化为字符串
    error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    # 创建一个临时的Tkinter窗口来承载错误弹窗
    # 以防主窗口自己就创建失败了
    error_window = tk.Toplevel()
    error_window.withdraw()  # 先隐藏这个临时窗口

    # 显示一个包含完整错误信息的弹窗
    messagebox.showerror(
        title="程序发生致命错误 (Fatal Error)",  # 硬编码中英文混搭
        message=f"An unhandled exception caused the program to terminate unexpectedly. Please report the following information to the developer:\n(一个未处理的异常导致程序意外终止，请将以下信息报告给开发者：)\n\n{error_message} ",
        # 硬编码中英文混搭
        parent=error_window  # 确保弹窗显示在最前面
    )
    error_window.destroy()
    sys.exit(1)  # 显示错误后退出


# 2. --- 设置全局钩子 ---
# 将我们上面定义的函数设置为Python的全局异常处理钩子
sys.excepthook = show_uncaught_exception


def main():
    """
    主函数，用于创建并运行应用实例。
    """
    # 这里我们只修改了导入路径，因为 gui_app 现在将使用 ttkbootstrap
    from ui.gui_app import CottonToolkitApp
    try:
        app = CottonToolkitApp()
        app.mainloop()
    except Exception:
        # 如果在app = CottonToolkitApp()这行就出错了，
        # 上面的全局钩子也能捕获到，这里是备用方案。
        show_uncaught_exception(*sys.exc_info())


if __name__ == "__main__":
    # 当直接运行 main.py 时，执行 main 函数
    main()
