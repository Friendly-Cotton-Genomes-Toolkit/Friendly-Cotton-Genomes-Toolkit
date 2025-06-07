# cli.py
# (建议将此文件放在项目根目录，或者作为 cotton_toolkit/cli.py 并通过 python -m cotton_toolkit.cli 运行)

import argparse
import gettext
import logging  # 用于日志记录
import os
import sys
from typing import Dict, Any, Optional, Callable  # 确保导入
import webbrowser
import yaml
from pip._internal.utils.logging import setup_logging
from cotton_toolkit import HELP_URL,VERSION as APP_VERSION
from cotton_toolkit.tools_pipeline import run_ai_task, run_functional_annotation
from cotton_toolkit.core.convertXlsx2csv import convert_xlsx_to_single_csv

# --- 1. 定义应用名称 (用于i18n和logging) ---
APP_NAME_FOR_I18N = "cotton_toolkit"

# --- 2. 定义 _ 函数的初始占位符 (会被 setup_cli_i18n 覆盖) ---
_ = lambda text: text


# 动态添加项目根目录的父目录到sys.path，以允许从包外运行并导入包
# 这使得可以直接运行 D:/Python/cotton_tool/cli.py (如果cotton_toolkit目录在D:/Python/cotton_tool/下)
# 或者在打包后，这个逻辑就不那么重要了，因为包会被安装到site-packages
if __package__ is None or __package__ == '':  # 如果是作为顶层脚本运行
    # 获取 cli.py 所在的目录 (例如 D:/Python/cotton_tool)
    cli_dir = os.path.dirname(os.path.abspath(__file__))
    # 假设 cotton_toolkit 包是 cli.py 所在目录下的一个子目录
    # 如果不是，可能需要调整，或者期望 cotton_toolkit 已在PYTHONPATH中或已安装
    # 对于这里的示例，我们期望 cotton_toolkit 是一个与 cli.py 同级的目录（如果cli.py在根），
    # 或者 cli.py 在 cotton_toolkit 内，此时上面的 sys.path 修改更复杂。
    # 为简单起见，假设 cotton_toolkit 包可以被直接导入。
    # 如果 cli.py 在项目根，cotton_toolkit 是一个子目录，则不需要修改sys.path
    # 如果 cli.py 在 cotton_toolkit/cli.py，则需要 project_root = os.path.dirname(cli_dir)
    #     if project_root not in sys.path: sys.path.insert(0, project_root)
    pass

try:
    from cotton_toolkit.config.loader import load_config, get_genome_data_sources
    from cotton_toolkit.core.downloader import download_genome_data, decompress_gz_to_temp_file
    from cotton_toolkit.pipelines import integrate_bsa_with_hvg, run_homology_mapping_standalone, run_gff_gene_lookup_standalone, REASONING_COL_NAME # 新增导入
    from cotton_toolkit.core.gff_parser import DB_SUFFIX

    print(f"INFO (cli.py): Successfully imported real package modules.")
    REAL_MODULES_LOADED = True
