import logging
from typing import Tuple, Dict, Any

from cotton_toolkit.config.models import MainConfig

# --- 常量定义 ---
LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"

# --- 将所有文本集中管理，以支持多语言 ---
# 扩展了语言支持，并为tkinter弹窗优化了换行(\n)
MESSAGES: Dict[str, Dict[str, str]] = {
    'en': {  # English
        'compatible': 'Configuration file version ({version}) is compatible.',
        'incompatible_old': (
            'Configuration File Incompatible!\n\n'
            'You are using an outdated version ({file_version}),\n'
            'while the application requires version ({latest_version}).\n\n'
            'Please update or regenerate your configuration file.'
        ),
        'incompatible_new': (
            'Configuration file version is newer than expected.\n\n'
            'File Version: {file_version}\n'
            'Application Version: {latest_version}\n\n'
            'While this may be backward-compatible, for best stability,\n'
            'using the matching configuration version is recommended.'
        )
    },

    'zh-hans': {  # Simplified Chinese (简体中文)
        'compatible': '配置文件版本 ({version}) 兼容，检查通过。',
        'incompatible_old': (
            '配置文件不兼容！\n\n'
            '您使用的是过时的版本 ({file_version})，\n'
            '而应用程序需要版本 ({latest_version})。\n\n'
            '请更新或重新生成您的配置文件。'
        ),
        'incompatible_new': (
            '配置文件版本高于预期。\n\n'
            '文件版本: {file_version}\n'
            '应用版本: {latest_version}\n\n'
            '这通常可以向后兼容，但为确保最佳稳定性，\n'
            '建议使用与应用程序匹配的配置文件。'
        )
    },
}

logger = logging.getLogger("cotton_toolkit.config.compatibility_check")


def check_config_compatibility(current_config: MainConfig, language: str = 'en') -> Tuple[str, str]:
    """
    检查加载的配置文件与应用程序要求的版本是否兼容。

    函数会同时在内部记录日志，并返回适合UI弹窗显示的格式化文本。

    Args:
        current_config: 从文件加载的配置对象。
        language: 输出语言 (例如: 'en', 'ja', 'zh-hans', 'zh-hant')。

    Returns:
        一个元组 (level, text)，其中：
        - level (str): 表示结果等级 ('info', 'warning', 'error')。
        - text (str): 对应的、已格式化的描述性文本。
    """
    file_version = current_config.config_version
    latest_version = 2

    level = LEVEL_INFO
    msg_key = 'compatible'
    format_args: Dict[str, Any] = {'version': file_version}

    if file_version < latest_version:
        level = LEVEL_ERROR
        msg_key = 'incompatible_old'
    elif file_version > latest_version:
        level = LEVEL_WARNING
        msg_key = 'incompatible_new'

    # 为不兼容的情况准备格式化参数
    if level != LEVEL_INFO:
        format_args = {'file_version': file_version, 'latest_version': latest_version}

    # 根据语言选择和消息键获取模板
    lang = language if language in MESSAGES else 'en'  # 如果语言不存在，默认使用英文
    template = MESSAGES[lang][msg_key]

    # 格式化最终文本
    text = template.format(**format_args)

    # 记录日志 (可以将多行文本替换为空格以便日志查看)
    log_text = text.replace('\n', ' ')
    if level == LEVEL_INFO:
        logger.info(log_text)
    elif level == LEVEL_WARNING:
        logger.warning(log_text)
    else:
        logger.error(log_text)

    return level, text


def old_file_updater():
    # 用于将旧版本的配置文件更新到最新版本。反正现在也没人用，就先不写了
    # Used to update configuration files from older versions to the latest. Since no one is using it anyway,
    # I'll just leave it unwritten for now.
    pass