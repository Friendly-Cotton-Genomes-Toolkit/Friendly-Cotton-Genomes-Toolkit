# cotton_toolkit/core/downloader.py

import concurrent.futures  # 用于多线程
import gzip  # 用于解压.gz文件
import logging  # 用于日志记录
import os
import shutil  # 用于文件操作 (如 copyfileobj)
from typing import List, Dict, Optional, Callable, Any
from urllib.parse import urlparse  # 用于从URL解析文件名

import requests  # 用于HTTP请求
from tqdm import tqdm  # 用于显示进度条

from cotton_toolkit.core.convertXlsx2csv import convert_xlsx_to_single_csv

# --- 国际化和日志设置 ---
# 假设 _ 函数已由主应用程序入口设置到 builtins
# 为了让静态检查工具识别 _，可以这样做：
try:
    import builtins

    _ = builtins._  # type: ignore
except (AttributeError, ImportError):  # builtins._ 未设置或导入builtins失败
    # 如果在测试或独立运行此模块时，_ 可能未设置
    def _(text: str) -> str:
        return text


    if 'builtins' not in locals() or not hasattr(builtins, '_'):  # 再次检查，避免重复打印
        print("Warning (downloader.py): builtins._ not found for i18n. Using pass-through.")

# 获取logger实例。主应用入口会配置根logger或包logger。
# 这里我们获取一个特定于本模块的logger。
logger = logging.getLogger("cotton_toolkit.downloader")


