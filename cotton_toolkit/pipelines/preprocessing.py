import gzip
import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, Callable
import logging
import sqlite3
from cotton_toolkit import PREPROCESSED_DB_NAME, GFF3_DB_DIR
from cotton_toolkit.config.loader import get_genome_data_sources, get_local_downloaded_file_path
from cotton_toolkit.config.models import MainConfig, GenomeSourceItem
from cotton_toolkit.core.convertFiles2sqlite import _read_excel_to_dataframe, _read_text_to_dataframe, \
    _read_annotation_text_file, _read_fasta_to_dataframe
from cotton_toolkit.core.downloader import download_genome_data
from cotton_toolkit.core.file_normalizer import normalize_to_csv
from cotton_toolkit.core.gff_parser import create_gff_database
from cotton_toolkit.pipelines.decorators import pipeline_task
from cotton_toolkit.utils.file_utils import _sanitize_table_name

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text

logger = logging.getLogger("cotton_toolkit.pipeline.preprocessing")


def _create_sub_progress_updater(
        main_progress_callback: Callable[[int, str], None],
        task_name: str,
        start_percentage: float,
        end_percentage: float
) -> Callable[[int, str], None]:
    """
    创建一个用于子任务的进度更新器。
    它会将子任务的0-100%进度映射到主进度条的 [start, end] 区间。
    """

    def sub_progress_updater(sub_percentage: int, sub_message: str):
        # 将子进度的百分比 (0-100) 转换为在主进度条上的绝对值
        main_percentage = start_percentage + (sub_percentage / 100.0) * (end_percentage - start_percentage)
        # 格式化消息，包含主任务名和子任务状态
        message = f"{task_name}: {sub_message}"
        main_progress_callback(int(main_percentage), message)

    return sub_progress_updater


def _process_single_file_to_sqlite(
        file_key: str,
        source_path: str,
        db_path: str,
        version_id: str,
        id_regex: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None
) -> bool:
    """
    Worker function to process a single annotation file and write it to a SQLite table.
    Now supports detailed progress reporting.
    """
    progress = progress_callback if progress_callback else lambda p, m: None

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            raise InterruptedError(_("文件处理过程被取消。"))

    table_name = _sanitize_table_name(os.path.basename(source_path), version_id=version_id)
    conn = None

    try:
        progress(0, _("开始处理..."))
        # Step 1: File reading and parsing
        check_cancel()
        progress(10, _("正在读取文件..."))

        dataframe = None
        filename_lower = source_path.lower()

        if file_key == 'predicted_cds':
            dataframe = _read_fasta_to_dataframe(source_path, id_regex=id_regex)
        elif filename_lower.endswith(('.xlsx', '.xlsx.gz')):
            dataframe = _read_excel_to_dataframe(source_path)
        elif file_key in ['GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs', 'homology_ath']:
            dataframe = _read_annotation_text_file(source_path)
        else:
            dataframe = _read_text_to_dataframe(source_path)

        check_cancel()

        if dataframe is None or dataframe.empty:
            logger.warning(_("跳过文件 '{}'，因为未能读取到有效数据。").format(os.path.basename(source_path)))
            return False

        progress(50, _("文件读取完毕, 正在清洗ID..."))

        if id_regex and file_key != 'predicted_cds':
            target_column = 'Query'
            if target_column in dataframe.columns:
                logger.debug(
                    _("正在对 {} 的 '{}' 列应用正则表达式...").format(os.path.basename(source_path), target_column))
                cleaned_ids = dataframe[target_column].astype(str).str.extract(id_regex).iloc[:, 0]
                dataframe[target_column] = cleaned_ids.fillna(dataframe[target_column])
                logger.info(_("成功清洗了 '{}' 列。").format(target_column))
            else:
                logger.warning(
                    f"文件 {os.path.basename(source_path)} 中未找到预期的 '{target_column}' 列，跳过清洗。")

        # Step 2: Database writing
        progress(75, _("正在写入数据库..."))
        try:
            conn = sqlite3.connect(db_path, timeout=30.0)
            dataframe.to_sql(table_name, conn, if_exists='replace', index=False)
            conn.close()
            conn = None
        finally:
            if conn:
                conn.close()

        check_cancel()
        logger.info(_("成功将 '{}' 转换到表 '{}'。").format(os.path.basename(source_path), table_name))
        progress(100, _("处理完成"))
        return True

    except InterruptedError:
        logger.warning(_("文件 '{}' 的处理过程被取消。").format(os.path.basename(source_path)))
        progress(100, _("任务已取消"))
        # Cleanup logic for cancelled tasks
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            conn.commit()
            conn.close()
            logger.info(_("成功清理表 '{}'。").format(table_name))
        except Exception as cleanup_e:
            logger.error(_("清理表 '{}' 时发生错误: {}").format(table_name, cleanup_e))
        return False

    except Exception as e:
        progress(100, _("处理失败"))
        logger.error(
            _("处理文件 '{}' 到表 '{}' 时发生错误。原因: {}").format(os.path.basename(source_path), table_name, e))
        return False


