# main.py
# 这是应用程序的主入口文件
import os
import sys
import traceback
from tkinter import messagebox
import tkinter as tk

# 1. --- 全局异常处理函数 (保持不变) ---
def show_uncaught_exception(exc_type, exc_value, exc_tb):
    """
    捕获所有未被处理的异常，并用弹窗显示详细信息。
    这是调试闪退问题的关键。
    """
    error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    error_window = tk.Toplevel()
    error_window.withdraw()
    messagebox.showerror(
        title="程序发生致命错误 (Fatal Error)",
        message=f"An unhandled exception caused the program to terminate unexpectedly. Please report the following information to the developer:\n(一个未处理的异常导致程序意外终止，请将以下信息报告给开发者：)\n\n{error_message}",
        parent=error_window
    )
    error_window.destroy()
    sys.exit(1)


# 2. --- 设置全局钩子 (保持不变) ---
sys.excepthook = show_uncaught_exception


# 3. --- 【核心修改】修改 main 函数 ---
def main():
    """
    主函数，用于设置环境、创建并运行应用实例。
    """
    # 导入所需的模块
    from ui.gui_app import CottonToolkitApp
    from cotton_toolkit.config.loader import load_config
    from cotton_toolkit.utils.localization import setup_localization

    # --- 步骤 1: 在创建UI前，加载配置并确定语言 ---
    DEFAULT_LANGUAGE = 'zh-hans'
    DEFAULT_CONFIG_PATH = 'config.yml'
    lang_code = DEFAULT_LANGUAGE

    try:
        if os.path.exists(DEFAULT_CONFIG_PATH):
            config = load_config(DEFAULT_CONFIG_PATH)
            lang_code = getattr(config, 'language', DEFAULT_LANGUAGE)
            print(f"Config file loaded. Language set to '{lang_code}'.")
        else:
            print(f"Config file not found at '{DEFAULT_CONFIG_PATH}'. Using default language '{lang_code}'.")
    except Exception as e:
        print(f"Error loading config, falling back to default language. Error: {e}")
        lang_code = DEFAULT_LANGUAGE

    # --- 步骤 2: 使用获取到的语言代码，初始化翻译功能 ---
    # setup_localization 会返回翻译函数，我们用一个变量接收它
    translator = setup_localization(lang_code)

    # --- 步骤 3: 启动主应用，并注入 translator ---
    try:
        # 【关键修复】将获取到的 translator 传递给 CottonToolkitApp 的构造函数
        app = CottonToolkitApp(translator=translator)
        app.mainloop()
    except Exception:
        # 如果在app的创建或运行中出错，全局钩子会捕获
        show_uncaught_exception(*sys.exc_info())


if __name__ == "__main__":
    main()