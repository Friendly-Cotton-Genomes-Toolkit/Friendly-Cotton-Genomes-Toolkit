# cotton_toolkit/tools/batch_ai_processor.py

import os
import time
from typing import Optional, Callable
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from diskcache import Cache
from functools import partial
from ..core.ai_wrapper import AIWrapper

# --- 国际化和日志设置 ---
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

# --- 全局变量 ---
CACHE_DIRECTORY_BASE = "tmp/.ai_cache"
client_global: 'AIWrapper'


def _prepare_cache(task_identifier: str, log: Callable) -> Optional[Cache]:
    """创建并返回指定任务的缓存对象。"""
    cache_directory = f"{CACHE_DIRECTORY_BASE}_{task_identifier}"
    try:
        os.makedirs(cache_directory, exist_ok=True)
        cache = Cache(cache_directory)
        log(f"任务 '{task_identifier}' 的缓存将使用目录: {os.path.abspath(cache_directory)}", "DEBUG")
        return cache
    except Exception as e:
        log(f"错误: 无法创建或访问缓存目录 {cache_directory}: {e}", "ERROR")
        return None


def _process_text_with_openai(
        text_to_process,
        cache: Cache,
        system_prompt,
        user_prompt_template,
        task_identifier,
        status_callback: Callable,  # 新增
        retries=3,
        delay=3):
    """使用AI API处理文本，具有重试、缓存和日志回调功能。"""
    if not text_to_process or not isinstance(text_to_process, str) or str(text_to_process).strip() == "":
        return ""

    cache_key = f"{task_identifier}::{str(text_to_process)}"
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    for attempt in range(retries):
        try:
            formatted_user_prompt = user_prompt_template.format(text=str(text_to_process))
            completion = client_global.process(
                text=text_to_process,
                custom_prompt_template=user_prompt_template
            )
            processed_text = completion.strip()

            if processed_text.startswith('"') and processed_text.endswith('"'):
                processed_text = processed_text[1:-1]
            if processed_text.startswith('“') and processed_text.endswith('”'):
                processed_text = processed_text[1:-1]

            if processed_text:
                cache.set(cache_key, processed_text)
            return processed_text
        except Exception as e:
            status_callback(
                f"API调用错误: {e}。在 {delay}秒 后重试 {attempt + 1}/{retries}。文本: '{str(text_to_process)[:30]}...'",
                "WARNING")
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                status_callback(f"警告: 经过 {retries} 次尝试后，文本 '{str(text_to_process)}' 处理失败。", "ERROR")
                return f"PROCESSING_ERROR: {e}"
    return "PROCESSING_ERROR: Max retries reached"


