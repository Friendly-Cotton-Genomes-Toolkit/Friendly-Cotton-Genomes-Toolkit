# cotton_toolkit/tools/batch_ai_processor.py

import os
import threading
import time
from typing import Optional, Callable
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from diskcache import Cache
from functools import partial
import logging

from ..core.ai_wrapper import AIWrapper

try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

# 修改: 创建 logger 实例
logger = logging.getLogger("cotton_toolkit.tools.batch_ai_processor")

CACHE_DIRECTORY_BASE = "tmp/.ai_cache"
client_global: 'AIWrapper'


def _prepare_cache(task_identifier: str) -> Optional[Cache]:
    cache_directory = f"{CACHE_DIRECTORY_BASE}_{task_identifier}"
    try:
        os.makedirs(cache_directory, exist_ok=True)
        cache = Cache(cache_directory)
        # 修改: 直接使用 logger
        logger.debug(_("任务 '{}' 的缓存目录: {}").format(task_identifier, os.path.abspath(cache_directory)))
        return cache
    except Exception as e:
        # 修改: 直接使用 logger
        logger.error(_("错误: 无法创建缓存目录 {}: {}").format(cache_directory, e))
        return None


def _process_text_with_ai(
        text_to_process: str,
        cache: Cache,
        user_prompt_template: str,
        task_identifier: str,
        retries: int = 3,
        delay: int = 5,
        cancel_event: Optional[threading.Event] = None,
) -> str:
    """
    使用 AIWrapper.process() 处理文本。
    """
    if cancel_event and cancel_event.is_set():
        return "PROCESSING_CANCELLED"

    if not text_to_process or not isinstance(text_to_process, str) or not text_to_process.strip():
        return ""

    cache_key = f"{task_identifier}::{user_prompt_template}::{text_to_process}"

    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    for attempt in range(retries):
        if cancel_event and cancel_event.is_set():
            return "PROCESSING_CANCELLED"

        try:
            global client_global
            processed_text = client_global.process(
                text=text_to_process,
                custom_prompt_template=user_prompt_template
            )

            if processed_text:
                if processed_text.startswith('"') and processed_text.endswith('"'):
                    processed_text = processed_text[1:-1]
                cache.set(cache_key, processed_text)
                return processed_text
            cache.set(cache_key, "")
            return ""
        except Exception as e:
            # 修改: 直接使用 logger
            logger.warning(_("API调用错误: {}。在 {}秒 后重试 {}/{}。").format(e, delay, attempt + 1, retries))

            if attempt < retries - 1:
                if cancel_event and cancel_event.is_set():
                    return "PROCESSING_CANCELLED"
                time.sleep(delay)
            else:
                # 修改: 直接使用 logger
                logger.error(
                    _("警告: 经过 {} 次尝试后，文本 '{}' 处理失败。").format(retries, text_to_process[:50] + '...'))
                return f"PROCESSING_ERROR: {e}"

    return _("PROCESSING_ERROR: Max retries reached")


def _process_dataframe_column(
        df_input: pd.DataFrame,
        cache: Cache,
        source_column_name: str,
        new_column_name: str,
        user_prompt_template: str,
        task_identifier: str,
        max_row_workers: int,
        progress_callback: Callable,
        cancel_event: Optional[threading.Event] = None
) -> pd.DataFrame:
    """在DataFrame的指定源列上运行AI处理，并将结果添加到新列。"""
    df = df_input.copy()

    if source_column_name not in df.columns:
        # 修改: 直接使用 logger
        logger.warning(_("警告: 列 '{}' 在DataFrame中未找到。").format(source_column_name))
        return df

    texts_to_process = df[source_column_name].tolist()
    process_func_for_row = partial(
        _process_text_with_ai,
        cache=cache,
        user_prompt_template=user_prompt_template,
        task_identifier=task_identifier,
        cancel_event=cancel_event
    )

    items_to_process = [str(text_data) if pd.notna(text_data) else "" for text_data in texts_to_process]
    total_items = len(items_to_process)
    results_list = [None] * total_items

    if max_row_workers > 1 and total_items > 1:
        with ThreadPoolExecutor(max_workers=max_row_workers) as executor:
            future_to_index = {executor.submit(process_func_for_row, item): i for i, item in
                               enumerate(items_to_process)}
            for i, future in enumerate(as_completed(future_to_index)):
                if cancel_event and cancel_event.is_set():
                    # 修改: 直接使用 logger
                    logger.info("任务已被用户取消。")
                    for f in future_to_index:
                        f.cancel()
                    break
                original_index = future_to_index[future]
                try:
                    results_list[original_index] = future.result()
                except Exception as exc:
                    results_list[original_index] = f"ERROR: {exc}"
                progress_callback(int((i + 1) * 100 / total_items), f"{_('正在处理行')} {i + 1}/{total_items}")
    else:
        for i, text_data in enumerate(items_to_process):
            if cancel_event and cancel_event.is_set():
                # 修改: 直接使用 logger
                logger.info("任务已被用户取消。")
                break
            results_list[i] = process_func_for_row(text_data)
            progress_callback(int((i + 1) * 100 / total_items), f"{_('正在处理行')} {i + 1}/{total_items}")

    try:
        source_col_index = df.columns.get_loc(source_column_name)
        df.insert(source_col_index + 1, new_column_name, results_list)
        # 修改: 直接使用 logger
        logger.debug(_("新列 '{}' 已插入到 '{}' 之后。").format(new_column_name, source_column_name))
    except Exception as e:
        # 修改: 直接使用 logger
        logger.error(_("插入新列时发生错误: {}。将新列附加到末尾作为备用方案。").format(e))
        df[new_column_name] = results_list

    return df


