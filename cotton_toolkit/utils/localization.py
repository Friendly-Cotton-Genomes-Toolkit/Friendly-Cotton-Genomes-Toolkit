# cotton_toolkit/utils/localization.py

import gettext
import os
import sys
from typing import Callable

# 将应用名称常量移到这里，方便管理
APP_NAME_FOR_I18N = "cotton_toolkit"

def setup_localization(language_code: str = 'zh-hans', app_name: str = APP_NAME_FOR_I18N) -> Callable[[str], str]:
    """
    设置应用程序的国际化(i18n)支持。

    Args:
        language_code (str): 目标语言代码 (例如 'en', 'zh-hans')。
        app_name (str): 应用程序的翻译域名。

    Returns:
        Callable[[str], str]: 一个翻译函数，通常是 `_`。
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
            return lambda text: text

        lang_translation = gettext.translation(
            app_name,
            localedir=locales_dir,
            languages=[language_code],
            fallback=True  # 如果找不到语言，则退回到原始文本
        )
        return lang_translation.gettext
    except Exception as e:
        print(f"Warning: Could not set up language translation for '{language_code}'. Reason: {e}", file=sys.stderr)
        return lambda text: text