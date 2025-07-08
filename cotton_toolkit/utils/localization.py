# 文件路径: cotton_toolkit/utils/localization.py

import gettext
import os
import sys
import builtins
from typing import Callable

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

APP_NAME_FOR_I18N = "cotton_toolkit"


def setup_localization(language_code: str = 'zh-hans') -> Callable[[str], str]:
    """
    设置应用程序的国际化(i18n)支持。
    此函数会：
    1. 将翻译函数安装到 builtins，使其全局可用。
    2. 返回该翻译函数，以便在需要时可以明确调用。
    """
    try:
        # 确定 locales 目录的位置
        if hasattr(sys, '_MEIPASS'):
            # 如果在打包的 .exe 中运行
            locales_dir = os.path.join(sys._MEIPASS, 'cotton_toolkit', 'locales')
        else:
            # 在正常的Python环境中运行
            locales_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'locales')

        if not os.path.isdir(locales_dir):
            print(f"Warning: Locales directory not found at '{locales_dir}'. Using fallback.", file=sys.stderr)
            # 如果找不到，安装一个不做任何事的函式，并返回它
            builtins._ = lambda text: text
            return builtins._

        # 找到翻译档案
        lang_translation = gettext.translation(
            "cotton_toolkit",  # 确保这里的域名和 .mo 文件名一致
            localedir=locales_dir,
            languages=[language_code],
            fallback=True  # 如果找不到语言，则退回到原始文本
        )

        # 【核心修正】
        # 1. 全局安装 `_` 函式，供所有模组隐性使用
        lang_translation.install()

        # 2. 明确返回 gettext 函式，供 UI Manager 等模组明确呼叫
        return lang_translation.gettext

    except Exception as e:
        print(f"Warning: Could not set up language translation for '{language_code}'. Reason: {e}", file=sys.stderr)
        # 出错时也要安装一个预设函式，并返回它
        builtins._ = lambda text: text
        return builtins._