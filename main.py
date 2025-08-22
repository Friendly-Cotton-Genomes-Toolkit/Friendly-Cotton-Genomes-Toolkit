# main.py
# 这是应用程序的主入口文件
import builtins
import json
import logging
import os
import sys
import traceback
import tkinter as tk
from tkinter import messagebox

import yaml

from cotton_toolkit.config.compatibility_check import check_config_compatibility, MainConfig


# 1. --- 全局异常处理函数 (保持不变) ---
def show_uncaught_exception(exc_type, exc_value, exc_tb):
    """
    捕获所有未被处理的异常，并用弹窗显示详细信息。
    这是调试闪退问题的关键。
    """
    # 尝试在调用 gettext 前获取翻译函数
    try:
        from builtins import _
    except ImportError:
        _ = lambda s: str(s)

    error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    # 创建一个临时的根窗口来显示消息框
    temp_root = tk.Tk()
    temp_root.withdraw()  # 隐藏临时窗口
    messagebox.showerror(
        title=_("程序发生致命错误 (Fatal Error)"),
        message=(
            _("一个未处理的异常导致程序意外终止，请将以下信息报告给开发者：") +
            "\n(An unhandled exception caused the program to terminate unexpectedly. "
            "Please report the following information to the developer:)\n\n"
            f"{error_message}"
        ),
        parent=temp_root
    )
    temp_root.destroy()
    sys.exit(1)


# 2. --- 设置全局钩子 ---
sys.excepthook = show_uncaught_exception


def main():
    """
    主函数，用于设置环境、创建并运行应用实例。
    """
    # 将模块导入移动到函数内部，以控制加载顺序
    from cotton_toolkit.config.loader import load_config
    from cotton_toolkit.utils.localization import setup_localization
    from cotton_toolkit.utils.logger import setup_global_logger

    # --- 步骤 1: 在创建UI前，加载配置并确定语言 ---
    DEFAULT_LANGUAGE = 'en'
    DEFAULT_CONFIG_PATH = 'config.yml'
    lang_code = DEFAULT_LANGUAGE

    # 在UI完全启动前，使用基本的日志记录
    setup_global_logger(log_level_str="INFO")

    try:
        if os.path.exists(DEFAULT_CONFIG_PATH):
            config = load_config(DEFAULT_CONFIG_PATH)

            # 确保读取正确的字段名 i18n_language
            lang_code = getattr(config, 'i18n_language', DEFAULT_LANGUAGE)
            logging.info(f"Config file loaded. Startup language set to '{lang_code}'.")

            # --- 检测配置文件兼容性 --- # 偷懒了，也只有简中和英语吧
            level, message = check_config_compatibility(config, lang_code)
            if level != 'info':
                temp_root = tk.Tk()
                temp_root.withdraw()

                if level == 'warning':
                    messagebox.showwarning(message=message,parent=temp_root)
                else:
                    messagebox.showerror(message=message,parent=temp_root)
                    temp_root.destroy()
                    sys.exit(1)

        else:
             # 在加载UI设置前尝试读取
            try:
                with open("config.yml", "r") as f:
                    ui_settings = yaml.load(f, Loader=yaml.FullLoader)
                    lang_code = ui_settings.get("language", DEFAULT_LANGUAGE)
                    logging.info(f"UI settings file loaded. Startup language set to '{lang_code}'.")
            except (FileNotFoundError, json.JSONDecodeError):
                 logging.info(f"Config file not found at '{DEFAULT_CONFIG_PATH}'. Using default language '{lang_code}'.")
    except Exception:
        show_uncaught_exception(*sys.exc_info())

    # --- 步骤 2: 使用获取到的语言代码，初始化翻译功能 ---
    # 这会设置全局的 _ 函数
    translator = setup_localization(lang_code)
    builtins._ = translator  # 确保 _ 函数在 builtins 中可用


    # --- 关键：现在才导入UI相关的类，确保它们在导入时能获得正确的翻译函数 ---
    from ui.gui_app import CottonToolkitApp

    # --- 步骤 4: 启动主应用，并注入 translator ---
    try:
        app = CottonToolkitApp(translator=translator)
        app.mainloop()
    except Exception:
        # 如果在app的创建或运行中出错，全局钩子会捕获
        show_uncaught_exception(*sys.exc_info())


if __name__ == "__main__":
    main()