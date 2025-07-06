# cotton_toolkit/core/downloader.py

import concurrent.futures  # 用于多线程
import gzip  # 用于解压.gz文件
import logging  # 用于日志记录
import os
import re
import shutil  # 用于文件操作 (如 copyfileobj)
import threading
import time
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

logger = logging.getLogger("cotton_toolkit.downloader")


def decompress_gz_to_temp_file(gz_filepath: str, temp_output_filepath: str, log: Callable) -> bool:
    """解压 .gz 文件到指定的临时文件路径。"""
    try:
        with gzip.open(gz_filepath, 'rb') as f_in, open(temp_output_filepath, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
        log(_("DEBUG: Successfully decompressed '{}' to temporary file.").format(os.path.basename(gz_filepath)))
        return True
    except Exception as e:
        log(_("ERROR: Failed to decompress file '{}': {}").format(gz_filepath, e))
        return False


def download_file(
        url: str,
        target_path: str,
        force_download: bool = False,
        task_desc: str = "",
        proxies: Optional[Dict[str, str]] = None
) -> bool:
    """下载单个文件到指定路径，支持代理。"""
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

        # 使用分离的连接和读取超时以提高取消操作的响应性
        response = requests.get(url, stream=True, timeout=(10, 60), proxies=proxies)
        response.raise_for_status()

        total_size_in_bytes = int(response.headers.get('content-length', 0))
        block_size = 1024 * 8

        with open(target_path, 'wb') as file, \
                tqdm(total=total_size_in_bytes, unit='iB', unit_scale=True, desc=effective_desc, leave=False,
                     ascii=" #") as progress_bar:
            for data in response.iter_content(block_size):
                progress_bar.update(len(data))
                file.write(data)

        if total_size_in_bytes != 0 and progress_bar.n < total_size_in_bytes:
            progress_bar.update(total_size_in_bytes - progress_bar.n)
        progress_bar.close()

        if total_size_in_bytes != 0 and os.path.getsize(target_path) != total_size_in_bytes:
            logger.error(_("错误: 下载的文件 {} 大小 ({}) 与预期 ({}) 不符。可能下载不完整。").format(
                os.path.basename(target_path), os.path.getsize(target_path), total_size_in_bytes
            ))
            return False

        return True
    except requests.exceptions.RequestException as e:
        logger.error(_("网络请求错误导致下载失败: {}. URL: {}").format(e, url))
    except Exception as e:
        logger.exception(_("下载 {} 时发生未知错误:").format(url))

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
        cancel_event: Optional[threading.Event] = None,
) -> bool:
    """为单个文件执行下载和后续处理的包装函数。"""
    log = status_callback

    if cancel_event and cancel_event.is_set():
        log(_("INFO: Task cancelled before downloading {}.").format(f"{version_id}_{file_key}"))
        return False

    base_dir = downloader_config.download_output_base_dir
    version_identifier = getattr(genome_info, 'version_id', None)
    if not version_identifier:
        log(_(
            "WARNING: GenomeSourceItem for '{}' is missing 'version_id'. Falling back to species name for directory.").format(
            genome_info.species_name), "WARNING")
        version_identifier = re.sub(r'[\\/*?:"<>|]', "_", genome_info.species_name).replace(" ", "_")
    version_output_dir = os.path.join(base_dir, version_identifier)

    try:
        os.makedirs(version_output_dir, exist_ok=True)
    except OSError as e:
        log(_("ERROR: Failed to create directory {}. Reason: {}").format(version_output_dir, e))
        return False

    filename = os.path.basename(urlparse(url).path)
    local_path = os.path.join(version_output_dir, filename)

    if not force and os.path.exists(local_path):
        log(_("INFO: 文件已存在，跳过下载: {}").format(os.path.basename(local_path)))
        is_download_successful = True
    else:
        description = f"{version_id}_{file_key}"
        log(_("INFO: 开始下载: {}...").format(description))
        is_download_successful = _download_file_with_progress(url, local_path, description, proxies, log, cancel_event)

    if cancel_event and cancel_event.is_set():
        return False

    if is_download_successful and file_key == 'homology_ath' and local_path.lower().endswith(".xlsx.gz"):
        gz_excel_path = local_path
        base_name, _V = os.path.splitext(os.path.basename(gz_excel_path))
        csv_filename = os.path.splitext(base_name)[0] + ".csv"
        final_csv_path = os.path.join(os.path.dirname(gz_excel_path), csv_filename)

        if not force and os.path.exists(final_csv_path):
            log(_("INFO: 对应的CSV文件已存在，跳过转换: {}").format(csv_filename))
        else:
            if cancel_event and cancel_event.is_set(): return False
            log(_("INFO: 尝试将 {} 转换为 CSV...").format(os.path.basename(gz_excel_path)))
            temp_xlsx_path = os.path.splitext(gz_excel_path)[0]
            if decompress_gz_to_temp_file(gz_excel_path, temp_xlsx_path, log):
                try:
                    convert_excel_to_standard_csv(temp_xlsx_path, final_csv_path)
                except Exception as e:
                    log(_("ERROR: 转换Excel到CSV时发生错误: {}").format(e))
                finally:
                    if os.path.exists(temp_xlsx_path):
                        for i in range(3):
                            try:
                                os.remove(temp_xlsx_path)
                                break
                            except PermissionError:
                                time.sleep(0.5)
                            except Exception as e:
                                log(_("ERROR: 删除临时文件 {} 失败: {}").format(temp_xlsx_path, e))
                                break
    return is_download_successful


def _download_file_with_progress(
        url: str,
        local_path: str,
        description: str,
        proxies: Optional[Dict[str, str]],
        status_callback: Optional[Callable] = None,
        cancel_event: Optional[threading.Event] = None
) -> bool:
    """一个带有tqdm进度条和取消功能的文件下载辅助函数。"""
    log = status_callback if status_callback else print
    try:
        # =========== 代码修正部分 ===========
        # 使用分离的连接(10s)和读取(60s)超时来提高取消操作的响应性
        with requests.get(url, stream=True, proxies=proxies, timeout=(10, 60)) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))

            with tqdm(total=total_size, unit='iB', unit_scale=True, desc=description, ncols=100, leave=False,
                      ascii=" #") as pbar:
                with open(local_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if cancel_event and cancel_event.is_set():
                            log(_("INFO: Download for {} was cancelled by user.").format(description))
                            return False

                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

            if total_size != 0 and os.path.getsize(local_path) < total_size:
                log(_("WARNING: Downloaded size for {} is less than expected. The file might be incomplete.").format(
                    description))
                return False
            return True

    except requests.exceptions.RequestException as e:
        if cancel_event and cancel_event.is_set():
            log(_("INFO: Download for {} was cancelled during request setup.").format(description))
        else:
            log(_("ERROR: Failed to download {} from {}. Network error: {}").format(description, url, e))
        if os.path.exists(local_path): os.remove(local_path)
        return False
    except Exception as e:
        log(_("ERROR: An unexpected error occurred while downloading {}: {}").format(description, e))
        if os.path.exists(local_path): os.remove(local_path)
        return False