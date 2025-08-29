import logging
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures import as_completed
import pandas as pd
from typing import Optional, Dict, Any, Callable
import os
import threading

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
        return sample_series # 如果总读数为0，则返回原始计数（全为0）
    fpkm_series = sample_series.div(gene_length_kb).div(total_reads_per_million)
    fpkm_series.name = f"{sample_series.name}_FPKM_RPKM"
    return fpkm_series

def _calculate_tpm_worker(sample_series: pd.Series, gene_length_kb: pd.Series) -> pd.Series:
    """计算单个样本(列)的TPM值"""
    rpk_series = sample_series.div(gene_length_kb)
    rpk_sum_per_million = rpk_series.sum() / 1_000_000
    if rpk_sum_per_million == 0:
        return sample_series # 如果总和为0，则返回原始计数（全为0）
    tpm_series = rpk_series.div(rpk_sum_per_million)
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
    使用多线程按样本加速计算。
    """
    progress = kwargs.get('progress_callback', lambda p, m: print(f"进度: {p}%, 信息: {m}"))
    check_cancel = kwargs.get('check_cancel', lambda: False)

    progress(0, _("开始表达量标准化..."))
    if check_cancel(): return None

    # 1. 读取输入文件
    try:
        progress(5, _("正在智能加载原始计数文件..."))
        counts_df = smart_load_file(counts_file_path)
        if counts_df is None:
            raise IOError(_("无法加载或不支持的计数文件格式: {}").format(os.path.basename(counts_file_path)))
        # 手动将第一列设置为索引，以兼容后续逻辑
        counts_df.set_index(counts_df.columns[0], inplace=True)

        progress(10, _("正在智能加载基因长度文件..."))
        lengths_df = smart_load_file(gene_lengths_file_path)
        if lengths_df is None:
            raise IOError(_("无法加载或不支持的基因长度文件格式: {}").format(os.path.basename(gene_lengths_file_path)))
        # 手动重命名列并设置索引，以兼容后续逻辑
        if len(lengths_df.columns) < 2:
            raise ValueError(_("基因长度文件必须至少有两列（基因ID 和 长度）。"))
        lengths_df = lengths_df.iloc[:, [0, 1]]  # 只取前两列
        lengths_df.columns = ['gene_id', 'length']
        lengths_df.set_index('gene_id', inplace=True)

    except (FileNotFoundError, IOError, ValueError) as e:
        raise e
    except Exception as e:
        raise IOError(_("读取输入文件时发生未知错误: {}").format(e))

    if check_cancel(): return None

    # 2. 数据预处理与合并
    progress(20, _("正在对齐计数与长度数据..."))

    # 1. 找到两个文件共有的基因ID
    common_genes = counts_df.index.intersection(lengths_df.index)

    if common_genes.empty:
        raise ValueError(_("基因ID无法匹配，请检查计数文件和长度文件的基因ID格式是否一致。"))

    logger.info(_("成功匹配 {} 个基因的计数和长度信息。").format(len(common_genes)))

    # 2. 根据共有的基因ID，分别过滤和对齐两个数据表
    counts = counts_df.loc[common_genes]
    lengths = lengths_df.loc[common_genes, 'length']  # 直接从长度表中提取 'length' 列

    gene_length_kb = lengths / 1000
    # --- 修改结束 ---

    if check_cancel(): return None

    # 3. 根据选择的方法，使用多线程进行计算 (此部分及以后无需修改)
    method = normalization_method.lower()
    progress(30, _("正在为 '{}' 方法准备并行计算任务...").format(method.upper()))

    normalized_results = []
    target_worker = None

    if method == 'tpm':
        target_worker = _calculate_tpm_worker
    elif method in ['fpkm', 'rpkm']:
        target_worker = _calculate_fpkm_worker
    else:
        raise ValueError(_("无效的标准化方法: '{}'。可用选项为 'tpm', 'fpkm', 'rpkm'。").format(normalization_method))

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

            sample_name = future_to_sample[future]
            try:
                result_series = future.result()
                normalized_results.append(result_series)
            except Exception as exc:
                logger.error(_("样本 '{}' 的计算失败: {}").format(sample_name, exc))
            finally:
                completed_tasks += 1
                progress(30 + int((completed_tasks / total_tasks) * 60),
                         _("计算进度 ({}/{}) - 样本: {}").format(completed_tasks, total_tasks, sample_name))

    if check_cancel(): return None

    # 4. 整合并保存结果
    progress(95, _("正在整合并保存结果..."))

    # 将所有线程的结果按原始顺序合并
    normalized_df = pd.concat(sorted(normalized_results, key=lambda s: s.name), axis=1)

    # 将原始计数与计算结果合并
    final_df = pd.concat([counts, normalized_df], axis=1)

    try:
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        final_df.to_csv(output_path, encoding='utf-8-sig')
        success_message = _("表达量标准化成功！结果已保存至: {}").format(output_path)
        logger.info(success_message)
        progress(100, _("标准化完成。"))
        return success_message
    except Exception as e:
        raise IOError(_("保存结果文件时出错: {}").format(e))


# --- 用于独立测试的模块 ---
if __name__ == '__main__':
    print("--- 开始独立测试表达量标准化模块 (V2) ---")
    test_dir = "temp_test_data"
    os.makedirs(test_dir, exist_ok=True)

    # 创建测试文件 (与之前相同)
    pd.DataFrame({
        'gene_id': ['gene1', 'gene2', 'gene3', 'gene4'],
        'sampleA': [10, 200, 5, 0],
        'sampleB': [15, 350, 10, 0],
        'sampleC': [50, 100, 2, 80],
        'sampleD': [25, 50, 1, 40]
    }).to_csv(os.path.join(test_dir, "dummy_counts.csv"), index=False)
    pd.DataFrame({
        'gene_id': ['gene1', 'gene2', 'gene4', 'gene5'],
        'length': [1000, 2500, 1500, 3000]
    }).to_csv(os.path.join(test_dir, "dummy_lengths.csv"), index=False, header=False)

    counts_file = os.path.join(test_dir, "dummy_counts.csv")
    lengths_file = os.path.join(test_dir, "dummy_lengths.csv")

    # --- 测试1: 计算 TPM ---
    try:
        print("\n--- 测试 1: 计算 TPM ---")
        output_tpm_file = os.path.join(test_dir, "normalized_tpm.csv")
        run_expression_normalization(
            counts_file_path=counts_file,
            gene_lengths_file_path=lengths_file,
            output_path=output_tpm_file,
            normalization_method='tpm',
            max_workers=4
        )
        print("\nTPM 结果预览:")
        print(pd.read_csv(output_tpm_file, index_col=0))
    except Exception as e:
        print(f"TPM 测试失败: {e}")

    # --- 测试2: 计算 FPKM ---
    try:
        print("\n--- 测试 2: 计算 FPKM ---")
        output_fpkm_file = os.path.join(test_dir, "normalized_fpkm.csv")
        run_expression_normalization(
            counts_file_path=counts_file,
            gene_lengths_file_path=lengths_file,
            output_path=output_fpkm_file,
            normalization_method='fpkm',
            max_workers=4
        )
        print("\nFPKM 结果预览:")
        print(pd.read_csv(output_fpkm_file, index_col=0))
    except Exception as e:
        print(f"FPKM 测试失败: {e}")

    print("\n--- 测试结束 ---")
