# 文件路径: cotton_toolkit/utils/localization.py

import gettext
import os
import sys
import builtins
import logging # 修改: 导入logging
from typing import Callable

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

# 修改: 创建logger实例
logger = logging.getLogger("cotton_toolkit.utils.localization")

APP_NAME_FOR_I18N = "cotton_toolkit"


def setup_localization(language_code: str = 'zh-hans') -> Callable[[str], str]:
    """
    设置应用程序的国际化(i18n)支持。
    此函数会：
    1. 将翻译函数安装到 builtins，使其全局可用。
    2. 返回该翻译函数，以便在需要时可以明确调用。
    """
    try:
        if hasattr(sys, '_MEIPASS'):
            locales_dir = os.path.join(sys._MEIPASS, 'cotton_toolkit', 'locales')
        else:
            locales_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'locales')

        if not os.path.isdir(locales_dir):
            # 修改: 使用logger.warning
            logger.warning(f"Locales directory not found at '{locales_dir}'. Using fallback.")
            builtins._ = lambda text: text
            return builtins._

        lang_translation = gettext.translation(
            "cotton_toolkit",
            localedir=locales_dir,
            languages=[language_code],
            fallback=True
        )

        lang_translation.install()

        return lang_translation.gettext

    except Exception as e:
        logger.warning(f"Could not set up language translation for '{language_code}'. Reason: {e}")
        builtins._ = lambda text: text
        return builtins._