import os
from typing import Optional, Tuple, Union, List  # Added Union, List

import pandas as pd


import time
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from shutil import rmtree
from diskcache import Cache
from functools import partial

from cotton_toolkit.core.ai_wrapper import AIWrapper

# --- 全局变量 ---
# 缓存文件存储目录 (通用名称)
CACHE_DIRECTORY_BASE = "tmp/.openai_cache"  # 基础目录

client_global: 'AIWrapper'  # Forward declaration if AIWrapper is complex or defined later
current_cache_directory: str  # 将根据任务设置


# --- 缓存准备函数 ---
def _prepare_cache(task_identifier: str) -> Optional[Cache]:
    """
    创建并返回指定任务的缓存对象。

    Args:
        task_identifier (str): 任务标识符。

    Returns:
        Optional[Cache]: diskcache缓存对象，如果创建失败则为None。
    """
    global current_cache_directory
    current_cache_directory = f"{CACHE_DIRECTORY_BASE}_{task_identifier}"
    try:
        os.makedirs(current_cache_directory, exist_ok=True)
        cache = Cache(current_cache_directory)
        print(f"任务 '{task_identifier}' 的处理缓存将使用目录: {os.path.abspath(current_cache_directory)}")
        return cache
    except Exception as e:
        print(f"错误: 无法创建或访问缓存目录 {current_cache_directory}: {e}")
        return None


# --- 通用OpenAI文本处理函数 (带重试和缓存) ---
def _process_text_with_openai(
        text_to_process,
        cache: Cache,
        system_prompt,
        user_prompt_template,
        task_identifier,
        retries=3,
        delay=3):
    """
    使用自定义的、与OpenAI兼容的API处理文本，具有重试和缓存功能。

    Args:
        text_to_process (str): 需要处理的文本。
        cache (Cache): diskcache缓存对象。
        system_prompt (str): 系统提示词。
        user_prompt_template (str): 用户提示词模板，使用{text}占位。
        task_identifier (str): 任务标识符，用于区分缓存。
        retries (int): 最大重试次数。
        delay (int): 重试间隔（秒）。

    Returns:
        str: 处理后的文本结果，或错误标记字符串。
    """
    processing_error_marker = f"处理错误标记 ({task_identifier}): {str(text_to_process)[:50]}..."

    if not text_to_process or not isinstance(text_to_process, str) or str(text_to_process).strip() == "":
        return ""

    cache_key = f"{task_identifier}::{str(text_to_process)}"  # 确保缓存键对任务是唯一的
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    for attempt in range(retries):
        try:
            global client_global
            formatted_user_prompt = user_prompt_template.format(text=str(text_to_process))
            completion = client_global.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": formatted_user_prompt}
                ],
            )
            processed_text = completion.choices[0].message.content
            if processed_text is not None:
                processed_text = processed_text.strip()
            else:
                processed_text = ""

            if processed_text.startswith('"') and processed_text.endswith('"'):
                processed_text = processed_text[1:-1]
            if processed_text.startswith('“') and processed_text.endswith('”'):
                processed_text = processed_text[1:-1]

            if processed_text:
                cache.set(cache_key, processed_text)
            return processed_text
        except Exception as e:
            print(
                f"任务 {task_identifier} 的API调用错误: {e}。在 {delay}秒 后重试 {attempt + 1}/{retries}。文本: '{str(text_to_process)[:30]}...'")
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                print(
                    f"警告: 经过 {retries} 次尝试后，文本 '{str(text_to_process)}' 为任务 '{task_identifier}' 处理失败。")
                return processing_error_marker
    return processing_error_marker


