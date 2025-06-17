# cotton_toolkit/core/downloader.py

import concurrent.futures  # 用于多线程
import gzip  # 用于解压.gz文件
import logging  # 用于日志记录
import os
import re
import shutil  # 用于文件操作 (如 copyfileobj)
import time  # <---【修改点1】新增导入，用于重试等待
from typing import List, Dict, Optional, Callable, Any
from urllib.parse import urlparse  # 用于从URL解析文件名

import requests  # 用于HTTP请求
from tqdm import tqdm  # 用于显示进度条

from cotton_toolkit.config.models import DownloaderConfig, GenomeSourceItem
from cotton_toolkit.core.convertXlsx2csv import convert_excel_to_standard_csv

# --- 国际化和日志设置 ---
try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


# 获取logger实例。主应用入口会配置根logger或包logger。
# 这里我们获取一个特定于本模块的logger。
logger = logging.getLogger("cotton_toolkit.downloader")


def decompress_gz_to_temp_file(gz_filepath: str, temp_output_filepath: str, log: Callable) -> bool:
    """解压 .gz 文件到指定的临时文件路径。"""
    try:
        with gzip.open(gz_filepath, 'rb') as f_in, open(temp_output_filepath, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
        log(f"DEBUG: Successfully decompressed '{os.path.basename(gz_filepath)}' to temporary file.")
        return True
    except Exception as e:
        log(f"ERROR: Failed to decompress file '{gz_filepath}': {e}")
        return False


def download_file(
        url: str,
        target_path: str,
        force_download: bool = False,
        task_desc: str = "",  # 用于tqdm的描述
        proxies: Optional[Dict[str, str]] = None
) -> bool:
    """
    下载单个文件到指定路径，支持代理。

    Args:
        url (str): 文件的下载链接。
        target_path (str): 本地保存路径（包含文件名）。
        force_download (bool): 如果为True，即使文件已存在也重新下载。
        task_desc (str): 用于进度条的额外描述。
        proxies (Optional[Dict[str, str]]): 代理配置。

    Returns:
        bool: 下载成功返回True，否则返回False。
    """
    if not force_download and os.path.exists(target_path):
        logger.info(_("文件已存在: {} (跳过下载)").format(target_path))
        return True

    target_dir = os.path.dirname(target_path)
    if target_dir and not os.path.exists(target_dir):
        try:
            os.makedirs(target_dir)
            logger.info(_("已创建目录: {}").format(target_dir))
        except OSError as e:
            logger.error(_("创建目录 {} 失败: {}").format(target_dir, e))
            return False

    try:
        effective_desc = task_desc if task_desc else os.path.basename(target_path)
        logger.info(
            _("开始下载: {} -> {} (代理: {})").format(url, target_path, proxies if proxies else _("系统默认/无")))

        response = requests.get(url, stream=True, timeout=60, proxies=proxies)
        response.raise_for_status()  # 如果状态码是 4xx 或 5xx，则抛出HTTPError

        total_size_in_bytes = int(response.headers.get('content-length', 0))
        block_size = 1024 * 8  # 8KB 块大小

        with open(target_path, 'wb') as file, \
                tqdm(total=total_size_in_bytes, unit='iB', unit_scale=True, desc=effective_desc, leave=False,
                     ascii=" #") as progress_bar:
            for data in response.iter_content(block_size):
                progress_bar.update(len(data))
                file.write(data)

        # 确保进度条在循环结束后达到100% (如果total_size已知且准确)
        if total_size_in_bytes != 0 and progress_bar.n < total_size_in_bytes:
            progress_bar.update(total_size_in_bytes - progress_bar.n)  # 补齐进度
        progress_bar.close()

        if total_size_in_bytes != 0 and os.path.getsize(target_path) != total_size_in_bytes:
            logger.error(_("错误: 下载的文件 {} 大小 ({}) 与预期 ({}) 不符。可能下载不完整。").format(
                os.path.basename(target_path), os.path.getsize(target_path), total_size_in_bytes
            ))
            # if os.path.exists(target_path): os.remove(target_path) # 可选择删除不完整文件
            return False  # 标记为失败

        # logger.info(_("下载成功: {}").format(target_path)) # 成功信息由调用者统一打印
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(_("HTTP错误导致下载失败: {}. URL: {}. 响应: {}").format(e, url, e.response.text[
                                                                                     :200] if e.response else "N/A"))
    except requests.exceptions.RequestException as e:
        logger.error(_("网络请求错误导致下载失败: {}. URL: {}").format(e, url))
    except Exception as e:
        logger.exception(_("下载 {} 时发生未知错误:").format(url))  # logger.exception 会记录堆栈跟踪

    # 如果发生任何异常，且文件已部分创建，则删除
    if os.path.exists(target_path):
        try:
            os.remove(target_path)
            logger.info(_("已删除不完整的下载文件: {}").format(target_path))
        except OSError as e_del:
            logger.warning(_("删除不完整文件 {} 失败: {}").format(target_path, e_del))
    return False


def download_genome_data(
    downloader_config: DownloaderConfig,
    version_id: str,
    genome_info: GenomeSourceItem,
    file_key: str,
    url: str,
    force: bool,
    proxies: Optional[Dict[str, str]],
    status_callback: Callable,
) -> bool:
    """
    【全新版本】下载单个指定的基因组数据文件，并处理后续操作。
    此函数现在由 run_download_pipeline 在多线程中为每个文件调用一次。
    """
    log = status_callback

    # 1. 构建输出目录和文件路径
    base_dir = downloader_config.download_output_base_dir
    safe_species_name = re.sub(r'[\\/*?:"<>|]', "_", genome_info.species_name).replace(" ", "_")
    version_output_dir = os.path.join(base_dir, safe_species_name)

    # 【修正 WinError 183】使用 exist_ok=True, 多线程同时调用也不会报错
    try:
        os.makedirs(version_output_dir, exist_ok=True)
    except OSError as e:
        log(f"ERROR: Failed to create directory {version_output_dir}. Reason: {e}")
        return False

    filename = os.path.basename(urlparse(url).path)
    local_path = os.path.join(version_output_dir, filename)

    # 2. 检查文件是否存在以及是否需要强制下载
    if not force and os.path.exists(local_path):
        log(f"INFO: 文件已存在，跳过下载: {os.path.basename(local_path)}")
        # 即使跳过下载，也检查是否需要进行后续转换
        is_download_successful = True
    else:
        # 3. 开始下载
        description = f"{version_id}_{file_key}"
        log(f"INFO: 开始下载: {description}...")
        is_download_successful = _download_file_with_progress(url, local_path, description, proxies, log)

    # 4. 如果下载成功，执行后续操作（如解压和转换）
    if is_download_successful and file_key == 'homology_ath' and local_path.lower().endswith(".xlsx.gz"):
        gz_excel_path = local_path
        base_name, _ = os.path.splitext(os.path.basename(gz_excel_path))  # xxx.xlsx
        csv_filename = os.path.splitext(base_name)[0] + ".csv"  # xxx.csv
        final_csv_path = os.path.join(os.path.dirname(gz_excel_path), csv_filename)

        if not force and os.path.exists(final_csv_path):
            log(f"INFO: 对应的CSV文件已存在，跳过转换: {csv_filename}")
        else:
            log(f"INFO: 尝试将 {os.path.basename(gz_excel_path)} 转换为 CSV...")
            temp_xlsx_path = os.path.splitext(gz_excel_path)[0]
            if decompress_gz_to_temp_file(gz_excel_path, temp_xlsx_path, log):
                try:
                    convert_excel_to_standard_csv(temp_xlsx_path, final_csv_path)
                except Exception as e:
                    log(f"ERROR: 转换Excel到CSV时发生错误: {e}")
                finally:
                    # 线程安全的文件删除
                    if os.path.exists(temp_xlsx_path):
                        for i in range(3):
                            try:
                                os.remove(temp_xlsx_path)
                                break
                            except PermissionError:
                                time.sleep(0.5)
                            except Exception as e:
                                log(f"ERROR: 删除临时文件 {temp_xlsx_path} 失败: {e}")
                                break

    return is_download_successful


def _download_file_with_progress(
        url: str,
        local_path: str,
        description: str,
        proxies: Optional[Dict[str, str]],
        status_callback: Optional[Callable] = None
) -> bool:
    """一个带有tqdm进度条的文件下载辅助函数。"""
    log = status_callback if status_callback else print
    try:
        with requests.get(url, stream=True, proxies=proxies, timeout=60) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))

            with tqdm(
                    total=total_size, unit='iB', unit_scale=True, desc=description,
                    ncols=100, leave=False, ascii=" #",
            ) as pbar:
                with open(local_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

            if total_size != 0 and os.path.getsize(local_path) < total_size:
                log(f"WARNING: Downloaded size for {description} is less than expected. The file might be incomplete.")
                return False
            return True
    except requests.exceptions.RequestException as e:
        log(f"ERROR: Failed to download {description} from {url}. Network error: {e}")
        if os.path.exists(local_path): os.remove(local_path)
        return False
    except Exception as e:
        log(f"ERROR: An unexpected error occurred while downloading {description}: {e}")
        if os.path.exists(local_path): os.remove(local_path)
        return False