def _process_dataframe_openai_column(
        df_input: pd.DataFrame,
        cache: Cache,
        source_column_name: str,
        new_column_name: str,
        system_prompt: str,
        user_prompt_template: str,
        task_identifier: str,
        max_row_workers: int,
        status_callback: Callable,
        progress_callback: Callable
) -> pd.DataFrame:
    """在DataFrame的指定源列上运行AI处理，并将结果添加到新列。"""
    df = df_input.copy()

    if source_column_name not in df.columns:
        status_callback(f"警告: 列 '{source_column_name}' 在提供的DataFrame中未找到。", "WARNING")
        return df

    texts_to_process = df[source_column_name].tolist()
    process_func_for_row = partial(
        _process_text_with_openai,
        cache=cache,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        task_identifier=task_identifier,
        status_callback=status_callback
    )

    items_to_process = [str(text_data) if pd.notna(text_data) else "" for text_data in texts_to_process]
    processed_results = []
    total_items = len(items_to_process)

    if max_row_workers > 1 and total_items > 1:
        with ThreadPoolExecutor(max_workers=max_row_workers) as executor:
            future_to_index = {executor.submit(process_func_for_row, item): i for i, item in
                               enumerate(items_to_process)}
            results_list = [None] * total_items
            for i, future in enumerate(as_completed(future_to_index)):
                original_index = future_to_index[future]
                try:
                    results_list[original_index] = future.result()
                except Exception as exc:
                    results_list[original_index] = f"ERROR: {exc}"

                # 更新进度
                progress_callback((i + 1) * 100 // total_items, f"{_('正在处理行')} {i + 1}/{total_items}")
            processed_results = results_list
    else:
        for i, text_data in enumerate(items_to_process):
            processed_results.append(process_func_for_row(text_data))
            progress_callback((i + 1) * 100 // total_items, f"{_('正在处理行')} {i + 1}/{total_items}")

    df[new_column_name] = processed_results
    return df


def _process_csv_file(
        filepath: str,
        target_output_path: str,
        cache: Cache,
        source_column_name: str,
        new_column_name: str,
        system_prompt: str,
        user_prompt_template: str,
        task_identifier: str,
        max_row_workers: int,
        status_callback: Callable,
        progress_callback: Callable
):
    """处理单个CSV文件，现在传递回调函数。"""
    input_filename = os.path.basename(filepath)
    try:
        try:
            df = pd.read_csv(filepath, sep=',', encoding='utf-8')
        except UnicodeDecodeError:
            status_callback(f"文件 {input_filename} UTF-8解码失败，尝试GBK...", "INFO")
            df = pd.read_csv(filepath, sep=',', encoding='gbk')

        if source_column_name not in df.columns:
            status_callback(f"警告: 列 '{source_column_name}' 在 {input_filename} 中未找到。跳过。", "WARNING")
            return

        df_processed = _process_dataframe_openai_column(
            df, cache, source_column_name, new_column_name,
            system_prompt, user_prompt_template, task_identifier,
            max_row_workers, status_callback, progress_callback
        )

        os.makedirs(os.path.dirname(target_output_path), exist_ok=True)
        df_processed.to_csv(target_output_path, sep=',', index=False, encoding='utf-8-sig')
        status_callback(f"文件 {input_filename} 已处理并保存到: {target_output_path}", "INFO")

    except Exception as e:
        status_callback(f"处理文件 {input_filename} 时发生严重错误: {e}", "ERROR")


def process_single_csv_file(
        client: 'AIWrapper',
        input_csv_path: str,
        output_csv_directory: str,
        source_column_name: str,
        new_column_name: str,
        system_prompt: str,
        user_prompt_template: str,
        task_identifier: str,
        max_row_workers: int,
        status_callback: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
        output_csv_path: Optional[str] = None):
    """针对单个CSV文件进行分析处理，现在接收并使用回调函数。"""

    global client_global
    client_global = client

    log = status_callback if status_callback else print
    progress = progress_callback if progress_callback else lambda p, m: None

    cache = _prepare_cache(task_identifier, log)
    if cache is None:
        log(f"错误: 任务 '{task_identifier}' 的缓存初始化失败，处理中止。", "ERROR")
        return

    # (决定输出路径的逻辑保持不变)
    actual_target_output_path = ""
    if output_csv_path:
        actual_target_output_path = output_csv_path
    else:
        task_specific_output_dir = os.path.join(output_csv_directory, task_identifier)
        os.makedirs(task_specific_output_dir, exist_ok=True)
        base, ext = os.path.splitext(os.path.basename(input_csv_path))
        actual_target_output_path = os.path.join(task_specific_output_dir, f"{base}_{task_identifier}_processed{ext}")

    log(f"处理单个CSV文件: {os.path.abspath(input_csv_path)}", "INFO")
    log(f"源列名: '{source_column_name}', 新列名: '{new_column_name}'", "INFO")

    _process_csv_file(
        filepath=input_csv_path,
        target_output_path=actual_target_output_path,
        cache=cache,
        source_column_name=source_column_name,
        new_column_name=new_column_name,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        task_identifier=task_identifier,
        max_row_workers=max_row_workers,
        status_callback=log,
        progress_callback=progress
    )

    cache.close()
    log(f"任务 '{task_identifier}' 的磁盘缓存已关闭。", "DEBUG")