# --- DataFrame OpenAI列处理辅助函数 ---
def _process_dataframe_openai_column(
        df_input: pd.DataFrame,
        cache: Cache,
        source_column_name: str,
        new_column_name: str,
        system_prompt: str,
        user_prompt_template: str,
        task_identifier: str,
        max_row_workers: int,
        log_prefix: str = ""
) -> pd.DataFrame:
    """
    在DataFrame的指定源列上运行OpenAI处理，并将结果添加到新列。

    Args:
        df_input (pd.DataFrame): 输入的DataFrame。
        cache (Cache): diskcache缓存对象。
        source_column_name (str): 需要处理的源列名。
        new_column_name (str): 新增的结果列名。
        system_prompt (str): 系统提示词。
        user_prompt_template (str): 用户提示词模板。
        task_identifier (str): 任务标识符 (用于缓存键和日志)。
        max_row_workers (int): 行级并发线程数。
        log_prefix (str): 日志和进度条的前缀。

    Returns:
        pd.DataFrame: 带有已处理列的新DataFrame副本。如果源列不存在，则返回原始DataFrame副本。
    """
    df = df_input.copy()  # 操作副本以避免修改原始DataFrame

    if source_column_name not in df.columns:
        print(f"{log_prefix}警告: 列 '{source_column_name}' 在提供的DataFrame中未找到。将返回原始数据。")
        return df

    texts_from_column = df[source_column_name].tolist()
    process_func_for_row = partial(_process_text_with_openai,
                                   cache=cache,
                                   system_prompt=system_prompt,
                                   user_prompt_template=user_prompt_template,
                                   task_identifier=task_identifier)  # 使用主任务标识符以共享缓存

    items_to_process = [str(text_data) if pd.notna(text_data) else "" for text_data in texts_from_column]
    processed_results = []
    tqdm_desc = f"{log_prefix}处理行 ({task_identifier})"

    if max_row_workers > 1 and len(items_to_process) > 1:
        with ThreadPoolExecutor(max_workers=max_row_workers) as row_executor:
            processed_results_iterator = row_executor.map(process_func_for_row, items_to_process)
            processed_results = list(tqdm(processed_results_iterator,
                                          total=len(items_to_process),
                                          desc=tqdm_desc,
                                          unit="行", leave=True, mininterval=0.5,
                                          ncols=100))  # leave=True for sheet context
    else:
        for text_data in tqdm(items_to_process,
                              desc=tqdm_desc,
                              unit="行", leave=True, mininterval=0.5, ncols=100):  # leave=True
            processed_results.append(process_func_for_row(text_data))

    try:
        source_col_index = df.columns.get_loc(source_column_name)
    except KeyError:
        # 此检查理论上多余，因为函数开始时已检查，但作为安全措施保留
        print(f"{log_prefix}内部错误: 列 '{source_column_name}' 查找失败。将返回原始数据。")
        return df

    if new_column_name in df.columns:
        print(f"{log_prefix}信息: 列 '{new_column_name}' 已存在，将被覆盖。")
        df[new_column_name] = processed_results
    else:
        df.insert(source_col_index + 1, new_column_name, processed_results)

    return df


# --- CSV文件处理函数 ---
def _process_csv_file(filepath: str,
                      target_output_path: str,
                      cache: Cache,
                      source_column_name: str,
                      new_column_name: str,
                      system_prompt: str,
                      user_prompt_template: str,
                      task_identifier: str,
                      max_row_workers: int):
    """
    处理单个CSV文件：读取内容，对指定列应用OpenAI处理，
    添加带有结果的新列，并保存到指定的输出文件路径。使用缓存。
    (此函数与您先前版本中的逻辑基本一致，现在使用 _process_dataframe_openai_column)
    """
    input_filename = os.path.basename(filepath)
    try:
        try:
            df = pd.read_csv(filepath, sep=',', encoding='utf-8')
        except UnicodeDecodeError:
            print(f"信息: 文件 {input_filename} UTF-8解码失败，尝试GBK...")
            df = pd.read_csv(filepath, sep=',', encoding='gbk')
        except FileNotFoundError:
            return f"错误: 输入文件 {filepath} 未找到。"
        except Exception as read_err:
            return f"读取输入文件 {filepath} 错误: {read_err}"

        if source_column_name not in df.columns:
            print(f"警告: 列 '{source_column_name}' 在 {input_filename} 中未找到。跳过。")
            return f"已跳过 (原因: 缺少 '{source_column_name}' 列): {input_filename}"

        # 使用新的辅助函数处理DataFrame
        df_processed = _process_dataframe_openai_column(
            df, cache, source_column_name, new_column_name,
            system_prompt, user_prompt_template, task_identifier,
            max_row_workers, log_prefix=f"文件'{input_filename}': "
        )

        target_output_dir = os.path.dirname(target_output_path)
        if target_output_dir:
            os.makedirs(target_output_dir, exist_ok=True)

        df_processed.to_csv(target_output_path, sep=',', index=False, encoding='utf-8-sig')
        return f"成功: 文件 {input_filename} 已为任务 '{task_identifier}' 处理并保存到: {target_output_path}"

    except Exception as e:
        return f"处理文件 {input_filename} (任务: '{task_identifier}') 时发生严重错误并尝试写入 {target_output_path}: {e}"


