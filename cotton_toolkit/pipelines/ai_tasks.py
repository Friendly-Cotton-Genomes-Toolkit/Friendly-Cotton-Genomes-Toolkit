import logging
import os
import threading
from typing import Optional, Dict, Any, Callable

from cotton_toolkit.config.models import MainConfig
from cotton_toolkit.core.ai_wrapper import AIWrapper
from cotton_toolkit.pipelines.decorators import pipeline_task
from cotton_toolkit.tools.batch_ai_processor import process_single_csv_file

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

logger = logging.getLogger("cotton_toolkit.pipeline.ai_task")

@pipeline_task(_("AI"))
def run_ai_task(
        config: MainConfig,
        input_file: str,
        source_column: str,
        new_column: str,
        task_type: str,
        custom_prompt_template: Optional[str],
        cli_overrides: Optional[Dict[str, Any]],
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        output_file: Optional[str] = None,
        **kwargs
):

    progress = kwargs['progress_callback']
    check_cancel = kwargs['check_cancel']


    progress(0, _("AI任务流程开始..."))
    logger.info(_("AI任务流程开始..."))
    if check_cancel(): return

    progress(5, _("正在解析AI服务配置..."))
    if check_cancel(): return

    ai_cfg = config.ai_services
    provider_name = cli_overrides.get('ai_provider') if cli_overrides else ai_cfg.default_provider
    model_name = cli_overrides.get('ai_model') if cli_overrides else None
    provider_cfg_obj = ai_cfg.providers.get(provider_name)
    if not provider_cfg_obj:
        logger.error(_("错误: 在配置中未找到AI服务商 '{}' 的设置。").format(provider_name))
        return
    if not model_name: model_name = provider_cfg_obj.model
    api_key = provider_cfg_obj.api_key
    base_url = provider_cfg_obj.base_url
    if not api_key or "YOUR_API_KEY" in api_key:
        logger.error(_("错误: 请在配置文件中为服务商 '{}' 设置一个有效的API Key。").format(provider_name))
        return

    proxies_to_use = config.proxies.model_dump(
        exclude_none=True) if ai_cfg.use_proxy_for_ai and config.proxies else None

    progress(10, _("正在初始化AI客户端..."))
    if check_cancel(): return

    logger.info(_("正在初始化AI客户端... 服务商: {}, 模型: {}").format(provider_name, model_name))
    ai_client = AIWrapper(provider=provider_name, api_key=api_key, model=model_name, base_url=base_url,
                          proxies=proxies_to_use, max_workers=config.batch_ai_processor.max_workers)

    prompt_to_use = custom_prompt_template or (
        config.ai_prompts.translation_prompt if task_type == 'translate' else config.ai_prompts.analysis_prompt)

    final_output_path = None
    if output_file is not None:
        output_directory = os.path.dirname(output_file)
        final_output_path = output_file
        logger.info(_("将在原文件上修改: {}").format(output_file))
    else:
        output_directory = os.path.dirname(input_file)
        logger.info(_("将创建新文件并保存于源文件目录: {}").format(output_directory))

    os.makedirs(output_directory, exist_ok=True)

    progress(15, _("正在处理CSV文件并调用AI服务..."))
    if check_cancel(): return

    # 修改: process_single_csv_file 不再需要 status_callback
    process_single_csv_file(
        client=ai_client,
        input_csv_path=input_file,
        output_csv_directory=output_directory,
        source_column_name=source_column,
        new_column_name=new_column,
        user_prompt_template=prompt_to_use,
        task_identifier=f"{os.path.basename(input_file)}_{task_type}",
        max_row_workers=config.batch_ai_processor.max_workers,
        progress_callback=lambda p, m: progress(15 + int(p * 0.8), _("AI处理: {}").format(m)),
        cancel_event=cancel_event,
        output_csv_path=final_output_path
    )

    if cancel_event and cancel_event.is_set():
        return

    progress(100, _("任务完成。"))
    logger.info(_("AI任务流程成功完成。"))