def check_preprocessing_status(config: MainConfig, genome_info: GenomeSourceItem) -> Dict[str, str]:
    """
    检查预处理状态。使用基于配置文件位置的绝对路径来定位数据库。
    """
    status_dict = {}

    config_file_path = getattr(config, 'config_file_abs_path_', None)
    if not config_file_path:
        logger.error("Config对象缺少绝对路径锚点，无法定位数据库。")
        return {}

    project_root = os.path.dirname(config_file_path)
    db_path = os.path.join(project_root, PREPROCESSED_DB_NAME)
    db_exists = os.path.exists(db_path)
    logger.debug(f"[CHECKER] Attempting to check database at absolute path: {db_path}")

    ALL_FILE_KEYS = [
        "predicted_cds", "predicted_protein", "gff3", "GO", "IPR",
        "KEGG_pathways", "KEGG_orthologs", "homology_ath"
    ]

    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True) if db_exists else None
    cursor = conn.cursor() if conn else None

    try:
        for key in ALL_FILE_KEYS:
            url_attr = f"{key}_url"
            if not hasattr(genome_info, url_attr) or not getattr(genome_info, url_attr):
                continue

            local_path = get_local_downloaded_file_path(config, genome_info, key)
            status = 'not_downloaded'

            if local_path and os.path.exists(local_path):
                status = 'downloaded'

                # --- 核心状态判断逻辑 ---
                if key == 'predicted_cds':
                    # 检查1: BLAST数据库是否存在
                    db_fasta_path = local_path.removesuffix('.gz')
                    db_type = 'prot' if key == 'predicted_protein' else 'nucl'
                    db_check_ext = '.phr' if db_type == 'prot' else '.nhr'
                    blast_exists = os.path.exists(db_fasta_path + db_check_ext)

                    # 检查2: SQLite中的数据表是否存在
                    table_exists = False
                    if cursor:
                        table_name = _sanitize_table_name(os.path.basename(local_path),
                                                          version_id=genome_info.version_id)
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                        if cursor.fetchone():
                            table_exists = True

                    # 根据两个检查结果判断最终状态
                    if blast_exists and table_exists:
                        status = 'processed'  # 已就绪
                    elif blast_exists and not table_exists:
                        status = 'db_only'  # 仅建库
                    elif not blast_exists and table_exists:
                        status = 'organized_only'  # 仅整理

                elif key == 'predicted_protein':
                    # 蛋白质文件简化为双状态：只要BLAST库建好，即为“已就绪”
                    db_fasta_path = local_path.removesuffix('.gz')
                    if os.path.exists(db_fasta_path + '.phr'):
                        status = 'processed'

                elif key == 'gff3':
                    gff_db_dir = os.path.join(project_root, GFF3_DB_DIR)
                    db_filename = f"{genome_info.version_id}_genes.db"
                    if os.path.exists(os.path.join(gff_db_dir, db_filename)):
                        status = 'processed'

                elif key in ['GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs', 'homology_ath']:
                    if cursor:
                        table_name = _sanitize_table_name(os.path.basename(local_path),
                                                          version_id=genome_info.version_id)
                        logger.debug(
                            f"[CHECKER] For file '{os.path.basename(local_path)}', checking for table: '{table_name}'")
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
                        if cursor.fetchone():
                            status = 'processed'

            status_dict[key] = status
    finally:
        if conn:
            conn.close()

    return status_dict