def process_single_csv_file(client: 'AIWrapper',
                            input_csv_path: str,
                            output_csv_directory: str,
                            source_column_name: str,
                            new_column_name: str,
                            system_prompt: str,
                            user_prompt_template: str,
                            task_identifier: str,
                            max_row_workers: int,
                            output_csv_path: Optional[str] = None):
    """
    针对单个CSV文件进行分析处理。

    Args:
        client (AIWrapper): OpenAI API封装对象。
        input_csv_path (str): 输入CSV文件路径。
        output_csv_directory (str): 输出目录的根路径。
                                     仅在`output_csv_path`未提供时，用于构建默认输出路径。
        source_column_name (str): 需要处理的源列名。
        new_column_name (str): 新增的结果列名。
        system_prompt (str): 系统提示词。
        user_prompt_template (str): 用户提示词模板，使用{text}占位符。
        task_identifier (str): 任务标识符 (用于缓存和默认输出子目录/文件名)。
        max_row_workers (int): 行级并发线程数。
        output_csv_path (Optional[str]): 可选参数。如果提供，则指定输出CSV文件的确切路径。
                                         此时 `output_csv_directory` 将被忽略。
                                         如果此路径与 `input_csv_path` 相同，文件将被覆盖。

    Returns:
        None
    """

    global client_global
    client_global = client

    cache = _prepare_cache(task_identifier)
    if cache is None:
        print(f"错误: 任务 '{task_identifier}' 的缓存初始化失败，处理中止。")
        return

    actual_target_output_path: str

    if output_csv_path:
        actual_target_output_path = os.path.abspath(output_csv_path)
        output_parent_dir = os.path.dirname(actual_target_output_path)
        if output_parent_dir:
            os.makedirs(output_parent_dir, exist_ok=True)
        print(f"\n将直接输出到指定路径: {actual_target_output_path}")
    else:
        task_specific_output_dir = os.path.join(output_csv_directory, task_identifier)
        if os.path.isdir(task_specific_output_dir):
            print(f"警告: 任务 '{task_identifier}' 的默认输出目录 '{task_specific_output_dir}' 已存在。正在清空它。")
            try:
                rmtree(task_specific_output_dir)
            except OSError as e:
                print(f"错误: 无法移除已存在的默认输出目录 {task_specific_output_dir}: {e}")
                cache.close()
                return
        try:
            os.makedirs(task_specific_output_dir, exist_ok=True)
        except OSError as e:
            print(f"错误: 无法创建默认输出目录 {task_specific_output_dir}: {e}")
            cache.close()
            return

        input_filename = os.path.basename(input_csv_path)
        base, ext = os.path.splitext(input_filename)
        actual_target_output_path = os.path.join(task_specific_output_dir, f"{base}_{task_identifier}_processed{ext}")
        print(f"\n输出将保存到默认构造路径: {actual_target_output_path}")

    print(f"处理单个CSV文件: {os.path.abspath(input_csv_path)}")
    print(f"源列名: '{source_column_name}', 新列名: '{new_column_name}'")
    print("-" * 30)

    result = _process_csv_file(
        filepath=input_csv_path,
        target_output_path=actual_target_output_path,
        cache=cache,
        source_column_name=source_column_name,
        new_column_name=new_column_name,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        task_identifier=task_identifier,
        max_row_workers=max_row_workers
    )
    print(result)
    cache.close()
    print(f"任务 '{task_identifier}' 的磁盘缓存已关闭。")


