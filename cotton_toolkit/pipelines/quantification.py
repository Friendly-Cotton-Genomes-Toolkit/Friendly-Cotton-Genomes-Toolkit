# quantification.py (已优化和重构)

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Any, Callable

import pandas as pd

from cotton_toolkit.pipelines.decorators import pipeline_task
from cotton_toolkit.utils.file_utils import smart_load_file

try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

logger = logging.getLogger("cotton_toolkit.pipeline.quantification")


def _calculate_fpkm_worker(sample_series: pd.Series, gene_length_kb: pd.Series) -> pd.Series:
    """计算单个样本(列)的FPKM值"""
    total_reads_per_million = sample_series.sum() / 1_000_000
    if total_reads_per_million == 0:
        return pd.Series(0.0, index=sample_series.index, name=f"{sample_series.name}_FPKM_RPKM")
    fpkm_series = sample_series.div(gene_length_kb).div(total_reads_per_million)
    fpkm_series.name = f"{sample_series.name}_FPKM_RPKM"
    return fpkm_series


def _calculate_tpm_worker(sample_series: pd.Series, gene_length_kb: pd.Series) -> pd.Series:
    """计算单个样本(列)的TPM值"""
    rpk_series = sample_series.div(gene_length_kb)
    rpk_sum = rpk_series.sum()
    if rpk_sum == 0:
        return pd.Series(0.0, index=sample_series.index, name=f"{sample_series.name}_TPM")
    tpm_series = (rpk_series / rpk_sum) * 1_000_000
    tpm_series.name = f"{sample_series.name}_TPM"
    return tpm_series


@pipeline_task(_("表达量标准化"))
def run_expression_normalization(
        counts_file_path: str,
        gene_lengths_file_path: str,
        output_path: str,
        normalization_method: str = 'tpm',
        max_workers: int = 4,
        config: Optional[Any] = None,
        cancel_event: Optional[threading.Event] = None,
        **kwargs
) -> Optional[str]:
    """
    将原始基因计数(raw counts)转换为指定的标准化值（TPM, FPKM, 或 RPKM）。
    """
    progress = kwargs.get('progress_callback', lambda p, m: None)
    check_cancel = kwargs.get('check_cancel', lambda: False)

    progress(0, _("开始表达量标准化..."))
    if check_cancel(): return None

    # --- 1. 数据加载 ---
    try:
        progress(5, _("正在智能加载原始计数文件..."))
        counts_df = smart_load_file(counts_file_path)
        if counts_df is None or counts_df.empty:
            raise IOError(_("无法加载或不支持的计数文件格式: {}").format(os.path.basename(counts_file_path)))

        # 检查计数文件是否缺少表头
        if counts_df.columns[0] != 'gene_id':
            raise ValueError(
                _("计数文件 '{}' 格式错误: 第一列表头必须是 'gene_id'，但检测到的是 '{}'。")
                .format(os.path.basename(counts_file_path), counts_df.columns[0])
            )

        counts_df.set_index(counts_df.columns[0], inplace=True)

        progress(10, _("正在智能加载基因长度文件..."))
        lengths_df = smart_load_file(gene_lengths_file_path)
        if lengths_df is None or lengths_df.empty:
            raise IOError(_("无法加载或不支持的基因长度文件格式: {}").format(os.path.basename(gene_lengths_file_path)))


        if len(lengths_df.columns) < 2:
            raise ValueError(_("基因长度文件必须至少有两列（基因ID 和 长度）。"))

        # --- 校验基因长度文件表头 ---
        actual_headers = lengths_df.columns
        if actual_headers[0] != 'gene_id':
            raise ValueError(
                _("基因长度文件 '{}' 格式错误: 第一列表头必须是 'gene_id'，但检测到的是 '{}'。")
                .format(os.path.basename(gene_lengths_file_path), actual_headers[0])
            )
        if actual_headers[1] != 'length':
            raise ValueError(
                _("基因长度文件 '{}' 格式错误: 第二列表头必须是 'length'，但检测到的是 '{}'。")
                .format(os.path.basename(gene_lengths_file_path), actual_headers[1])
            )

        lengths_df = lengths_df.iloc[:, [0, 1]]
        lengths_df.columns = ['gene_id', 'length']
        lengths_df.set_index('gene_id', inplace=True)

    except (FileNotFoundError, IOError, ValueError) as e:
        logger.error(_("文件加载或格式检查失败: {}").format(e))
        raise e

    if check_cancel(): return None

    # --- 2. 数据对齐与预处理 ---
    progress(20, _("正在对齐计数与长度数据..."))
    common_genes = counts_df.index.intersection(lengths_df.index)

    if common_genes.empty:
        raise ValueError(_("基因ID无法匹配，请检查计数文件和长度文件的基因ID格式是否一致。"))

    logger.info(_("成功匹配 {} 个基因的计数和长度信息。").format(len(common_genes)))

    counts = counts_df.loc[common_genes]
    lengths = lengths_df.loc[common_genes, 'length']
    gene_length_kb = lengths / 1000

    # --- 3. 并行计算 ---
    method = normalization_method.lower()
    progress(30, _("正在为 '{}' 方法准备并行计算任务...").format(method.upper()))

    target_worker = None
    if method == 'tpm':
        target_worker = _calculate_tpm_worker
    elif method in ['fpkm', 'rpkm']:
        target_worker = _calculate_fpkm_worker
    else:
        raise ValueError(_("无效的标准化方法: '{}'。可用选项为 'tpm', 'fpkm', 'rpkm'。").format(normalization_method))

    normalized_results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_sample = {
            executor.submit(target_worker, counts[col], gene_length_kb): col for col in counts.columns
        }
        total_tasks = len(future_to_sample)
        completed_tasks = 0
        for future in as_completed(future_to_sample):
            if check_cancel():
                executor.shutdown(wait=False, cancel_futures=True)
                return None

            result_series = future.result()
            normalized_results.append(result_series)

            completed_tasks += 1
            progress(30 + int((completed_tasks / total_tasks) * 60),
                     _("计算进度 ({}/{}) - 样本: {}").format(
                         completed_tasks, total_tasks, result_series.name.split('_')[0])
                     )

    if check_cancel(): return None

    # --- 4. 结果整合与保存 ---
    progress(95, _("正在整合并保存结果..."))

    original_order = list(counts.columns)
    normalized_results.sort(key=lambda s: original_order.index(s.name.split('_')[0]))
    normalized_df = pd.concat(normalized_results, axis=1)

    final_df = pd.concat([counts, normalized_df], axis=1)

    try:
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        final_df.to_csv(output_path, encoding='utf-8-sig')
        success_message = _("表达量标准化成功！结果已保存至: {}").format(output_path)
        logger.info(success_message)
        progress(100, _("标准化完成。"))
        return success_message
    except Exception as e:
        logger.error(_("保存结果文件时出错: {}").format(e))
        raise IOError(_("保存结果文件时出错: {}").format(e))