@pipeline_task(_("数据下载"))
def run_download_pipeline(
        config: MainConfig,
        cli_overrides: Optional[Dict[str, Any]] = None,
        **kwargs
):

    progress = kwargs.get('progress_callback')
    cancel_event = kwargs.get('cancel_event')
    check_cancel = kwargs.get('check_cancel')

    progress(0, _("下载流程开始..."))
    if check_cancel(): logger.info(_("任务在启动时被取消。")); return
    logger.info(_("下载流程开始..."))

    downloader_cfg = config.downloader
    # 修改: get_genome_data_sources 不再需要 logger_func
    genome_sources = get_genome_data_sources(config)
    if cli_overrides is None: cli_overrides = {}

    versions_to_download = cli_overrides.get("versions") or list(genome_sources.keys())
    force_download = cli_overrides.get("force", downloader_cfg.force_download)
    max_workers = downloader_cfg.max_workers
    use_proxy_for_this_run = cli_overrides.get("use_proxy_for_download", downloader_cfg.use_proxy_for_download)

    file_keys_to_process = cli_overrides.get("file_types")

    proxies_to_use = None
    if use_proxy_for_this_run:
        if config.proxies and (config.proxies.http or config.proxies.https):
            proxies_to_use = config.proxies.model_dump(exclude_none=True)
            logger.info(_("本次下载将使用代理: {}").format(proxies_to_use))
        else:
            logger.warning(_("下载代理开关已打开，但配置文件中未设置代理地址。"))

    progress(5, _("正在准备下载任务列表..."))
    if check_cancel(): logger.info(_("任务被取消。")); return

    logger.info(_("将尝试下载的基因组版本: {}").format(', '.join(versions_to_download)))

    all_download_tasks = []
    if not file_keys_to_process:
        all_possible_keys = [f.name.replace('_url', '') for f in GenomeSourceItem.model_fields.values() if
                             f.name.endswith('_url')]
        logger.debug(_("未从UI指定文件类型，将尝试检查所有可能的类型: {}").format(all_possible_keys))
    else:
        all_possible_keys = file_keys_to_process
        logger.debug(_("将根据UI的选择，精确下载以下文件类型: {}").format(all_possible_keys))

    for version_id in versions_to_download:
        if cancel_event and cancel_event.is_set(): break
        genome_info = genome_sources.get(version_id)
        if not genome_info:
            logger.warning(_("在基因组源中未找到版本 '{}'，已跳过。").format(version_id))
            continue

        for file_key in all_possible_keys:
            url_attr = f"{file_key}_url"
            if hasattr(genome_info, url_attr):
                url = getattr(genome_info, url_attr)
                if url:
                    all_download_tasks.append({
                        "version_id": version_id,
                        "genome_info": genome_info,
                        "file_key": file_key,
                        "url": url
                    })

    if check_cancel(): logger.info(_("任务在任务列表创建期间被取消。")); return

    if not all_download_tasks:
        logger.warning(_("根据您的选择，没有找到任何有效的URL可供下载。"))
        progress(100, _("任务完成：无文件可下载。"))
        return

    progress(10, _("找到 {} 个文件需要下载。").format(len(all_download_tasks)))
    if check_cancel(): logger.info(_("任务被取消。")); return
    logger.info(_("准备下载 {} 个文件...").format(len(all_download_tasks)))

    successful_downloads, failed_downloads = 0, 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(
                download_genome_data,
                downloader_config=config.downloader,
                version_id=task["version_id"],
                genome_info=task["genome_info"],
                file_key=task["file_key"],
                url=task["url"],
                force=force_download,
                proxies=proxies_to_use,
                cancel_event=cancel_event,
            ): task for task in all_download_tasks
        }

        total_tasks = len(future_to_task)
        current_completed_tasks = 0
        for future in as_completed(future_to_task):
            if cancel_event and cancel_event.is_set():
                logger.info(_("下载任务已被用户取消。"))
                progress(100, _("任务已取消。"))
                for f in future_to_task:
                    f.cancel()
                break

            task_info = future_to_task[future]
            try:
                if future.result():
                    successful_downloads += 1
                else:
                    failed_downloads += 1
            except Exception as exc:
                if not isinstance(exc, threading.CancelledError):
                    logger.error(_("下载 {} 的 {} 文件时发生严重错误: {}").format(task_info['version_id'],
                                                                                  task_info['file_key'], exc))
                failed_downloads += 1
            finally:
                current_completed_tasks += 1
                progress_percentage = 10 + int((current_completed_tasks / total_tasks) * 85)
                progress(progress_percentage,
                         f"{_('总体下载进度')} ({current_completed_tasks}/{total_tasks}) - {task_info['version_id']} {task_info['file_key']}")

    logger.info(_("所有指定的下载任务已完成。成功: {}, 失败: {}。").format(successful_downloads, failed_downloads))
    progress(100, _("下载流程完成。"))