# --- Excel文件处理主函数 ---
def process_single_excel_file(client: 'Wrapper',
                              input_excel_path: str,
                              source_column_name: str,
                              new_column_name: str,
                              system_prompt: str,
                              user_prompt_template: str,
                              task_identifier: str,
                              max_row_workers: int,
                              output_excel_directory: str | None = None,
                              output_excel_path: str | None = None,
                              sheet_name: Optional[Union[str, int, List[Union[str, int]]]] = None):
    """
    针对单个Excel文件进行分析处理，支持指定工作表。

    Args:
        client (AIWrapper): OpenAI API封装对象。
        input_excel_path (str): 输入Excel文件路径。
        output_excel_directory (str): 输出目录的根路径。
                                     仅在`output_excel_path`未提供时，用于构建默认输出路径。
        source_column_name (str): 需要处理的源列名。
        new_column_name (str): 新增的结果列名。
        system_prompt (str): 系统提示词。
        user_prompt_template (str): 用户提示词模板。
        task_identifier (str): 任务标识符 (用于缓存和默认输出子目录/文件名)。
        max_row_workers (int): 行级并发线程数。
        output_excel_path (Optional[str]): 可选。指定输出Excel文件的确切路径。
                                           此时 `output_excel_directory` 将被忽略。
                                           如果此路径与 `input_excel_path` 相同，文件将被覆盖。
        sheet_name (Optional[Union[str, int, List[Union[str, int]]]]):
                                           可选。指定要处理的工作表。
                                           可以是单个表名(str)，单个索引(int)，或它们的列表。
                                           如果为None，则尝试处理所有包含源列的工作表。
    Returns:
        None
    """

    if not output_excel_path and not output_excel_directory:
        raise ValueError('未填写输出路径或目录')

    global client_global  # 假设 client_global 是这样使用的
    client_global = client

    # 假设 _prepare_cache 函数已定义
    cache = _prepare_cache(task_identifier)
    if cache is None:
        print(f"错误: 任务 '{task_identifier}' 的缓存初始化失败，处理中止。")
        return

    actual_target_output_path: str
    task_specific_output_dir = ""  # 初始化，以便在后续的 except 块中使用

    if output_excel_path:
        actual_target_output_path = os.path.abspath(output_excel_path)
        output_parent_dir = os.path.dirname(actual_target_output_path)
        if output_parent_dir:
            os.makedirs(output_parent_dir, exist_ok=True)
        print(f"\n将直接输出Excel到指定路径: {actual_target_output_path}")
    else:
        task_specific_output_dir = os.path.join(output_excel_directory, task_identifier)
        if os.path.isdir(task_specific_output_dir):
            print(f"警告: 任务 '{task_identifier}' 的默认Excel输出目录 '{task_specific_output_dir}' 已存在。正在清空它。")
            try:
                rmtree(task_specific_output_dir)
            except OSError as e:
                print(f"错误: 无法移除已存在的默认Excel输出目录 {task_specific_output_dir}: {e}")
                if cache: cache.close()
                return
        try:
            os.makedirs(task_specific_output_dir, exist_ok=True)
        except OSError as e:
            print(f"错误: 无法创建默认Excel输出目录 {task_specific_output_dir}: {e}")
            if cache: cache.close()
            return

        input_filename = os.path.basename(input_excel_path)
        base, _ = os.path.splitext(input_filename)
        output_file_ext = ".xlsx"
        actual_target_output_path = os.path.join(task_specific_output_dir,
                                                 f"{base}_{task_identifier}_processed{output_file_ext}")
        print(f"\nExcel输出将保存到默认构造路径: {actual_target_output_path}")

    print(f"处理单个Excel文件: {os.path.abspath(input_excel_path)}")
    print(f"源列名: '{source_column_name}', 新列名: '{new_column_name}'")
    if sheet_name is not None:
        print(f"指定处理的表单: {sheet_name}")
    else:
        print("未指定特定表单，将尝试处理所有包含源列的表单。")
    print("-" * 30)

    try:
        xls = pd.ExcelFile(input_excel_path)
    except FileNotFoundError:
        print(f"错误: 输入Excel文件 {input_excel_path} 未找到。")
        if cache: cache.close()
        return
    except Exception as e:
        print(f"错误: 读取Excel文件元数据或初步解析 {input_excel_path} 失败: {e}")
        print("这通常表明输入文件本身已损坏或格式不兼容。请检查输入文件。")
        if cache: cache.close()
        return

    all_sheet_names_in_file = xls.sheet_names
    sheets_to_explicitly_process = []

    if sheet_name is not None:
        user_wants_sheets = []
        if isinstance(sheet_name, (str, int)):
            user_wants_sheets = [sheet_name]
        elif isinstance(sheet_name, list):
            user_wants_sheets = sheet_name
        else:
            print(f"警告: 无效的 sheet_name 类型 '{type(sheet_name)}'。将默认尝试处理所有表单。")
            user_wants_sheets = all_sheet_names_in_file

        for s_name_or_idx in user_wants_sheets:
            actual_s_name = None
            if isinstance(s_name_or_idx, int):
                if 0 <= s_name_or_idx < len(all_sheet_names_in_file):
                    actual_s_name = all_sheet_names_in_file[s_name_or_idx]
                else:
                    print(
                        f"警告: 指定的表单索引 {s_name_or_idx} 超出范围 (共 {len(all_sheet_names_in_file)} 个表单)，将被忽略。")
            elif isinstance(s_name_or_idx, str):
                if s_name_or_idx in all_sheet_names_in_file:
                    actual_s_name = s_name_or_idx
                else:
                    print(f"警告: 指定的表单名称 '{s_name_or_idx}' 在文件 {input_excel_path} 中不存在，将被忽略。")

            if actual_s_name and actual_s_name not in sheets_to_explicitly_process:
                sheets_to_explicitly_process.append(actual_s_name)

        if not user_wants_sheets:
            print(f"信息: 未指定任何表单进行处理。")
        elif not sheets_to_explicitly_process and user_wants_sheets:
            print(f"信息: 指定的表单均无效或不存在。")

    processed_sheets_data = {}
    any_sheet_successfully_read = False

    for current_sheet_name_in_file in tqdm(all_sheet_names_in_file, desc=f"预读并处理Excel中的表单 ({task_identifier})",
                                           unit="表单", leave=False):
        df_sheet_original = None
        try:
            df_sheet_original = pd.read_excel(xls, sheet_name=current_sheet_name_in_file)
            any_sheet_successfully_read = True
        except Exception as sheet_read_err:
            print(
                f"警告: 读取表单 '{current_sheet_name_in_file}' 从 {input_excel_path} 失败: {sheet_read_err}。此表单将被跳过。")
            processed_sheets_data[current_sheet_name_in_file] = None
            continue

        should_process_this_sheet = False
        if sheet_name is not None:
            if current_sheet_name_in_file in sheets_to_explicitly_process:
                should_process_this_sheet = True
        else:
            if source_column_name in df_sheet_original.columns:
                should_process_this_sheet = True

        if should_process_this_sheet:
            if source_column_name in df_sheet_original.columns:
                print(f"\n信息: 正在处理表单 '{current_sheet_name_in_file}' (任务: {task_identifier})...")
                # 假设 _process_dataframe_openai_column 函数已定义
                df_processed_sheet = _process_dataframe_openai_column(
                    df_sheet_original, cache, source_column_name, new_column_name,
                    system_prompt, user_prompt_template, task_identifier,
                    max_row_workers, log_prefix=f"表单'{current_sheet_name_in_file}': "
                )
                processed_sheets_data[current_sheet_name_in_file] = df_processed_sheet
                print(f"信息: 表单 '{current_sheet_name_in_file}' 处理完成。")
            else:
                print(
                    f"信息: 表单 '{current_sheet_name_in_file}' (目标处理) 但缺少源列 '{source_column_name}'。将复制原始表单数据。")
                processed_sheets_data[current_sheet_name_in_file] = df_sheet_original
        else:
            processed_sheets_data[current_sheet_name_in_file] = df_sheet_original

    valid_sheets_to_write = {name: df for name, df in processed_sheets_data.items() if df is not None}

    if not valid_sheets_to_write:
        if not any_sheet_successfully_read:
            print(
                f"严重错误: 无法从输入文件 '{input_excel_path}' 中成功读取任何工作表。文件可能已完全损坏或格式无法识别。")
        else:
            print(f"警告: 虽然尝试读取了工作表，但没有有效的工作表数据可写入到输出文件 '{actual_target_output_path}'。")
        print("因此，不会创建或修改输出文件。请检查输入文件。")
        if cache:
            cache.close()
            print(f"任务 '{task_identifier}' 的磁盘缓存已关闭。")

        if not output_excel_path and task_specific_output_dir and os.path.exists(
                task_specific_output_dir) and not os.listdir(task_specific_output_dir):
            try:
                os.rmdir(task_specific_output_dir)
                print(f"信息: 已移除空的默认输出目录 '{task_specific_output_dir}'。")
            except OSError as e:
                print(f"警告: 尝试移除空的默认输出目录 '{task_specific_output_dir}' 失败: {e}")
        return

    try:
        with pd.ExcelWriter(actual_target_output_path, engine='openpyxl') as writer:
            for sheet_name_to_write, df_to_write in valid_sheets_to_write.items():
                df_to_write.to_excel(writer, sheet_name=sheet_name_to_write, index=False)

        print(f"\n--- Excel文件成功保存到: '{actual_target_output_path}' ---")
        # 可以根据需要添加更详细的计数信息
        processed_count = sum(1 for df in valid_sheets_to_write.values() if
                              new_column_name in df.columns and source_column_name in df.columns)
        copied_count = len(valid_sheets_to_write) - processed_count
        print(f"  总共写入的表单数: {len(valid_sheets_to_write)}")
        print(f"    其中已处理的表单数 (估算): {processed_count}")
        print(f"    其中仅复制的表单数 (估算): {copied_count}")


    except Exception as e:
        print(f"保存Excel文件到 '{actual_target_output_path}' (任务: '{task_identifier}') 时发生严重错误: {e}")
    finally:
        if cache:
            cache.close()
            print(f"任务 '{task_identifier}' 的磁盘缓存已关闭。")