except ImportError as e:
    print(f"WARNING (cli.py): Could not import real package modules due to: {e}.")
    print("             Using MOCK functions for CLI operation. Ensure package is installed or PYTHONPATH is set.")
    REAL_MODULES_LOADED = False

    # ... (原有MOCK函数定义保持不变，需要为新的 standalone 函数添加MOCK) ...
    # MOCK for run_homology_mapping_standalone
    def run_homology_mapping_standalone(config, source_gene_ids_override=None, source_assembly_id_override=None,
                                      target_assembly_id_override=None, s_to_b_homology_file_override=None,
                                      b_to_t_homology_file_override=None, output_csv_path=None,
                                      status_callback=None, progress_callback=None, task_done_callback=None):
        print(f"MOCK (CLI): run_homology_mapping_standalone called. Source: {source_gene_ids_override}")
        if status_callback: status_callback("Mock homology mapping started.")
        if progress_callback: progress_callback(100, "Mock homology mapping 100%")
        if status_callback: status_callback("Mock homology mapping finished.")
        if task_done_callback: task_done_callback(True)
        return True

    # MOCK for run_gff_gene_lookup_standalone
    def run_gff_gene_lookup_standalone(config, assembly_id_override=None, gene_ids_override=None, region_override=None,
                                     output_csv_path=None, status_callback=None, progress_callback=None, task_done_callback=None):
        print(f"MOCK (CLI): run_gff_gene_lookup_standalone called. Assembly: {assembly_id_override}, Genes: {gene_ids_override}, Region: {region_override}")
        if status_callback: status_callback("Mock GFF gene lookup started.")
        if progress_callback: progress_callback(100, "Mock GFF gene lookup 100%")
        if status_callback: status_callback("Mock GFF gene lookup finished.")
        if task_done_callback: task_done_callback(True)
        return True

    # --- 定义MOCK函数和变量以便脚本能作为示例独立运行 ---
    def load_config(path: str) -> Optional[Dict[str, Any]]:
        print(f"MOCK (CLI): Loading config from '{path}'")
        if not os.path.exists(path):
            print(f"MOCK ERROR: Config file '{path}' not found.")
            return None
        # 返回一个更完整的模拟配置
        return {
            "_config_file_abs_path_": os.path.abspath(path),
            "i18n_language": "en",
            "downloader": {
                "download_output_base_dir": "mock_cli_downloads",
                "genome_sources_file": "mock_genome_sources.yaml",
                "max_workers": 1, "force_download": False, "proxies": None,
                "genome_sources": {  # 直接内嵌，因为get_genome_data_sources也是mock
                    "MOCK_NBI_v1.1": {"gff3_url": "http://mock.url/NBI.gff3.gz",
                                      "homology_ath_url": "http://mock.url/NBI_hom.xlsx.gz",
                                      "species_name": "Mock_NBI_v1.1_sp"},
                    "MOCK_HAU_v2.0": {"gff3_url": "http://mock.url/HAU.gff3.gz",
                                      "homology_ath_url": "http://mock.url/HAU_hom.xlsx.gz",
                                      "species_name": "Mock_HAU_v2.0_sp"}
                }
            },
            "integration_pipeline": {
                "input_excel_path": "mock_cli_input.xlsx",
                "bsa_sheet_name": "BSA_Sheet_Mock", "hvg_sheet_name": "HVG_Sheet_Mock",
                "output_sheet_name": "CLI_Output_Sheet_Mock",
                "bsa_assembly_id": "MOCK_NBI_v1.1", "hvg_assembly_id": "MOCK_HAU_v2.0",
                "gff_files": {"MOCK_NBI_v1.1": "mock_gff_A.gff3", "MOCK_HAU_v2.0": "mock_gff_B.gff3.gz"},
                "homology_files": {"bsa_to_bridge_csv": "mock_hom_A_At.csv", "bridge_to_hvg_csv": "mock_hom_At_B.csv"},
                "bsa_columns": {"chr": "chr", "start": "region.start", "end": "region.end"},
                "hvg_columns": {"gene_id": "gene_id", "category": "hvg_category", "log2fc": "log2fc_WT_vs_Ms1"},
                "homology_columns": {"query": "Query", "match": "Match", "evalue": "Exp", "score": "Score",
                                     "pid": "PID"},
                "selection_criteria_source_to_bridge": {"top_n": 1},
                "selection_criteria_bridge_to_target": {"top_n": 1},
                "common_hvg_significant_log2fc_threshold": 1.0,
                "gff_db_storage_dir": "mock_gff_dbs"
            }
        }




    def get_genome_data_sources(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        print("MOCK (CLI): get_genome_data_sources called.")
        downloader_cfg = cfg.get('downloader', {})
        if 'genome_sources' in downloader_cfg: return downloader_cfg['genome_sources']
        # 模拟从文件加载 (如果需要更复杂的MOCK)
        return None


    def download_genome_data(config, genome_versions_to_download_override=None, force_download_override=None,
                             output_base_dir_override=None, status_callback=None, progress_callback=None):
        print(
            f"MOCK (CLI): download_genome_data called. Versions: {genome_versions_to_download_override}, Force: {force_download_override}")
        if status_callback: status_callback("Mock download started.")
        if progress_callback: progress_callback(50, "Mock download 50%")
        if progress_callback: progress_callback(100, "Mock download 100%")
        if status_callback: status_callback("Mock download finished.")


    def integrate_bsa_with_hvg(config, input_excel_path_override=None, output_sheet_name_override=None,
                               status_callback=None, progress_callback=None):
        print(
            f"MOCK (CLI): integrate_bsa_with_hvg called. Input: {input_excel_path_override}, Output Sheet: {output_sheet_name_override}")
        if status_callback: status_callback("Mock integration started.")
        if progress_callback: progress_callback(100, "Mock integration 100%")
        if status_callback: status_callback("Mock integration finished.")
        return True  # 模拟成功


    # Mocks for downloader's internal helpers (downloader.py本身应该有这些占位符，这里是为了cli.py能独立运行)
    def USER_CONVERTER_FUNC(xlsx, csv):
        print(f"MOCK_CONVERTER (CLI): {xlsx} to {csv}"); return True


    def decompress_gz_to_temp_file(gz, temp):
        print(f"MOCK_DECOMPRESS (CLI): {gz} to {temp}"); return True


    # Mocks for gff_parser and homology_mapper if pipelines.py can't import them
    # 这些仅当 integrate_bsa_with_hvg 的MOCK版本需要它们时才必要
    DB_SUFFIX = ".mock.db"
    REASONING_COL_NAME = 'Ms1_LoF_Support_Reasoning_Mock'


# --- 4. setup_cli_i18n 函数定义 ---
def setup_cli_i18n(language_code: str = 'zh-hans', app_name: str = APP_NAME_FOR_I18N):

    try:
        # 尝试定位 locales 目录
        # 假设 cli.py 在项目根目录，而包 cotton_toolkit 是一个子目录，locales 在 cotton_toolkit/locales
        script_dir = os.path.dirname(os.path.abspath(__file__))  # cli.py 所在的目录
        # 尝试1: cotton_toolkit/locales (如果 cli.py 在项目根, cotton_toolkit是子包)
        locale_dir = os.path.join(script_dir, "cotton_toolkit", "locales")
        if not os.path.isdir(locale_dir):
            # 尝试2: ../locales (如果 cli.py 在 cotton_toolkit/cli.py, locales在 cotton_toolkit/locales)
            # 此时 script_dir 是 cotton_toolkit/cli.py 的目录，即 cotton_toolkit/
            locale_dir = os.path.join(script_dir, 'locales')
            if not os.path.isdir(locale_dir):
                # 尝试3: 如果是作为已安装的包，gettext 或许能自己找到
                # 作为最后的手段，假设 locales 就在当前工作目录的一个子目录里 (不太可能)
                locale_dir = os.path.join(os.getcwd(), 'locales')

        # print(f"DEBUG (CLI i18n): Using locale_dir: {os.path.abspath(locale_dir)}, lang: {language_code}, app_name: {app_name}")

        lang_translation = gettext.translation(app_name, localedir=locale_dir, languages=[language_code], fallback=True)
        lang_translation.install()
        translator_func = lang_translation.gettext

        logging.info(f"CLI i18n: Language set to '{language_code}'.")  # 使用logging

    except FileNotFoundError:
        logging.warning(
            f"CLI i18n: Translation files for '{language_code}' (domain: {app_name}) not found. Using default strings (English or source). Searched in paths like '{locale_dir}'.")
        lang_translation = gettext.translation(app_name, localedir=locale_dir, languages=['zh-hans'], fallback=True)
        lang_translation.install()
        translator_func = lang_translation.gettext

    except Exception as e:
        logging.error(f"Error during CLI i18n setup: {e}", exc_info=True)
        lang_translation = gettext.translation(app_name, localedir=locale_dir, languages=['zh-hans'], fallback=True)
        lang_translation.install()
        translator_func = lang_translation.gettext

    return translator_func


# 新增：处理 homology_map 命令的函数
def handle_homology_map_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.homology_map")
    logger_cmd.info(_("执行同源映射命令..."))

    gene_ids_list = args.genes.split(',') if args.genes else None
    if gene_ids_list:
        gene_ids_list = [gid.strip() for gid in gene_ids_list if gid.strip()]

    run_homology_mapping_standalone(
        config=config_main,
        source_gene_ids_override=gene_ids_list,
        source_assembly_id_override=args.source_assembly,
        target_assembly_id_override=args.target_assembly,
        s_to_b_homology_file_override=args.homology_sb_file,
        b_to_t_homology_file_override=args.homology_bt_file,
        output_csv_path=args.output_csv,
        status_callback=lambda msg: logger_cmd.info(f"Mapping Status: {msg}"),
        progress_callback=lambda p, msg: logger_cmd.info(f"Mapping Progress [{p}%]: {msg}")
    )

# 新增：处理 gff_query 命令的函数
def handle_gff_query_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.gff_query")
    logger_cmd.info(_("执行GFF基因查询命令..."))

    gene_ids_list = args.genes.split(',') if args.genes else None
    if gene_ids_list:
        gene_ids_list = [gid.strip() for gid in gene_ids_list if gid.strip()]

    region_tuple = None
    if args.region:
        try:
            parts = args.region.split(':')
            chrom = parts[0]
            start_end = parts[1].split('-')
            start = int(start_end[0])
            end = int(start_end[1])
            region_tuple = (chrom, start, end)
        except Exception:
            logger_cmd.error(_("区域格式不正确。请使用 'chr:start-end' 格式。"))
            return

    if not gene_ids_list and not region_tuple:
        logger_cmd.error(_("必须提供基因ID列表 (--genes) 或染色体区域 (--region)。"))
        return

    run_gff_gene_lookup_standalone(
        config=config_main,
        assembly_id_override=args.assembly,
        gene_ids_override=gene_ids_list,
        region_override=region_tuple,
        output_csv_path=args.output_csv,
        status_callback=lambda msg: logger_cmd.info(f"GFF Query Status: {msg}"),
        progress_callback=lambda p, msg: logger_cmd.info(f"GFF Query Progress [{p}%]: {msg}")
    )


def handle_convert_cmd(args, config_main):
    logger_cmd = logging.getLogger(f"cotton_toolkit.cli.convert")
    logger_cmd.info(_("执行 XLSX 到 CSV 的转换..."))

    input_path = args.input
    output_path = args.output

    if not os.path.exists(input_path):
        logger_cmd.error(_("错误: 输入文件 '{}' 不存在。").format(input_path))
        return

    if not output_path:
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(os.path.dirname(input_path), f"{base_name}_merged.csv")
        logger_cmd.info(_("未指定输出路径，将自动保存到: {}").format(output_path))

    logger_cmd.info(_("此工具会将所有工作表合并到一个CSV文件中。"))

    success = convert_xlsx_to_single_csv(input_path, output_path)

    if success:
        logger_cmd.info(_("转换成功！"))
    else:
        logger_cmd.error(_("转换失败，请检查文件格式或错误日志。"))

# --- 6. 定义 handle_download_cmd 和 handle_integrate_cmd 函数 ---
def handle_download_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.download")  # 子logger
    logger_cmd.info(_("执行下载命令..."))
    if not config_main or 'downloader' not in config_main:
        logger_cmd.error(_("错误: 配置文件中缺少 'downloader' 配置部分。"))
        return

    # 确保 config_main['downloader']['genome_sources'] 被正确填充
    downloader_cfg = config_main['downloader']
    if 'genome_sources_file' in downloader_cfg and 'genome_sources' not in downloader_cfg:
        gs_data = get_genome_data_sources(config_main)  # 使用已导入的config_loader函数
        if gs_data:
            downloader_cfg['genome_sources'] = gs_data
        else:
            logger_cmd.error(_("错误: 无法从配置文件或指定的genome_sources_file中加载基因组源数据。"))
            return
    elif 'genome_sources' not in downloader_cfg:
        logger_cmd.error(_("错误: 下载器配置中缺少 'genome_sources'。"))
        return

    download_genome_data(  # 调用已导入的downloader函数
        config_main,
        genome_versions_to_download_override=args.genomes,
        force_download_override=args.force_set,  # args.force_set 会是 True, False, 或 None
        output_base_dir_override=args.output_dir
    )


def handle_integrate_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.integrate")  # 子logger
    logger_cmd.info(_("执行整合分析命令..."))
    if not config_main or 'integration_pipeline' not in config_main:
        logger_cmd.error(_("错误: 配置文件中缺少 'integration_pipeline' 配置部分。"))
        return

    integrate_bsa_with_hvg(  # 调用已导入的pipelines函数
        config_main,
        input_excel_path_override=args.input_excel,
        output_sheet_name_override=args.output_sheet
        # status_callback 和 progress_callback 可以由CLI提供简单的打印函数
        # status_callback=lambda msg: logger_cmd.info(f"Pipeline Status: {msg}"),
        # progress_callback=lambda p, msg: logger_cmd.info(f"Pipeline Progress [{p}%]: {msg}")
    )

# --- 新增：生成“关于”信息的通用函数 ---
def get_about_text(translator: Callable[[str], str]) -> str:
    """
    生成格式化、可翻译的“关于”信息文本。

    Args:
        translator: 翻译函数 (例如 gettext.gettext)。
    """
    _ = translator  # 在函数内部使用传入的翻译器
    lines = [
        "--------------------------------------------------",
        f"{_('应用名称')}: {_('棉花基因组分析工具包')}",
        f"{_('版本')}: {APP_VERSION}",
        f"{_('作者')}: PureAmaya",
        f"{_('开源许可')}: Apache License 2.0",
        f"{_('人工智能')}: 本工具的开发依靠 Gemini 2.5 Pro (preview) 完成",
        "--------------------------------------------------",
        _("此工具包旨在整合BSA定位结果与HVG基因数据，"),
        _("进行棉花功能缺失基因的筛选与优先级排序。"),
        f"--------------------------------------------------",
        f"{_('帮助文档')}: {HELP_URL}"
    ]
    return "\n".join(lines)

# --- 新增：处理 about 命令的函数 ---
def handle_about_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    """处理 'about' 子命令的函数。"""
    # cli_main_entry 中已经设置好了 _ 函数，所以这里可以直接使用
    print(get_about_text(translator=_))

# --- 新增：处理 help 命令的函数 ---
def handle_help_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.help")
    logger_cmd.info(_("正在浏览器中打开在线帮助文档... URL: {}").format(HELP_URL))
    try:
        webbrowser.open(HELP_URL)
    except Exception as e:
        logger_cmd.error(_("无法自动打开帮助链接。请手动复制此链接到浏览器: {} \n错误: {}").format(HELP_URL, e))



# 处理 annotate 命令的函数
def handle_annotate_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    logger_cmd = logging.getLogger(f"cotton_toolkit.cli.annotate")
    logger_cmd.info(_("执行功能注释命令..."))
    output_dir = args.output_dir or os.path.join(os.path.dirname(args.input), "annotation_results")
    run_functional_annotation(
        config=config_main, input_file=args.input, output_dir=output_dir,
        annotation_types=args.types, gene_column_name=args.gene_column,
        status_callback=logger_cmd.info
    )


# 处理 ai 命令的函数
def handle_ai_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    logger_cmd = logging.getLogger(f"cotton_toolkit.cli.ai")
    logger_cmd.info(_("执行 AI 助手命令..."))
    if args.task_type == 'analyze' and not args.prompt:
        logger_cmd.error(_("错误: 'analyze' 任务需要使用 --prompt 参数提供一个提示模板。")); return
    output_dir = args.output_dir or os.path.join(os.path.dirname(args.input), "ai_results")
    run_ai_task(
        config=config_main, input_file=args.input, output_dir=output_dir,
        source_column=args.source_column, new_column=args.new_column,
        task_type=args.task_type, custom_prompt_template=args.prompt,
        status_callback=logger_cmd.info
    )



# --- 7. 定义 cli_main_entry 函数 ---
def cli_main_entry():
    """CLI主入口函数"""
    # 预解析语言参数，以便尽早设置i18n (如果需要argparse的help也被翻译)
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--lang", type=str, choices=['zh-hans', 'zh-hant', 'en', 'ja'])
    pre_args, _remaining_argv = pre_parser.parse_known_args()

    # 优先命令行 --lang, 其次尝试从一个非常临时的config加载（如果存在），最后默认'en'
    # 这一步的 _ 还是原始的 lambda text: text
    initial_lang = pre_args.lang if pre_args.lang else 'zh-hans'
    temp_config_for_lang_path = "config.yml"  # 假设一个默认名
    if os.path.exists(temp_config_for_lang_path) and not pre_args.lang:
        try:
            with open(temp_config_for_lang_path, 'r', encoding='utf-8') as f_cfg_temp:
                temp_cfg = yaml.safe_load(f_cfg_temp)
                if isinstance(temp_cfg, dict) and 'i18n_language' in temp_cfg:
                    initial_lang = temp_cfg['i18n_language']
        except:
            pass  # 忽略错误，使用默认语言

    setup_cli_i18n(language_code=initial_lang, app_name=APP_NAME_FOR_I18N)  # 设置 _ 函数

    # 现在 _() 可以用于翻译 argparse 的描述和帮助文本
    parser = argparse.ArgumentParser(
        description=_("棉花基因组分析工具包 (Cotton Toolkit)"),
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--config", type=str, default="config.yaml", help=_("配置文件路径 (YAML)。默认: %(default)s"))
    parser.add_argument("--lang", type=str, choices=['en', 'zh_CN'], help=_("界面语言 (en/zh_CN)。覆盖配置。"))
    parser.add_argument("--loglevel", type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        default="INFO", help=_("控制台日志级别。默认: %(default)s"))
    parser.add_argument("--logfile", type=str, default="cotton_toolkit.log",
                        help=_("日志文件路径。设为 'NONE' 则不记录到文件。默认: %(default)s"))

    subparsers = parser.add_subparsers(dest="command", title=_("可用命令"), help=_("选择子命令执行"))
    subparsers.required = True

    # --- 【新增】XLSX转CSV子命令 ---
    parser_convert = subparsers.add_parser("convert", help=_("将一个XLSX文件的所有工作表合并成一个CSV文件。"))
    parser_convert.add_argument("-i", "--input", required=True, help=_("要转换的源 .xlsx 文件路径。"))
    parser_convert.add_argument("-o", "--output", help=_("输出 .csv 文件的路径 (可选)。"))
    parser_convert.set_defaults(func=handle_convert_cmd)

    # --- AI 助手子命令 ---
    parser_ai = subparsers.add_parser("ai", help=_("使用AI批量处理表格数据。"))
    parser_ai.add_argument("-i", "--input", required=True, help=_("要处理的输入CSV文件。"))
    parser_ai.add_argument("-o", "--output-dir",
                           help=_("存放结果的输出目录 (默认为输入文件同级目录下的 'ai_results')。"))
    parser_ai.add_argument("--source-column", required=True, help=_("要处理的源列名。"))
    parser_ai.add_argument("--new-column", required=True, help=_("存放结果的新列名。"))
    parser_ai.add_argument("--task-type", required=True, choices=['translate', 'analyze'], help=_("要执行的任务类型。"))
    parser_ai.add_argument("--prompt", help=_("执行'analyze'任务时使用的自定义提示模板 (必须包含'{text}')。"))
    parser_ai.set_defaults(func=handle_ai_cmd)

    # --- 功能注释子命令 ---
    parser_annotate = subparsers.add_parser("annotate", help=_("使用本地数据库为基因列表添加功能注释。"))
    parser_annotate.add_argument("-i", "--input", required=True, help=_("包含基因列表的输入文件 (Excel/CSV)。"))
    parser_annotate.add_argument("-o", "--output-dir",
                                 help=_("存放注释结果的输出目录 (默认为输入文件同级目录下的 'annotation_results')。"))
    parser_annotate.add_argument("-t", "--types", nargs='+', required=True,
                                 choices=['go', 'ipr', 'kegg_orthologs', 'kegg_pathways'],
                                 help=_("要执行的注释类型 (可多选)。"))
    parser_annotate.add_argument("-g", "--gene-column", default="gene",
                                 help=_("输入文件中基因ID所在列的名称 (默认: 'gene')。"))
    parser_annotate.set_defaults(func=handle_annotate_cmd)

    # 下载器子命令
    parser_download = subparsers.add_parser("download", help=_("下载基因组数据 (GFF3, 同源文件)。"))
    parser_download.add_argument("--genomes", nargs="+", metavar="GENOME_ID", help=_("要下载的基因组版本ID列表。"))
    parser_download.add_argument("--output_dir", type=str, help=_("覆盖下载输出目录。"))
    group_force = parser_download.add_mutually_exclusive_group()
    group_force.add_argument("--force", action="store_true", dest="force_set", help=_("强制重新下载。"))
    group_force.add_argument("--no-force", action="store_false", dest="force_set", help=_("不强制重新下载 (默认)。"))
    parser_download.set_defaults(func=handle_download_cmd, force_set=None)

    # 整合分析子命令
    parser_integrate = subparsers.add_parser("integrate", help=_("整合BSA结果与HVG数据。"))
    parser_integrate.add_argument("--input_excel", type=str, help=_("覆盖输入Excel文件路径。"))
    parser_integrate.add_argument("--output_sheet", type=str, help=_("覆盖输出工作表名称。"))
    parser_integrate.set_defaults(func=handle_integrate_cmd)

    # 新增：同源映射子命令
    parser_homology_map = subparsers.add_parser("homology_map", help=_("独立执行基因组同源映射。"))
    parser_homology_map.add_argument("--genes", type=str, required=True,
                                     help=_("要映射的源基因ID，多个用逗号分隔 (例如: GeneA1,GeneA2)。"))
    parser_homology_map.add_argument("--source_assembly", type=str, help=_("源基因组版本ID (覆盖配置文件)。"))
    parser_homology_map.add_argument("--target_assembly", type=str, help=_("目标基因组版本ID (覆盖配置文件)。"))
    parser_homology_map.add_argument("--homology_sb_file", type=str,
                                     help=_("源到桥梁的同源CSV文件路径 (覆盖配置文件)。"))
    parser_homology_map.add_argument("--homology_bt_file", type=str,
                                     help=_("桥梁到目标的同源CSV文件路径 (覆盖配置文件)。"))
    parser_homology_map.add_argument("--output_csv", type=str, help=_("结果输出CSV文件路径。"))
    parser_homology_map.set_defaults(func=handle_homology_map_cmd)

    # 新增：GFF基因查询子命令
    parser_gff_query = subparsers.add_parser("gff_query", help=_("独立查询GFF文件中的基因信息。"))
    parser_gff_query.add_argument("--assembly", type=str, help=_("要查询的基因组版本ID (覆盖配置文件)。"))
    parser_gff_query.add_argument("--genes", type=str, help=_("要查询的基因ID，多个用逗号分隔 (例如: GeneB1,GeneB2)。"))
    parser_gff_query.add_argument("--region", type=str, help=_("要查询的染色体区域 (例如: chr1:1000-5000)。"))
    parser_gff_query.add_argument("--output_csv", type=str, help=_("结果输出CSV文件路径。"))
    parser_gff_query.set_defaults(func=handle_gff_query_cmd)

    # 新增：帮助子命令
    parser_help = subparsers.add_parser("web_help", help=_("在浏览器中打开在线帮助文档。"))
    parser_help.set_defaults(func=handle_help_cmd)

    # 新增：关于子命令
    parser_about = subparsers.add_parser("about", help=_("显示关于本应用的信息。"))
    parser_about.set_defaults(func=handle_about_cmd)

    args = parser.parse_args()  # sys.argv[1:] (如果之前用了 pre_parser, 这里用 _remaining_argv 可能更合适，但通常argparse能处理)

    # 1. 加载最终配置
    config = load_config(args.config)
    if not config: sys.exit(1)
    if '_config_file_abs_path_' not in config: config['_config_file_abs_path_'] = os.path.abspath(args.config)

    # 2. 最终设置国际化 (如果 --lang 在命令行中提供了，它优先)
    final_language = args.lang if args.lang else config.get('i18n_language', 'en')
    final_app_domain = config.get('i18n_app_domain', APP_NAME_FOR_I18N)  # 允许配置覆盖域名
    if _("test") == "test" or args.lang:  # 如果 _ 还是透传或者命令行指定了新语言，重新设置
        setup_cli_i18n(language_code=final_language, app_name=final_app_domain)

    # 3. 设置日志系统
    logfile_to_use = args.logfile if str(args.logfile).upper() != 'NONE' else None
    setup_logging(loglevel_console_str=args.loglevel, log_file=logfile_to_use)

    logger_main_cli = logging.getLogger(APP_NAME_FOR_I18N)  # 获取主logger
    logger_main_cli.info(_("CLI启动。配置来自 '{}'，语言: '{}'，控制台日志级别: '{}'").format(
        args.config, final_language, args.loglevel))

    # 4. 执行命令
    if hasattr(args, 'func'):
        # 再次处理 download 命令的 force_set，确保 None/True/False 正确传递
        if args.command == "download":
            if hasattr(args, 'force_set_true') and args.force_set_true:  # --force
                args.force_set = True
            elif hasattr(args, 'force_set_false') and args.force_set_false is False:  # --no-force
                args.force_set = False
            # else: args.force_set 保持为 None, download_genome_data 内部会用配置的默认值
        try:
            args.func(args, config)
        except Exception as e_cmd:
            logger_main_cli.critical(_("执行命令 '{}' 时发生未捕获的严重错误: {}").format(args.command, e_cmd),
                                     exc_info=True)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


# --- 8. 主程序入口 ---
if __name__ == '__main__':
    # 动态修改sys.path以允许从项目根目录运行 `python cotton_toolkit/cli.py` 并正确导入同级模块
    # (这段代码在之前的回复中讨论过，如果需要，请保留或调整)
    if (__package__ is None or __package__ == '') and not REAL_MODULES_LOADED:
        # 仅在真实模块导入失败（即 MOCK 被使用）且作为脚本运行时尝试调整路径
        # 这表明可能需要 python -m cotton_toolkit.cli 来运行
        print("Info (cli.py __main__): Running as script and real modules might not have loaded due to path issues.")
        print("Consider running as 'python -m cotton_toolkit.cli' from the project root if imports fail.")

    cli_main_entry()