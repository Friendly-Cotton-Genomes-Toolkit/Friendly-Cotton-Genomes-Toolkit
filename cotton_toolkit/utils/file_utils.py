# cotton_toolkit/utils/file_utils.py
import io
import os
import re

import pandas as pd
import gzip
import logging
from typing import Optional

from cotton_toolkit.core.file_normalizer import normalize_to_csv

try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


logger = logging.getLogger(__name__)


def prepare_input_file(
        original_path: str,
        temp_dir: str
) -> Optional[str]:
    """
    【通用版】预处理一个输入文件，确保其为标准的CSV格式，并使用缓存。
    支持 .csv, .txt, .xlsx 及其 .gz 压缩版本。
    """
    if not os.path.exists(original_path):
        # 修改: 使用 logger.error
        logger.error(_("输入文件不存在: {}").format(original_path))
        return None

    os.makedirs(temp_dir, exist_ok=True)

    base_name = os.path.basename(original_path)
    cache_base_name = base_name.split('.')[0]
    cached_csv_path = os.path.join(temp_dir, f"{cache_base_name}_standardized.csv")

    if os.path.exists(cached_csv_path):
        try:
            original_mtime = os.path.getmtime(original_path)
            cached_mtime = os.path.getmtime(cached_csv_path)
            if cached_mtime >= original_mtime:
                # 修改: 使用 logger.info
                logger.info(_("发现有效的缓存文件，将直接使用: {}").format(os.path.basename(cached_csv_path)))
                return cached_csv_path

        except OSError as e:
            # 修改: 使用 logger.warning
            logger.warning(_("无法检查文件时间戳: {}").format(e))

    # 修改: 使用 logger.info
    logger.info(_("正在处理新文件或已更新的文件: {}").format(base_name))

    try:
        # 修改: normalize_to_csv 不再接受回调函数
        result_path = normalize_to_csv(original_path, cached_csv_path)
        if result_path:
            # 修改: 使用 logger.info
            logger.info(_("文件已成功转换为标准CSV并缓存: {}").format(os.path.basename(cached_csv_path)))
            return result_path

        else:
            # 修改: 使用 logger.error
            logger.error(_("文件规范化失败: {}").format(base_name))
            return None
    except Exception as e:
        # 修改: 使用 logger.error
        logger.error(_("处理文件 {} 时发生严重错误: {}").format(base_name, e))
        return None


def smart_load_file(file_path: str) -> Optional[pd.DataFrame]:
    """
    智能加载数据文件，能自动处理 .gz 压缩和多种表格格式 (Excel, CSV, TSV)。
    """
    if not file_path or not os.path.exists(file_path):
        # 修改: 使用 logger.error
        logger.error(_("错误: 文件不存在 -> {}").format(file_path))
        return None

    file_name_for_log = os.path.basename(file_path)

    try:
        is_gzipped = file_path.lower().endswith('.gz')
        open_func = gzip.open if is_gzipped else open
        uncompressed_path = file_path.lower().replace('.gz', '') if is_gzipped else file_path.lower()
        file_ext = os.path.splitext(uncompressed_path)[1]

        # 修改: 使用 logger.debug
        logger.debug(_("正在读取文件: {} (类型: {}, 压缩: {})").format(file_name_for_log, file_ext, is_gzipped))

        with open_func(file_path, 'rb') as f:
            content_bytes = f.read()

        df = None
        if file_ext in ['.xlsx', '.xls']:
            df = pd.read_excel(io.BytesIO(content_bytes), engine='openpyxl')

        elif file_ext in ['.csv', '.tsv', '.txt']:
            try:
                content_str = content_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # 修改: 使用 logger.warning
                logger.warning(_("文件 {} 使用UTF-8解码失败，尝试latin-1编码。").format(file_name_for_log))
                content_str = content_bytes.decode('latin-1', errors='ignore')

            first_line = content_str.splitlines()[0] if content_str else ""
            if '\t' in first_line:
                separator = '\t'
                # 修改: 使用 logger.debug
                logger.debug(_("检测到制表符(Tab)分隔符: {}").format(file_name_for_log))
            else:
                separator = ','
                # 修改: 使用 logger.debug
                logger.debug(_("默认使用逗号(Comma)分隔符: {}").format(file_name_for_log))

            df = pd.read_csv(io.StringIO(content_str), sep=separator, engine='python')

        else:
            # 修改: 使用 logger.warning
            logger.warning(_("警告: 不支持的文件扩展名 '{}' 来自文件: {}").format(file_ext, file_name_for_log))
            return None

        # 修改: 使用 logger.info
        logger.info(_("文件 {} 加载成功，共 {} 行。").format(file_name_for_log, len(df)))
        return df

    except Exception as e:
        # 修改: 使用 logger.error
        logger.error(_("加载或解析文件 {} 时发生严重错误: {}").format(file_name_for_log, e))
        return None


def save_dataframe_as(df: pd.DataFrame, output_path: str) -> bool:
    """
    根据输出路径的扩展名，将DataFrame保存为CSV或Excel文件。
    """
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    file_ext = os.path.splitext(output_path)[1].lower()

    try:
        if file_ext == '.csv':
            df.to_csv(output_path, index=False, encoding='utf-8-sig')
            # 修改: 使用 logger.info
            logger.info(_("DataFrame 已成功保存为CSV文件: {}").format(output_path))
        elif file_ext == '.xlsx':
            df.to_excel(output_path, index=False, engine='openpyxl')
            # 修改: 使用 logger.info
            logger.info(_("DataFrame 已成功保存为Excel文件: {}").format(output_path))
        else:
            # 修改: 使用 logger.error
            logger.error(_("错误: 不支持的文件格式 '{}'。请使用 '.csv' 或 '.xlsx'。").format(file_ext))
            return False

        return True
    except Exception as e:
        # 修改: 使用 logger.error
        logger.error(_("保存DataFrame到 {} 时发生错误: {}").format(output_path, e))
        return False


def _sanitize_table_name(filename: str, version_id: Optional[str] = None) -> str:
    """
    清理文件名，创建一个有效的SQL表名，并可选择性地添加版本ID前缀。
    """
    base_name = filename.replace('.gz', '').replace('.xlsx', '').replace('.txt', '').replace('.csv', '').replace('.xls',
                                                                                                                 '')
    sane_name = re.sub(r'[^a-zA-Z0-9_]', '_', base_name)
    if sane_name and sane_name[0].isdigit():
        sane_name = '_' + sane_name

    if version_id:
        sane_version = re.sub(r'[^a-zA-Z0-9_]', '_', version_id)
        return f"{sane_version}_{sane_name}"

    return sane_name