# --- 批量CSV处理函数 ---
def process_all_csvs_in_directory(client: 'AIWrapper',
                                  input_csv_directory: str,
                                  output_csv_directory: str,
                                  source_column_name: str,
                                  new_column_name: str,
                                  system_prompt: str,
                                  user_prompt_template: str,
                                  task_identifier: str,
                                  max_file_workers: int,
                                  max_row_workers: int,
                                  exclude_csvs: Optional[list] = None):
    """
        遍历指定输入目录中的所有CSV文件，进行自定义文本处理并保存结果。
        输出文件将保存在 `output_csv_directory` 下名为 `task_identifier` 的子目录中。

        Args:
            client (AIWrapper): OpenAI API封装对象。
            input_csv_directory (str): 输入CSV文件目录。
            output_csv_directory (str): 输出目录的根路径。实际输出文件会在此路径下
                                         名为`task_identifier`的子目录中。
            source_column_name (str): 需要处理的源列名。
            new_column_name (str): 新增的结果列名。
            system_prompt (str): 系统提示词。
            user_prompt_template (str): 用户提示词模板，使用{text}占位符。
            task_identifier (str): 任务标识符 (用于缓存和输出子目录名)。
            max_file_workers (int): 文件级并发线程数。
            max_row_workers (int): 行级并发线程数 (传递给每个文件处理过程)。
            exclude_csvs (Optional[list]): 要排除的CSV文件名列表（仅文件名，不含路径）。

        Returns:
            None
        """

    global client_global
    client_global = client

    cache = _prepare_cache(task_identifier)
    if cache is None:
        print(f"错误: 任务 '{task_identifier}' 的缓存初始化失败，处理中止。")
        return

    task_run_output_base_dir = os.path.join(output_csv_directory, task_identifier)
    if os.path.isdir(task_run_output_base_dir):
        print(f"警告: 任务 '{task_identifier}' 的主输出目录 '{task_run_output_base_dir}' 已存在。正在清空它。")
        try:
            rmtree(task_run_output_base_dir)
        except OSError as e:
            print(f"错误: 无法移除已存在的主输出目录 {task_run_output_base_dir}: {e}")
            cache.close()
            return
    try:
        os.makedirs(task_run_output_base_dir, exist_ok=False)
    except OSError as e:
        print(f"错误: 无法创建主输出目录 {task_run_output_base_dir}: {e}")
        cache.close()
        return

    print(f"\n在目录中查找CSV文件: {os.path.abspath(input_csv_directory)}")
    print(f"任务 '{task_identifier}' 处理后的文件将保存到: {os.path.abspath(task_run_output_base_dir)}")
    print(
        f"最多使用 {max_file_workers} 个线程处理文件，每个文件内最多使用 {max_row_workers} 个线程处理行。任务: '{task_identifier}'")
    print(f"源列名: '{source_column_name}', 新列名: '{new_column_name}'")
    print("-" * 30)

    csv_files = glob.glob(os.path.join(input_csv_directory, "*.csv"))
    if exclude_csvs:
        exclude_set = set(exclude_csvs)
        csv_files = [f for f in csv_files if os.path.basename(f) not in exclude_set]

    if not csv_files:
        print(f"信息: 在 '{input_csv_directory}' 中未找到CSV文件。")
        cache.close()
        return
    else:
        print(f"为任务 '{task_identifier}' 找到 {len(csv_files)} 个CSV文件:")
        for i, f_path in enumerate(csv_files):
            print(f"  {i + 1}. {os.path.basename(f_path)}")
        print("-" * 30)

    results = []
    with ThreadPoolExecutor(max_workers=max_file_workers) as executor:
        future_to_file_map = {}
        for filepath in csv_files:
            input_filename_base, input_filename_ext = os.path.splitext(os.path.basename(filepath))
            current_file_target_output_path = os.path.join(
                task_run_output_base_dir,
                f"{input_filename_base}_{task_identifier}_processed{input_filename_ext}"
            )
            future = executor.submit(_process_csv_file,
                                     filepath,
                                     current_file_target_output_path,
                                     cache,
                                     source_column_name, new_column_name,
                                     system_prompt, user_prompt_template, task_identifier,
                                     max_row_workers)
            future_to_file_map[future] = filepath

        for future in tqdm(as_completed(future_to_file_map), total=len(csv_files),
                           desc=f"整体进度 ({task_identifier})", unit="文件", ncols=100):
            file_path = future_to_file_map[future]
            try:
                result_message = future.result()
                results.append(result_message)
            except Exception as exc:
                results.append(
                    f"文件 {os.path.basename(file_path)} (任务: {task_identifier}) 在主线程中发生严重错误: {exc}")

    print(f"\n--- 任务处理摘要: '{task_identifier}' ---")
    success_count, error_count, skipped_count = 0, 0, 0
    for msg in results:
        print(msg)
        if msg and "成功:" in msg:
            success_count += 1
        elif msg and "已跳过" in msg:
            skipped_count += 1
        else:
            error_count += 1
    print("---")
    print(f"任务 '{task_identifier}' 的总文件数: {len(csv_files)}")
    print(f"  成功处理: {success_count}")
    print(f"  失败或错误: {error_count}")
    print(f"  已跳过: {skipped_count}")
    print("--- 此任务的所有文件均已尝试处理。 ---")

    cache.close()
    print(f"任务 '{task_identifier}' 的磁盘缓存已关闭。")
