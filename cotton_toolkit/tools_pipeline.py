# cotton_toolkit/tools_pipeline.py
import os
from typing import Dict, Any, Optional, Callable
import logging
from dataclasses import asdict

# 导入主配置模型，用于类型提示
from .config.models import MainConfig

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

# 动态导入项目中的工具和核心模块
try:
    from .tools.annotator import match_genes
    from .tools.batch_ai_processor import process_single_csv_file as ai_process
    from .core.ai_wrapper import AIWrapper

    SCRIPTS_LOADED = True
except ImportError as e:
    logging.warning(f"tools_pipeline.py: 无法导入脚本 ({e})")
    SCRIPTS_LOADED = False


    # MOCK函数，确保在缺少依赖时程序不会直接崩溃
    def match_genes(**kwargs):
        logging.error("MOCK FUNCTION CALLED: annotator.match_genes")
        return False


    def ai_process(**kwargs):
        logging.error("MOCK FUNCTION CALLED: batch_ai_processor.process_single_csv_file")
        return False


    class AIWrapper:
        def __init__(self, **kwargs):
            logging.error("MOCK CLASS INITIALIZED: AIWrapper")

        pass


def run_functional_annotation(
        config: MainConfig,
        input_file: str,
        output_dir: str,
        annotation_types: list[str],
        gene_column_name: str,
        status_callback: Optional[Callable[[str], None]] = print
) -> bool:
    """
    执行功能注释流程。

    遍历指定的注释类型，为输入文件中的基因列表匹配并生成对应的注释结果文件。
    """
    if not SCRIPTS_LOADED:
        status_callback(_("错误: 'annotator' 脚本未找到或加载失败。"))
        return False

    # 从配置中获取注释工具的详细设置
    tool_cfg = config.annotation_tool
    db_root = tool_cfg.database_root_dir
    db_files = tool_cfg.database_files
    db_cols = tool_cfg.database_columns

    if not os.path.exists(input_file):
        status_callback(f"[ERROR] {_('错误: 输入文件未找到:')} {input_file}")
        return False

    if not os.path.exists(db_root):
        status_callback(f"[ERROR] {_('错误: 注释数据库根目录未找到:')} {db_root}")
        return False

    os.makedirs(output_dir, exist_ok=True)
    status_callback(_("输出目录已确认: {}").format(output_dir))

    all_tasks_successful = True
    input_filename_base = os.path.splitext(os.path.basename(input_file))[0]

    # 循环处理每一种请求的注释类型
    for anno_type in annotation_types:
        status_callback(f"--- " + _("开始处理 {} 注释").format(anno_type.upper()) + " ---")

        db_filename = db_files.get(anno_type)
        if not db_filename:
            status_callback(f"[WARNING] {_('警告: 在配置中未找到类型为 {} 的数据库文件定义。').format(anno_type)}")
            continue

        db_filepath = os.path.join(db_root, db_filename)
        if not os.path.exists(db_filepath):
            status_callback(f"[ERROR] {_('错误: 注释数据库文件未找到:')} {db_filepath}")
            all_tasks_successful = False
            continue

        output_csv_filename = f"{input_filename_base}_{anno_type}_annotated.csv"
        output_csv_path = os.path.join(output_dir, output_csv_filename)

        try:
            # 调用 annotator.py 中的核心匹配函数
            match_genes(
                xlsx_file_path=input_file,
                csv_file_path=db_filepath,
                output_csv_path=output_csv_path,
                xlsx_gene_column=gene_column_name,
                csv_query_column=db_cols.query,
                csv_match_column=db_cols.match,
                csv_description_column=db_cols.description
            )
            status_callback(_("成功: {} 注释结果已保存到 {}").format(anno_type.upper(), output_csv_path))
        except Exception as e:
            status_callback(f"[ERROR] {_('处理 {} 注释时发生错误: {}').format(anno_type.upper(), e)}")
            all_tasks_successful = False

    return all_tasks_successful


def run_ai_task(
        config: MainConfig,
        input_file: str,
        output_dir: str,
        source_column: str,
        new_column: str,
        task_type: str,
        custom_prompt_template: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = print
) -> bool:
    """
    执行AI助手任务，使用大模型处理CSV文件中的一整列数据。
    """
    if not SCRIPTS_LOADED:
        status_callback(_("错误: AI相关工具脚本未找到或加载失败。"))
        return False

    # 从配置中获取AI服务的详细设置
    ai_cfg = config.ai_services
    provider_name = ai_cfg.default_provider
    provider_cfg_obj = ai_cfg.providers.get(provider_name)

    if not provider_cfg_obj:
        status_callback(f"[ERROR] {_('错误: 在配置中未找到默认AI服务商 ({}) 的设置。').format(provider_name)}")
        return False

    provider_cfg = asdict(provider_cfg_obj)  # 将dataclass转换为字典
    api_key = provider_cfg.get('api_key')
    model = provider_cfg.get('model')
    base_url = provider_cfg.get('base_url')

    if not api_key or "YOUR_API_KEY" in api_key:
        status_callback(
            f"[ERROR] {_('错误: 请在配置文件中为服务商 ({}) 设置一个有效的API Key。').format(provider_name)}")
        return False

    # 根据任务类型，确定使用的Prompt模板
    prompt_to_use = custom_prompt_template
    if not prompt_to_use:
        if task_type == 'translate':
            prompt_to_use = config.ai_prompts.translation_prompt
        elif task_type == 'analyze':
            prompt_to_use = config.ai_prompts.analysis_prompt
        else:
            status_callback(f"[ERROR] {_('错误: 未知的AI任务类型: {}').format(task_type)}")
            return False

    if not prompt_to_use or "{text}" not in prompt_to_use:
        status_callback(f"[ERROR] {_('错误: Prompt模板无效或缺少 {{text}} 占位符。')}")
        return False

    try:
        # 初始化AI封装器
        status_callback(_("正在初始化AI客户端... 服务商: {}, 模型: {}").format(provider_name, model))
        wrapper = AIWrapper(provider=provider_name, api_key=api_key, model=model, base_url=base_url)

        # 调用 batch_ai_processor.py 中的核心处理函数
        # 注意：ai_process 是 from .tools.batch_ai_processor import process_single_csv_file as ai_process
        success = ai_process(
            client=wrapper,
            input_csv_path=input_file,
            output_csv_directory=output_dir,  # batch_ai_processor 会在内部创建子目录
            source_column_name=source_column,
            new_column_name=new_column,
            system_prompt=_("你是一个专业的生物信息学分析助手。"),
            user_prompt_template=prompt_to_use,
            task_identifier=f"{os.path.basename(input_file)}_{task_type}",
            max_row_workers=config.downloader.max_workers  # 复用下载器的线程数设置
        )
        return success

    except Exception as e:
        status_callback(f"[ERROR] {_('执行AI任务时发生严重错误:')} {e}")
        return False