@pipeline_task(task_name=_("预处理注释文件"))
def run_preprocess_annotation_files(
        config: MainConfig,
        selected_assembly_id: Optional[str] = None,
        status_callback: Optional[Callable[[str, str], None]] = None,
        **kwargs) -> bool:
    """
    串行预处理所有注释和同源文件。
    """
    progress = kwargs.get('progress_callback')
    cancel_event = kwargs.get('cancel_event')
    check_cancel = kwargs.get('check_cancel')
    status_update = status_callback if status_callback else lambda key, msg: None

    if check_cancel(): return False

    progress(0, _("开始预处理所有注释文件..."))
    logger.info(_("开始预处理所有注释文件 (包括GFF)..."))

    progress(5, _("正在加载基因组源数据..."))
    if check_cancel(): return False

    genome_sources = get_genome_data_sources(config)
    if not selected_assembly_id or selected_assembly_id not in genome_sources:
        raise ValueError(_("错误：预处理需要从UI明确选择一个基因组版本。"))


    genome_info = genome_sources[selected_assembly_id]
    progress(10, _("正在检查所有文件状态..."))
    all_statuses = check_preprocessing_status(config, genome_info)

    # 1. 将所有任务统一收集
    tasks_to_run = []
    project_root = os.path.dirname(config.config_file_abs_path_)

    ALL_ANNOTATION_KEYS = ['predicted_cds', 'gff3', 'GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs', 'homology_ath']
    files_to_process_keys = [
        key for key in ALL_ANNOTATION_KEYS
        if all_statuses.get(key, 'not_downloaded') not in ['processed', 'not_downloaded']
    ]

    if not files_to_process_keys:
        logger.info(_("所有注释文件均已处理完毕，无需再次运行。"))
        progress(100, _("所有文件均已是最新状态。"))
        return True

    for key in files_to_process_keys:
        source_path = get_local_downloaded_file_path(config, genome_info, key)
        if not source_path or not os.path.exists(source_path):
            logger.warning(f"Skipping {key} as its source file is not found at {source_path}")
            continue

        task_info = {"key": key, "source_path": source_path}
        if key == 'gff3':
            gff_db_dir = os.path.join(project_root, GFF3_DB_DIR)
            db_filename = f"{genome_info.version_id}_genes.db"
            final_db_path = os.path.join(gff_db_dir, db_filename)
            task_info["target_func"] = create_gff_database
            task_info["args"] = {
                "gff_filepath": source_path, "db_path": final_db_path,
                "force": True, "id_regex": genome_info.gene_id_regex
            }
        else:
            db_path = os.path.join(project_root, PREPROCESSED_DB_NAME)
            KEYS_NEEDING_REGEX = ['predicted_cds', 'GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs', 'homology_ath']
            regex_to_use = genome_info.gene_id_regex if key in KEYS_NEEDING_REGEX else None
            task_info["target_func"] = _process_single_file_to_sqlite
            task_info["args"] = {
                "file_key": key, "source_path": source_path, "db_path": db_path,
                "version_id": genome_info.version_id, "id_regex": regex_to_use,
                "cancel_event": cancel_event,
            }
        tasks_to_run.append(task_info)

    if not tasks_to_run:
        logger.warning(_("未找到有效文件进行处理。"))
        progress(100, "未找到有效文件进行处理。")
        return True

    logger.info(_("检测到以下待处理文件: {}").format(", ".join(t['key'] for t in tasks_to_run)))
    progress(20, _("找到 {} 个待处理文件...").format(len(tasks_to_run)))

    # 2. 串行执行所有任务
    overall_success = True
    errors_found = []
    total_tasks = len(tasks_to_run)
    task_weight = 80 / total_tasks if total_tasks > 0 else 0

    for i, task in enumerate(tasks_to_run):
        if check_cancel():
            overall_success = False
            break

        key = task['key']
        status_update(key, _("处理中..."))

        start_p = 20 + i * task_weight
        end_p = 20 + (i + 1) * task_weight
        sub_progress = _create_sub_progress_updater(progress, os.path.basename(task['source_path']), start_p, end_p)
        task['args']['progress_callback'] = sub_progress

        try:
            # 直接调用目标函数
            result = task['target_func'](**task['args'])
            if result:
                status_update(key, _("完成"))
            else:
                # 如果任务被取消，也记录下来
                if cancel_event and cancel_event.is_set():
                    status_update(key, _("已取消"))
                    errors_found.append(_("文件 '{}' 的处理被取消。").format(key))
                else:
                    status_update(key, _("失败"))
                    errors_found.append(_("文件 '{}' 处理失败，但未提供具体错误原因。").format(key))

        except Exception as e:
            status_update(key, _("错误"))
            error_msg = _("处理文件 '{}' 时发生错误: {}").format(key, e)
            errors_found.append(error_msg)
            logger.error(error_msg, exc_info=True)


    if errors_found:
        summary_error = _("部分文件在预处理过程中失败或被取消:\n\n") + "\n".join(f"- {e}" for e in errors_found)
        raise RuntimeError(summary_error)

    # 3. 最终总结
    if overall_success:
        logger.info(_("所有待处理的注释文件均已成功预处理。"))
        progress(100, _("预处理完成。"))
    else:
        logger.error(_("部分文件在预处理过程中失败，请检查日志。"))
        progress(100, _("任务因错误而终止。"))

    return overall_success


