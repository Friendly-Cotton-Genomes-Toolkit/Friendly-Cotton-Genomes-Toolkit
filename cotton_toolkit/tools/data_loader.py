# cotton_toolkit/tools/data_loader.py

import pandas as pd
import os
from typing import Optional
import logging

try:
    import builtins
    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

# 修改: 创建 logger 实例
logger = logging.getLogger("cotton_toolkit.tools.data_loader")


def load_annotation_data(
        file_path: str
) -> Optional[pd.DataFrame]:
    """
    【简化版】加载一个标准化的注释CSV文件。
    此函数假定输入的CSV文件第一行是表头。
    """
    if not os.path.exists(file_path):
        # 修改: 使用 logger.error
        logger.error(_("Annotation file not found at: {}").format(file_path))
        return None

    try:
        df = pd.read_csv(file_path, header=0, sep=',')

        if df.empty:
            # 修改: 使用 logger.warning
            logger.warning(_("Annotation file '{}' is empty.").format(os.path.basename(file_path)))
            return None

        df.dropna(subset=['GeneID', 'TermID'], inplace=True)
        df['GeneID'] = df['GeneID'].astype(str)
        df['TermID'] = df['TermID'].astype(str)

        if 'Description' not in df.columns:
            df['Description'] = df['TermID']
        if 'Namespace' not in df.columns:
            df['Namespace'] = 'KEGG' if 'ko' in df['TermID'].iloc[0] else 'unknown'

        return df

    except Exception as e:
        # 修改: 使用 logger.error
        logger.error(_("Failed to load and process standardized file {}. Reason: {}").format(file_path, e))
        return None