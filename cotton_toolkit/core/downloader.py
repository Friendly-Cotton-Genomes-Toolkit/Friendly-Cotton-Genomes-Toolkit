import os
import re
import shutil
import threading
import logging
from typing import Dict, Optional
from urllib.parse import urlparse

import requests
from tqdm import tqdm

from ..config.models import DownloaderConfig, GenomeSourceItem

# --- 国际化和日志设置 ---
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.downloader")


def download_genome_data(
        downloader_config: DownloaderConfig,
        version_id: str,
        genome_info: GenomeSourceItem,
        file_key: str,
        url: str,
        force: bool,
        proxies: Optional[Dict[str, str]],
        cancel_event: Optional[threading.Event] = None,
) -> bool:
    """
    【最终重构版】
    为单个文件执行纯粹的下载任务。
    此函数不再执行任何文件解压或格式转换操作。
    """
    if cancel_event and cancel_event.is_set():
        logger.info(_("任务在下载 {} 之前被取消。").format(f"{version_id}_{file_key}"))
        return False

    # 1. 确定输出目录和文件路径 (逻辑不变)
    base_dir = downloader_config.download_output_base_dir
    version_identifier = getattr(genome_info, 'version_id', version_id)
    version_output_dir = os.path.join(base_dir, version_identifier)

    try:
        os.makedirs(version_output_dir, exist_ok=True)
    except OSError as e:
        logger.error(_("错误: 创建目录 {} 失败。原因: {}").format(version_output_dir, e))
        return False

    filename = os.path.basename(urlparse(url).path)
    local_path = os.path.join(version_output_dir, filename)

    # 2. 检查文件是否存在或是否需要强制下载
    if not force and os.path.exists(local_path):
        logger.info(_("文件已存在，跳过下载: {}").format(os.path.basename(local_path)))
        return True

    # 3. 执行下载
    description = f"{version_id}_{file_key}"
    logger.info(_("开始下载: {}...").format(description))
    is_download_successful = _download_file_with_progress(
        url=url,
        local_path=local_path,
        description=description,
        proxies=proxies,
        cancel_event=cancel_event
    )

    if cancel_event and cancel_event.is_set():
        return False

    # 【核心修改】
    # 移除了所有在下载后立即将 .xlsx.gz 转换为 .csv 的逻辑。
    # 下载器的任务在文件成功下载到本地后即告完成。
    # 所有后续的转换和处理都应由 preprocessor.py 中的流程负责。

    return is_download_successful


def _download_file_with_progress(
        url: str,
        local_path: str,
        description: str,
        proxies: Optional[Dict[str, str]],
        cancel_event: Optional[threading.Event] = None
) -> bool:
    """
    一个带有tqdm进度条和取消功能的文件下载辅助函数 (此函数保持不变)。
    """
    target_dir = os.path.dirname(local_path)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)

    try:
        with requests.get(url, stream=True, proxies=proxies, timeout=(10, 60)) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))

            with tqdm(total=total_size, unit='iB', unit_scale=True, desc=description, ncols=100, leave=False,
                      ascii=" #") as pbar:
                with open(local_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if cancel_event and cancel_event.is_set():
                            logger.info(_("下载 {} 的任务被用户取消。").format(description))
                            # 清理未完成的文件
                            if os.path.exists(local_path):
                                os.remove(local_path)
                            return False

                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

            if total_size != 0 and os.path.getsize(local_path) < total_size:
                logger.warning(_("下载的文件 {} 大小小于预期，可能不完整。").format(description))
                return False

            logger.info(_("文件 {} 下载成功。").format(description))
            return True

    except requests.exceptions.RequestException as e:
        if not (cancel_event and cancel_event.is_set()):
            logger.error(_("下载 {} (来自 {}) 失败。网络错误: {}").format(description, url, e))
        if os.path.exists(local_path): os.remove(local_path)
        return False
    except Exception as e:
        logger.error(_("下载 {} 时发生未知错误: {}").format(description, e))
        if os.path.exists(local_path): os.remove(local_path)
        return False