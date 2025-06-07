# cotton_toolkit/tools_pipeline.py
import os
from typing import Dict, Any, Optional, Callable
import logging

# 假设 _ 函数已由主程序设置
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

# 【重要】从新的、优化后的结构中导入模块
try:
    # 假设用户的脚本逻辑会被迁移到这些新位置
    # from .tools.annotator import match_genes
    # from .tools.batch_ai_processor import process_single_csv_file as ai_process
    from .core.ai_wrapper import AIWrapper

    SCRIPTS_LOADED = True
except ImportError as e:
    logging.warning(
        f"tools_pipeline.py: 无法从 'tools' 或 'core' 目录导入脚本 ({e})，将使用MOCK函数。请确保您已将脚本逻辑迁移到新位置。")
    SCRIPTS_LOADED = False


    # ... MOCK函数定义 ...
    def match_genes(**kwargs):
        logging.info(f"MOCK: Calling match_genes with {kwargs}"); return True


    def ai_process(**kwargs):
        logging.info(f"MOCK: Calling ai_process with {kwargs}"); return True


    class AIWrapper:
        pass


def run_functional_annotation(
        config: Dict[str, Any],
        input_file: str,
        output_dir: str,
        annotation_types: list[str],
        gene_column_name: str,
        status_callback: Optional[Callable[[str], None]] = print
) -> bool:
    """
    执行功能注释的后端函数。
    """
    if not SCRIPTS_LOADED:
        status_callback(_("错误: 'annotator' 脚本未找到或加载失败。"))
        return False

    tool_cfg = config.get('annotation_tool', {})
    db_root = tool_cfg.get('database_root_dir', 'annotation_databases')
    db_files = tool_cfg.get('database_files', {})
    db_cols = tool_cfg.get('database_columns', {})

    if not os.path.exists(input_file):
        status_callback(_("错误: 输入文件未找到: {}").format(input_file));
        return False
    if not os.path.exists(db_root):
        status_callback(_("错误: 注释数据库根目录 '{}' 未找到。").format(db_root));
        return False
    os.makedirs(output_dir, exist_ok=True)

    all_success = True
    for anno_type in annotation_types:
        if anno_type not in db_files or not db_files[anno_type]:
            status_callback(_("警告: 注释类型 '{}' 未在配置文件中定义或值为空，已跳过。").format(anno_type));
            continue

        db_path = os.path.join(db_root, db_files[anno_type])
        if not os.path.exists(db_path):
            status_callback(_("错误: 数据库文件 '{}' 未找到，已跳过。").format(db_path));
            all_success = False;
            continue

        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(output_dir, f"{base_name}_{anno_type}_annotated.csv")

        status_callback(_("正在运行 {} 注释...").format(anno_type.upper()))

        try:
            # 调用真实或模拟的 match_genes 函数
            success = match_genes(
                xlsx_file_path=input_file, csv_fullpath=db_path, output_csv_fullpath=output_file,
                xlsx_gene_column=gene_column_name, csv_query_column=db_cols.get('query', 'Query'),
                csv_match_column=db_cols.get('match', 'Match'),
                csv_description_column=db_cols.get('description', 'Description')
            )
            if success:
                status_callback(_("{} 注释完成。输出: {}").format(anno_type.upper(), output_file))
            else:
                status_callback(_("{} 注释失败。").format(anno_type.upper())); all_success = False
        except Exception as e:
            status_callback(_("执行 {} 注释时发生错误: {}").format(anno_type.upper(), e));
            all_success = False

    return all_success


def run_ai_task(
        config: Dict[str, Any],
        input_file: str,
        output_dir: str,
        source_column: str,
        new_column: str,
        task_type: str,
        custom_prompt_template: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = print
) -> bool:
    """
    执行AI任务的后端函数 (翻译或分析)。
    """
    if not SCRIPTS_LOADED:
        status_callback(_("错误: AI相关工具脚本未找到或加载失败。"));
        return False

    ai_cfg = config.get('ai_services', {})
    provider_name = ai_cfg.get('default_provider', 'google')
    provider_cfg = ai_cfg.get('providers', {}).get(provider_name, {})

    api_key = provider_cfg.get('api_key')
    base_url = provider_cfg.get('base_url')
    model = provider_cfg.get('model')
    proxy_url = config.get('downloader', {}).get('proxies', {}).get('https')

    if not all([api_key, base_url, model]) or "YOUR_" in api_key:
        status_callback(_("错误: AI服务配置不完整或未填写API Key。请在配置中正确设置。"));
        return False
    os.makedirs(output_dir, exist_ok=True)

    try:
        # 【修改】使用新的 AIWrapper 类
        ai_wrapper = AIWrapper(api_key=api_key, base_url=base_url, model=model, proxy_url=proxy_url)
    except Exception as e:
        status_callback(_("AI客户端初始化失败: {}").format(e));
        return False

    if task_type == 'translate':
        system_prompt = '你是一名专业的生物学专家和翻译官。会精准地翻译我给你的文本'
        user_prompt_template = "请翻译下面的内容为中文：{text}。翻译时请直接告诉我翻译的结果，无需其他任何补充说明"
        task_identifier = 'translation'
    elif task_type == 'analyze':
        if not custom_prompt_template: status_callback(_("错误: 分析任务需要提供自定义的用户提示模板。")); return False
        system_prompt = "你是一名专业的生物学家，会根据我提供的研究背景和文本内容，进行详细的关联性分析。"
        user_prompt_template = custom_prompt_template
        task_identifier = 'analysis'
    else:
        status_callback(_("错误: 未知的AI任务类型 '{}'").format(task_type));
        return False

    status_callback(_("开始AI任务: {}...").format(task_type))

    try:
        # 【修改】调用 ai_process 函数，并传入 ai_wrapper 实例
        # 注意：这要求您的 `universal_openai_request.py` (即 `batch_ai_processor.py`) 脚本中的
        # `process_single_csv_file` 函数能够接收一个 `ai_wrapper` 对象，并使用它来调用 .get_completion() 方法。
        success = ai_process(
            ai_wrapper=ai_wrapper,
            input_csv_path=input_file,
            output_csv_directory=output_dir,
            source_column_name=source_column,
            new_column_name=new_column,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
            task_identifier=task_identifier
        )
        if success:
            status_callback(_("AI任务 '{}' 完成。").format(task_type))
        else:
            status_callback(_("AI任务 '{}' 失败。").format(task_type))
        return success
    except Exception as e:
        status_callback(_("执行AI任务时发生错误: {}").format(e));
        return False