def decompress_gz_to_temp_file(gz_filepath: str, temp_output_filepath: str) -> bool:
    """
    解压 .gz 文件到指定的临时文件路径。
    """
    try:
        with gzip.open(gz_filepath, 'rb') as f_in:
            with open(temp_output_filepath, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        logger.info(_("文件 '{}' 已成功解压到 '{}'").format(os.path.basename(gz_filepath), temp_output_filepath))
        return True
    except FileNotFoundError:
        logger.error(_("解压失败: 源文件 '{}' 未找到。").format(gz_filepath))
        return False
    except Exception as e:
        logger.error(_("解压文件 '{}' 失败: {}").format(gz_filepath, e))
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
        config: Dict[str, Any],
        genome_versions_to_download_override: Optional[List[str]] = None,
        force_download_override: Optional[bool] = None,
        output_base_dir_override: Optional[str] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        task_done_callback: Optional[Callable[[bool], None]] = None
) -> None:
    """
    为指定的棉花基因组版本多线程下载GFF3注释和与拟南芥的同源基因数据。
    参数主要从配置字典中获取，并允许部分被命令行参数覆盖。
    下载的同源基因文件（如果为.xlsx.gz）会被尝试转换为.csv。

    Args:
        config (Dict[str, Any]): 包含下载器配置 ('downloader') 和可能的基因组源数据 ('genome_sources') 的主配置字典。
        genome_versions_to_download_override (Optional[List[str]]): 覆盖配置，指定要下载的基因组版本列表。
        force_download_override (Optional[bool]): 覆盖配置中的 'force_download' 设置。
        output_base_dir_override (Optional[str]): 覆盖配置中的 'download_output_base_dir'。
        status_callback (Optional[Callable[[str], None]]): 用于向调用者（如GUI）报告状态更新的回调。
        progress_callback (Optional[Callable[[int, str], None]]): 用于向调用者报告进度的回调 (百分比, 消息)。
    """

    def _log_status(msg: str, level: str = "INFO"):
        if status_callback:
            status_callback(msg)
        else:
            if level.upper() == "ERROR":
                logger.error(msg)
            elif level.upper() == "WARNING":
                logger.warning(msg)
            else:
                logger.info(msg)

    def _log_progress(percent: int, msg: str):
        if progress_callback:
            progress_callback(percent, msg)
        else:
            logger.info(f"[{percent}%] {msg}")

    _log_status(_("初始化下载流程..."))
    _log_progress(0, _("准备下载参数..."))

    downloader_cfg = config.get('downloader')
    if not downloader_cfg:
        _log_status(_("错误: 配置中未找到 'downloader' 部分。"), "ERROR");
        return

    # from ..config.loader import get_genome_data_sources # 实际应从这里导入
    # 为了本模块的独立性（如果config loader未完全集成），暂时假设data_sources由config直接提供
    # 或者由调用者（如CLI）在传入config前，已经调用 get_genome_data_sources 并填充了 config['downloader']['genome_sources']
    data_sources = downloader_cfg.get('genome_sources')
    if not data_sources:
        # 如果 config_loader.py 在同一个包内且可用，可以尝试加载
        # from ..config.loader import get_genome_data_sources as get_gs_func # 避免命名冲突
        # data_sources = get_gs_func(config)
        # if not data_sources:
        _log_status(_("错误: 下载器配置中缺少 'genome_sources' 数据。"), "ERROR");
        return

    output_base_dir = output_base_dir_override if output_base_dir_override else \
        downloader_cfg.get('download_output_base_dir', "cotton_genome_data")
    force_download = force_download_override if force_download_override is not None else \
        downloader_cfg.get('force_download', False)
    max_workers = int(downloader_cfg.get('max_workers', 4))  # 确保是整数
    proxies = downloader_cfg.get('proxies')

    if not os.path.exists(output_base_dir):
        try:
            os.makedirs(output_base_dir); _log_status(_("已创建基础输出目录: {}").format(output_base_dir))
        except OSError as e:
            _log_status(_("创建基础输出目录 {} 失败: {}").format(output_base_dir, e), "ERROR"); return

    versions_to_process = []
    if genome_versions_to_download_override:
        versions_to_process = [v for v in genome_versions_to_download_override if v in data_sources]
        skipped = [v for v in genome_versions_to_download_override if v not in data_sources]
        if skipped: _log_status(_("警告: 版本 {} 未定义，已跳过。").format(", ".join(skipped)), "WARNING")
    else:
        versions_to_process = list(data_sources.keys())

    if not versions_to_process: _log_status(_("没有有效的基因组版本被指定下载。")); return
    _log_status(_("将尝试下载的基因组版本: {}").format(", ".join(versions_to_process)))
    _log_progress(5, _("版本列表确定。"))

    download_specs = []
    for version_name in versions_to_process:
        genome_info = data_sources.get(version_name)
        if not genome_info: _log_status(_("警告: 未找到版本 '{}' 的信息，跳过。").format(version_name),
                                        "WARNING"); continue

        safe_dir_name = genome_info.get("species_name", version_name).replace(" ", "_").replace(".", "_").replace("(",
                                                                                                                  "").replace(
            ")", "").replace("'", "")
        version_output_dir = os.path.join(output_base_dir, safe_dir_name)

        for file_key, file_type_desc, default_name_pattern, is_excel in [
            ("gff3_url", _('GFF3'), "{}_annotations.gff3.gz", False),
            ("homology_ath_url", _('同源数据'), "{}_homology_ath.xlsx.gz", True)
        ]:
            url = genome_info.get(file_key)
            if url:
                parsed_url = urlparse(url)
                filename = os.path.basename(parsed_url.path) if parsed_url.path and '.' in os.path.basename(
                    parsed_url.path) else default_name_pattern.format(safe_dir_name)
                target_path = os.path.join(version_output_dir, filename)
                download_specs.append({
                    'url': url, 'target_path': target_path,
                    'desc_for_tqdm': f"{version_name}_{file_type_desc}",
                    'version_name': version_name, 'file_type': file_type_desc,
                    'is_homology_excel': is_excel
                })
            else:
                _log_status(_("信息: 版本 {} 未提供 {} 下载链接。").format(version_name, file_type_desc), "INFO")

    overall_success = True  # 根据实际下载结果设置

    if not download_specs: _log_status(_("没有文件需要下载。")); return
    _log_status(_("准备下载 {} 个文件，使用最多 {} 个并发线程... (代理: {})").format(
        len(download_specs), max_workers, proxies if proxies else _("系统默认/无")))
    _log_progress(10, _("下载任务列表已创建。"))

    successful_downloads = 0
    failed_downloads = 0
    total_tasks = len(download_specs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_spec = {
            executor.submit(download_file, spec['url'], spec['target_path'], force_download, spec['desc_for_tqdm'],
                            proxies): spec
            for spec in download_specs
        }
        completed_count = 0
        for future in tqdm(concurrent.futures.as_completed(future_to_spec), total=total_tasks, desc=_("总体下载进度"),
                           unit="file"):
            spec = future_to_spec[future]
            completed_count += 1
            current_progress_percent = int((completed_count / total_tasks) * 100)
            try:
                download_successful = future.result()
                if download_successful:
                    successful_downloads += 1
                    _log_status(_("成功下载: {} 的 {} -> {}").format(spec['version_name'], spec['file_type'],
                                                                     spec['target_path']), "INFO")

                    if spec['is_homology_excel'] and spec['target_path'].lower().endswith((".xlsx.gz", ".xls.gz")):
                        gz_excel_path = spec['target_path']
                        base_name_no_gz_ext = os.path.splitext(os.path.basename(gz_excel_path))[0]  # xxx.xlsx
                        csv_filename = os.path.splitext(base_name_no_gz_ext)[0] + ".csv"  # xxx.csv
                        final_csv_path = os.path.join(os.path.dirname(gz_excel_path), csv_filename)

                        _log_status(_("尝试转换同源Excel文件: {} -> {}").format(os.path.basename(gz_excel_path),
                                                                                os.path.basename(final_csv_path)))

                        if not force_download and os.path.exists(final_csv_path):
                            _log_status(_("CSV 文件已存在: {} (跳过转换)").format(final_csv_path))
                        else:
                            # 临时的解压后xlsx文件名 (与gz同名，但去掉.gz)
                            temp_xlsx_path = os.path.splitext(gz_excel_path)[0]
                            if decompress_gz_to_temp_file(gz_excel_path, temp_xlsx_path):
                                conversion_ok = False
                                try:
                                    if convert_xlsx_to_single_csv(temp_xlsx_path, final_csv_path):
                                        _log_status(
                                            _("用户转换函数成功处理 '{}'。").format(os.path.basename(temp_xlsx_path)))
                                        conversion_ok = True
                                    else:
                                        _log_status(_("用户转换函数报告处理 '{}' 失败。").format(
                                            os.path.basename(temp_xlsx_path)), "WARNING")
                                except Exception as conv_e:
                                    _log_status(_("调用用户转换函数处理 '{}' 时发生错误: {}").format(
                                        os.path.basename(temp_xlsx_path), conv_e), "ERROR")
                                finally:
                                    if os.path.exists(temp_xlsx_path):
                                        try:
                                            os.remove(temp_xlsx_path); _log_status(
                                                _("已删除临时解压文件: {}").format(temp_xlsx_path))
                                        except OSError as e_del:
                                            _log_status(_("删除临时文件 {} 失败: {}").format(temp_xlsx_path, e_del),
                                                        "WARNING")
                                if conversion_ok:
                                    _log_status(_("同源数据已转换为CSV: {}").format(final_csv_path), "INFO")
                                else:
                                    _log_status(_("警告: 同源文件 {} 未能成功转换为CSV。").format(
                                        os.path.basename(gz_excel_path)), "WARNING")
                            else:  # 解压失败
                                _log_status(_("解压 {} 失败，无法进行CSV转换。").format(os.path.basename(gz_excel_path)),
                                            "WARNING")
                else:  # download_successful is False
                    failed_downloads += 1
            except Exception as exc:
                failed_downloads += 1
                _log_status(
                    _("下载任务 {} ({}) 产生了一个异常: {}").format(spec['version_name'], spec['file_type'], exc),
                    "ERROR")
                overall_success = False

            _log_progress(current_progress_percent, _("已处理 {}/{} 个下载任务").format(completed_count, total_tasks))

    summary_msg = _("\n下载摘要: {} 个文件成功, {} 个文件失败。").format(successful_downloads, failed_downloads)
    final_msg = _("所有指定的下载任务已完成。")
    _log_status(summary_msg)
    _log_status(final_msg)
    _log_progress(100, _("下载流程结束。"))
    task_done_callback(overall_success)  # 在任务结束时调用


# --- 用于独立测试 downloader.py 的示例代码 ---
if __name__ == '__main__':
    # 设置基本的日志记录，以便在独立运行时能看到logger的输出
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 模拟一个主配置字典
    mock_config = {
        "downloader": {
            "genome_sources": {
                "NBI_v1.1_test": {  # 与 GENOME_DATA_SOURCES 中的键名匹配
                    "gff3_url": "https://www.cottongen.org/files/GACI_CSG_AtDt_merged_Jun2018.gff3.gz",  # 一个真实但可能较大的文件
                    "homology_ath_url": "http://www.ebi.ac.uk/QuickGO/GAnnotation?format=tsv&geneProductId=A0A075ENS8",
                    # 一个小的xlsx.gz替代品 (实际是tsv)
                    # 为了测试，最好找到一个真实的、小的 .xlsx.gz
                    "species_name": "Gossypium_hirsutum_NBI_v1.1_testdl"
                },
                "INVALID_URL_TEST": {
                    "gff3_url": "http://invalid.url/somefile.gff3.gz",
                    "species_name": "Invalid_Test_sp"
                }
            },
            "download_output_base_dir": "test_downloader_output",
            "force_download": False,  # 改为True以测试下载
            "max_workers": 2,
            "proxies": None  # {"http": "...", "https": "..."}
        },
        # 可以添加其他应用的配置部分，如果 downloader 内部的辅助函数（如get_genome_data_sources）依赖它们
        # '_config_file_abs_path_': os.getcwd() # 模拟主配置文件路径
    }

    # 清理上次的测试输出目录
    if os.path.exists(mock_config['downloader']['download_output_base_dir']):
        shutil.rmtree(mock_config['downloader']['download_output_base_dir'])
        print(f"已清理旧的测试下载目录: {mock_config['downloader']['download_output_base_dir']}")

    print(_("--- 开始独立测试 downloader.py ---"))
    download_genome_data(
        config=mock_config,
        # genome_versions_to_download_override=["NBI_v1.1_test", "INVALID_URL_TEST"],
        force_download_override=True  # 强制下载以测试
    )
    print(_("--- downloader.py 测试结束 ---"))