def _process_single_blast_db(
        compressed_file: str,
        db_fasta_path: str,
        db_type: str,
        cancel_event: Optional[threading.Event] = None
) -> str:
    """
    处理单个FASTA文件以构建BLAST数据库的worker函数。
    返回处理结果的日志信息。
    """

    def check_cancel():
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Task cancelled.")

    try:
        if compressed_file.endswith('.gz'):
            if not os.path.exists(db_fasta_path) or os.path.getmtime(compressed_file) > os.path.getmtime(db_fasta_path):
                logger.info(_("正在解压 {}...").format(os.path.basename(compressed_file)))
                with gzip.open(compressed_file, 'rb') as f_in, open(db_fasta_path, 'wb') as f_out:
                    while True:
                        check_cancel()
                        chunk = f_in.read(1024 * 1024)
                        if not chunk: break
                        f_out.write(chunk)

        check_cancel()

        logger.info(_("正在为 {} 创建 {} 数据库...").format(os.path.basename(db_fasta_path), db_type))
        makeblastdb_cmd = ["makeblastdb", "-in", db_fasta_path, "-dbtype", db_type, "-out", db_fasta_path]

        result = subprocess.run(makeblastdb_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        return _("数据库 {} 创建成功。").format(os.path.basename(db_fasta_path))

    except InterruptedError:
        return _("任务在解压时被取消: {}").format(os.path.basename(compressed_file))
    except FileNotFoundError:
        msg = _("错误: 'makeblastdb' 命令未找到。请确保 BLAST+ 已被正确安装并添加到了系统的 PATH 环境变量中。")
        logger.error(msg)
        raise  # 重新抛出异常，让主线程知道
    except subprocess.CalledProcessError as e:
        return _("创建数据库 {} 失败: {}").format(os.path.basename(db_fasta_path), e.stderr)
    except Exception as e:
        return _("处理文件 {} 时发生未知错误: {}").format(os.path.basename(compressed_file), e)


@pipeline_task(task_name=_("构建BLAST数据库"))
def run_build_blast_db_pipeline(
        config: MainConfig,
        selected_assembly_id: Optional[str] = None,
        status_callback: Optional[Callable[[str, str], None]] = None,
        **kwargs
) -> bool:
    progress = kwargs.get('progress_callback')
    cancel_event = kwargs.get('cancel_event')
    check_cancel = kwargs.get('check_cancel')
    status_update = status_callback if status_callback else lambda key, msg: None

    if check_cancel(): return False

    progress(0, _("开始预处理BLAST数据库..."))
    if check_cancel(): logger.info(_("任务被取消。")); return False
    logger.info(_("开始批量创建BLAST数据库..."))

    progress(5, _("正在加载基因组源数据..."))
    if check_cancel(): logger.info(_("任务被取消。")); return False
    genome_sources = get_genome_data_sources(config)
    if not genome_sources:
        raise ValueError(_("任务终止：未能加载基因组源数据。"))

    genomes_to_process = [genome_sources[
                              selected_assembly_id]] if selected_assembly_id and selected_assembly_id in genome_sources else genome_sources.values()

    tasks_to_run = []
    BLAST_FILE_KEYS = ['predicted_cds', 'predicted_protein']
    progress(10, _("正在检查需要预处理的文件..."))
    if check_cancel(): logger.info(_("任务被取消。")); return False

    for genome_info in genomes_to_process:
        if check_cancel(): break
        for key in BLAST_FILE_KEYS:
            url_attr = f"{key}_url"
            if not hasattr(genome_info, url_attr) or not getattr(genome_info, url_attr):
                continue

            compressed_file = get_local_downloaded_file_path(config, genome_info, key)
            if not compressed_file or not os.path.exists(compressed_file):
                continue

            db_fasta_path = compressed_file.removesuffix('.gz')
            db_type = 'prot' if key == 'predicted_protein' else 'nucl'
            db_check_ext = '.phr' if db_type == 'prot' else '.nhr'

            if not os.path.exists(db_fasta_path + db_check_ext):
                tasks_to_run.append((compressed_file, db_fasta_path, db_type))

    if check_cancel(): logger.info(_("任务在文件检查后被取消。")); return False

    if not tasks_to_run:
        logger.info(_("所有BLAST数据库均已是最新状态，无需预处理。"))
        progress(100, _("无需处理，所有文件已是最新。"))
        return True

    total_tasks = len(tasks_to_run)
    progress(20, _("找到 {} 个BLAST数据库需要创建。").format(total_tasks))
    logger.info(_("找到 {} 个BLAST数据库需要创建。").format(total_tasks))

    errors_found = []
    success_count = 0
    completed_count = 0

    for task_tuple in tasks_to_run:
        if check_cancel():
            break

        file_key = os.path.basename(task_tuple[0])
        status_update(file_key, _("处理中..."))

        try:
            result_msg = _process_single_blast_db(*task_tuple, cancel_event)
            logger.info(f"Task {file_key}: {result_msg}")
            if "成功" in result_msg:
                success_count += 1
                status_update(file_key, _("完成"))
            else:
                status_update(file_key, _("警告"))
                errors_found.append(result_msg)

        except FileNotFoundError:
            raise FileNotFoundError(
                _("错误: 'makeblastdb' 命令未找到。请确保 BLAST+ 已被正确安装并添加到了系统的 PATH 环境变量中。"))

        except Exception as e:
            error_msg = _("处理 {} 时发生未知异常: {}").format(file_key, e)
            logger.error(error_msg, exc_info=True)
            status_update(file_key, _("错误"))
            errors_found.append(error_msg)
        finally:
            completed_count += 1
            task_progress = 20 + int((completed_count / total_tasks) * 75)
            progress(task_progress, _("进度 ({}/{}) - {}").format(completed_count, total_tasks, file_key))


    if errors_found:
        summary_error = _("部分BLAST数据库在创建过程中失败或被取消:\n\n") + "\n".join(f"- {e}" for e in errors_found)
        raise RuntimeError(summary_error)

    logger.info(_("BLAST数据库预处理完成。成功创建 {}/{} 个数据库。").format(success_count, total_tasks))
    progress(100, _("预处理完成。"))
    return success_count == total_tasks


@pipeline_task(_("GFF查询"))
def run_gff_preprocessing(
        config: MainConfig,
        **kwargs
) -> bool:
    """
    扫描数据目录，为所有GFF文件预先创建gffutils数据库，以加速后续查询。
    """
    progress = kwargs.get('progress_callback')
    check_cancel = kwargs.get('check_cancel')

    logger.info("Starting GFF file pre-processing to create databases...")
    progress(0, "开始GFF文件预处理...")

    try:
        project_root = os.path.dirname(config.config_file_abs_path_)
        db_storage_dir = os.path.join(project_root, GFF3_DB_DIR)
        os.makedirs(db_storage_dir, exist_ok=True)

        genome_sources = get_genome_data_sources(config)

        files_to_process = []
        for assembly_id, genome_info in genome_sources.items():
            gff_path = get_local_downloaded_file_path(config, genome_info, 'gff3')
            if gff_path and os.path.exists(gff_path):
                files_to_process.append((assembly_id, gff_path, genome_info))

        if not files_to_process:
            logger.warning("No GFF files found to preprocess.")
            progress(100, "未找到GFF文件。")
            return True

        logger.info(f"Found {len(files_to_process)} GFF files to process.")
        total_files = len(files_to_process)

        for i, (assembly_id, gff_path, genome_info) in enumerate(files_to_process):
            if check_cancel(): return False

            progress_percent = int(((i + 1) / total_files) * 100)
            filename = os.path.basename(gff_path)
            progress(progress_percent, f"正在处理: {filename} ({i + 1}/{total_files})")

            # 遵循 gff_parser.py 的命名规则
            db_filename = f"{assembly_id}_genes.db"
            db_path = os.path.join(db_storage_dir, db_filename)

            try:
                logger.info(f"Creating GFF database for '{assembly_id}' -> '{db_filename}'")
                # 直接调用 gff_parser 中的函数来创建数据库
                create_gff_database(
                    gff_filepath=gff_path,
                    db_path=db_path,
                    force=True,  # 在预处理时，总是强制重建以确保最新
                    id_regex=getattr(genome_info, 'gene_id_regex', None)
                )
            except Exception as e:
                logger.error(f"Failed to create database for {assembly_id}. Reason: {e}")

        logger.info("GFF pre-processing completed successfully.")
        progress(100, "GFF预处理全部完成。")
        return True

    except Exception as e:
        logger.exception(f"A critical error occurred during GFF pre-processing: {e}")
        progress(100, "GFF预处理因错误终止。")
        raise e
