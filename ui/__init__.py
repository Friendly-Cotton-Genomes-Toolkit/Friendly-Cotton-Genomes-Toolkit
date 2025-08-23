import os

from .dialogs import MessageDialog,ProgressDialog
from .tabs.annotation_tab import AnnotationTab


def get_persistent_settings_path():
    """获取用户主目录中持久化UI设置文件的路径。"""
    home_dir = os.path.expanduser("~")
    settings_dir = os.path.join(home_dir, ".fcgt")
    # 此函数只解析路径，不创建目录
    return os.path.join(settings_dir, "ui_settings.json")