def _process_csv_file(
        filepath: str,
        target_output_path: str,
        cache: Cache,
        source_column_name: str,
        new_column_name: str,
        user_prompt_template: str,
        task_identifier: str,
        max_row_workers: int,
        progress_callback: Callable,
        cancel_event: Optional[threading.Event] = None
):
    """处理单个CSV文件。"""
    try:
        try:
            df = pd.read_csv(filepath, sep=',', encoding='utf-8')
        except UnicodeDecodeError:
            # 修改: 直接使用 logger
            logger.info(_("文件 {} UTF-8解码失败，尝试GBK...").format(os.path.basename(filepath)))
            df = pd.read_csv(filepath, sep=',', encoding='gbk')

        if source_column_name not in df.columns:
            # 修改: 直接使用 logger
            logger.warning(
                _("警告: 列 '{}' 在 {} 中未找到。跳过。").format(source_column_name, os.path.basename(filepath)))
            return

        df_processed = _process_dataframe_column(
            df, cache, source_column_name, new_column_name,
            user_prompt_template, task_identifier,
            max_row_workers, progress_callback,
            cancel_event=cancel_event
        )

        os.makedirs(os.path.dirname(target_output_path), exist_ok=True)
        df_processed.to_csv(target_output_path, sep=',', index=False, encoding='utf-8-sig')
        # 修改: 直接使用 logger
        logger.info(
            _("文件 {} 已处理并保存到: {}").format(os.path.basename(filepath), os.path.basename(target_output_path)))


    except Exception as e:
        # 修改: 直接使用 logger
        logger.error(_("处理文件 {} 时发生严重错误: {}").format(os.path.basename(filepath), e))


def process_single_csv_file(
        client: 'AIWrapper',
        input_csv_path: str,
        output_csv_directory: str,
        source_column_name: str,
        new_column_name: str,
        user_prompt_template: str,
        task_identifier: str,
        max_row_workers: int,
        progress_callback: Optional[Callable] = None,
        output_csv_path: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None
):
    """针对单个CSV文件进行分析处理。"""
    global client_global
    client_global = client

    progress = progress_callback if progress_callback else lambda p, m: None

    # 修改: _prepare_cache不再接收log参数
    cache = _prepare_cache(task_identifier)
    if cache is None:
        # 修改: 直接使用 logger
        logger.error(_("错误: 任务 '{}' 的缓存初始化失败，处理中止。").format(task_identifier))
        return

    actual_target_output_path = ""
    if output_csv_path:
        actual_target_output_path = output_csv_path
    else:
        task_specific_output_dir = output_csv_directory
        os.makedirs(task_specific_output_dir, exist_ok=True)
        base, ext = os.path.splitext(os.path.basename(input_csv_path))
        actual_target_output_path = os.path.join(task_specific_output_dir, f"{base}_ai_processed{ext}")

    # 修改: 直接使用 logger
    logger.info(_("处理单个CSV文件: {}").format(os.path.abspath(input_csv_path)))

    _process_csv_file(
        filepath=input_csv_path,
        target_output_path=actual_target_output_path,
        cache=cache,
        source_column_name=source_column_name,
        new_column_name=new_column_name,
        user_prompt_template=user_prompt_template,
        task_identifier=task_identifier,
        max_row_workers=max_row_workers,
        progress_callback=progress,
        cancel_event=cancel_event
    )

    cache.close()
    # 修改: 直接使用 logger
    logger.debug(_("任务 '{}' 的磁盘缓存已关闭。").format(task_identifier))