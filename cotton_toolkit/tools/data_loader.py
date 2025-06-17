# cotton_toolkit/tools/data_loader.py

import pandas as pd
import os
from typing import Callable, Optional


def load_annotation_data(
        file_path: str,
        status_callback: Optional[Callable] = print
) -> Optional[pd.DataFrame]:
    """
    【简化版】加载一个标准化的注释CSV文件。
    此函数假定输入的CSV文件第一行是表头。
    """
    if not os.path.exists(file_path):
        status_callback(f"ERROR: Annotation file not found at: {file_path}")
        return None

    try:
        # 直接使用pandas的read_csv读取，header=0表示第一行是表头
        df = pd.read_csv(file_path, header=0, sep=',')

        if df.empty:
            status_callback(f"WARNING: Annotation file '{os.path.basename(file_path)}' is empty.")
            return None

        # 基本的数据清洗
        df.dropna(subset=['GeneID', 'TermID'], inplace=True)
        df['GeneID'] = df['GeneID'].astype(str)
        df['TermID'] = df['TermID'].astype(str)

        # 确保Description和Namespace列存在，以防万一
        if 'Description' not in df.columns:
            df['Description'] = df['TermID']
        if 'Namespace' not in df.columns:
            # 对于非GO文件，提供一个默认值
            df['Namespace'] = 'KEGG' if 'ko' in df['TermID'].iloc[0] else 'unknown'

        return df

    except Exception as e:
        status_callback(f"ERROR: Failed to load and process standardized file {file_path}. Reason: {e}")
        return None