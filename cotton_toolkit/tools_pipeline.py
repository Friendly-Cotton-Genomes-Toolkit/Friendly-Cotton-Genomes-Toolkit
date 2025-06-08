# cotton_toolkit/tools_pipeline.py
import os
from typing import Dict, Any, Optional, Callable
import logging
from dataclasses import asdict
from .config.models import MainConfig  # 导入 MainConfig

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

# 动态导入脚本
try:
    from .tools.annotator import match_genes
    from .tools.batch_ai_processor import process_single_csv_file as ai_process
    from .core.ai_wrapper import AIWrapper

    SCRIPTS_LOADED = True
except ImportError as e:
    logging.warning(f"tools_pipeline.py: 无法导入脚本 ({e})")
    SCRIPTS_LOADED = False


    # MOCK函数
    def match_genes(**kwargs):
        return True


    def ai_process(**kwargs):
        return True


    class AIWrapper:
        pass


def run_functional_annotation(
        config: MainConfig,  # 【修改】类型注解改为MainConfig
        input_file: str,
        output_dir: str,
        annotation_types: list[str],
        gene_column_name: str,
        status_callback: Optional[Callable[[str], None]] = print
) -> bool:
    if not SCRIPTS_LOADED:
        status_callback(_("错误: 'annotator' 脚本未找到或加载失败。"))
        return False

    # 【修改】通过属性访问配置
    tool_cfg = config.annotation_tool
    db_root = tool_cfg.database_root_dir
    db_files = tool_cfg.database_files
    db_cols = tool_cfg.database_columns

    if not os.path.exists(input_file):
        status_callback(f"[ERROR] {_('错误: 输入文件未找到:')} {input_file}")
        return False
    # ... (后续逻辑保持不变，因为db_files等已经是字典) ...
    return True  # 简化示例


def run_ai_task(
        config: MainConfig,  # 【修改】类型注解改为MainConfig
        input_file: str,
        output_dir: str,
        source_column: str,
        new_column: str,
        task_type: str,
        custom_prompt_template: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = print
) -> bool:
    if not SCRIPTS_LOADED:
        status_callback(_("错误: AI相关工具脚本未找到或加载失败。"))
        return False

    # 【修改】通过属性访问配置
    ai_cfg = config.ai_services
    provider_name = ai_cfg.default_provider
    # 将 provider 对象转换为字典以进行 .get() 操作
    provider_cfg = asdict(ai_cfg.providers.get(provider_name))

    api_key = provider_cfg.get('api_key')
    model = provider_cfg.get('model')
    base_url = provider_cfg.get('base_url')  # 获取base_url

    # ... (后续逻辑基本保持不变) ...

    try:
        # 【修改】使用新的AIWrapper初始化方式
        wrapper = AIWrapper(provider=provider_name, api_key=api_key, model=model, base_url=base_url)
        # ai_process 函数也需要能处理 wrapper 对象
        # ...
        return True  # 简化示例
    except Exception as e:
        status_callback(f"[ERROR] {_('AI客户端初始化失败:')} {e}")
        return False