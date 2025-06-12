import argparse
import gettext
import logging
import os
import sys
from typing import Dict, Any, Optional

from cotton_toolkit.config.models import MainConfig
from . import HELP_URL, VERSION as APP_VERSION
from .core.ai_wrapper import AIWrapper
from .tools_pipeline import run_ai_task, run_functional_annotation
from .core.convertXlsx2csv import convert_xlsx_to_single_csv
from .config.loader import load_config, generate_default_config_files
from .core.downloader import download_genome_data
from .pipelines import run_locus_conversion_standalone ,integrate_bsa_with_hvg, run_gff_gene_lookup_standalone

# --- 定义应用名称和翻译函数占位符 ---
APP_NAME_FOR_I18N = "cotton_toolkit"
_ = lambda text: text


def setup_cli_i18n(language_code: str = 'zh-hans', app_name: str = APP_NAME_FOR_I18N):
    """设置命令行界面(CLI)的国际化(i18n)支持。"""
    try:
        locales_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locales')
        if not os.path.isdir(locales_dir):
            # 如果在打包的 .exe 中运行，locales 目录可能在 sys._MEIPASS
            if hasattr(sys, '_MEIPASS'):
                locales_dir = os.path.join(sys._MEIPASS, 'cotton_toolkit', 'locales')

        lang_translation = gettext.translation(
            app_name,
            localedir=locales_dir,
            languages=[language_code],
            fallback=True
        )
        lang_translation.install()
        return lang_translation.gettext
    except FileNotFoundError:
        return lambda text: text
    except Exception as e:
        print(f"Warning: Could not set up language translation for '{language_code}'. Reason: {e}", file=sys.stderr)
        return lambda text: text


def get_about_text() -> str:
    """生成“关于”文本，包含版本号和帮助链接。"""
    return _("棉花基因组分析工具包 (Cotton Toolkit)\n版本: {}\n更多帮助请访问: {}").format(APP_VERSION, HELP_URL)


def handle_download_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    """处理 'download' 子命令的函数。"""
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.download")
    logger_cmd.info(_("开始下载流程..."))

    versions_list = args.versions.split(',') if args.versions else None

    # 从 MainConfig 对象更新
    if hasattr(config_main, 'downloader'):
        if args.force is not None:
            config_main.downloader.force_download = args.force
        if args.proxy is not None and not args.proxy:
            config_main.downloader.proxies = None

    success = download_genome_data(
        config=config_main,
        genome_versions_to_download_override=versions_list,
        status_callback=logger_cmd.info,
        progress_callback=lambda p, msg: logger_cmd.info(f"Progress {p}%: {msg}")
    )
    if success:
        logger_cmd.info(_("下载成功完成。"))
    else:
        logger_cmd.error(_("下载失败。"))
        sys.exit(1)


def handle_integrate_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    """处理 'integrate' (联合分析) 子命令的函数。"""
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.integrate")
    logger_cmd.info(_("开始整合分析流程..."))

    excel_path_override = args.excel_path if args.excel_path else config_main.integration_pipeline.input_excel_path

    def cli_progress_callback(percentage: int, message: str):
        sys.stdout.write(f"\r[{'#' * (percentage // 5):<20}] {percentage}%: {message.strip()}")
        sys.stdout.flush()
        if percentage == 100:
            sys.stdout.write('\n')

    success = integrate_bsa_with_hvg(
        config=config_main,
        input_excel_path_override=excel_path_override,
        status_callback=logger_cmd.info,
        progress_callback=cli_progress_callback,
    )
    if success:
        logger_cmd.info(_("整合分析流程成功完成。"))
    else:
        logger_cmd.error(_("整合分析流程执行失败。"))
        sys.exit(1)


def handle_homology_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    """处理 'homology' 子命令的函数。"""
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.homology")
    logger_cmd.info(_("开始同源映射..."))

    gene_list = [g.strip() for g in args.genes.split(',')]

    run_homology_mapping_standalone(
        config=config_main,
        source_gene_ids_override=gene_list,
        source_assembly_id_override=args.source_asm,
        target_assembly_id_override=args.target_asm,
        output_csv_path=args.output_csv,
        status_callback=logger_cmd.info,
        progress_callback=lambda p, msg: logger_cmd.info(f"Progress {p}%: {msg}"),
        task_done_callback=lambda s: logger_cmd.info(f"Task finished with success: {s}")
    )


def handle_gff_query_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    """处理 'gff-query' 子命令的函数。"""
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.gff_query")
    if not args.genes and not args.region:
        logger_cmd.error(_("错误：必须提供 --genes 或 --region 参数。"))
        sys.exit(1)

    gene_list = [g.strip() for g in args.genes.split(',')] if args.genes else None
    region_tuple = None
    if args.region:
        try:
            chrom, pos = args.region.split(':')
            start, end = map(int, pos.split('-'))
            region_tuple = (chrom, start, end)
        except ValueError:
            logger_cmd.error(_("错误：区域格式无效。请使用 'chr:start-end' 格式。"))
            sys.exit(1)

    logger_cmd.info(_("开始GFF基因查询..."))
    run_gff_gene_lookup_standalone(
        config=config_main,
        assembly_id_override=args.assembly_id,
        gene_ids_override=gene_list,
        region_override=region_tuple,
        output_csv_path=args.output_csv,
        status_callback=logger_cmd.info,
        progress_callback=lambda p, msg: logger_cmd.info(f"Progress {p}%: {msg}"),
        task_done_callback=lambda s: logger_cmd.info(f"Task finished with success: {s}")
    )


def handle_annotate_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    """处理 'annotate' 子命令的函数。"""
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.annotate")
    anno_types = [t.strip() for t in args.types.split(',')]
    logger_cmd.info(_("开始功能注释，类型: {}").format(', '.join(anno_types)))
    run_functional_annotation(
        config=config_main,
        input_file=args.input_file,
        output_dir=args.output_dir,
        annotation_types=anno_types,
        gene_column_name=args.gene_column,
        status_callback=logger_cmd.info
    )
    logger_cmd.info(_("注释完成。"))

def handle_locus_convert_cmd(args: argparse.Namespace, config_main: MainConfig): # 使用 MainConfig 类型提示
    """处理 'locus-convert' 子命令的函数。"""
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.locus_convert")
    logger_cmd.info(_("开始位点（区域）基因组转换..."))

    if not all([args.source_assembly, args.target_assembly, args.region]):
        logger_cmd.error(_("错误：必须提供 --source-assembly, --target-assembly 和 --region 参数。"))
        sys.exit(1)

    region_tuple = None
    try:
        parts = args.region.split(':')
        if len(parts) == 2 and '-' in parts[1]:
            chrom = parts[0]
            start, end = map(int, parts[1].split('-'))
            region_tuple = (chrom, start, end)
        else:
            raise ValueError("Format error")
    except Exception:
        logger_cmd.error(_("错误：区域格式无效。请使用 'chr:start-end' 格式。"))
        sys.exit(1)

    success = run_locus_conversion_standalone(
        config=config_main,
        source_assembly_id_override=args.source_assembly,
        target_assembly_id_override=args.target_assembly,
        region_override=region_tuple,
        output_csv_path=args.output_csv,
        status_callback=logger_cmd.info,
        progress_callback=lambda p, msg: logger_cmd.info(f"Progress {p}%: {msg}"),
        task_done_callback=lambda s: logger_cmd.info(f"Task finished with success: {s}")
    )
    if success:
        logger_cmd.info(_("位点转换流程成功完成。"))
    else:
        logger_cmd.error(_("位点转换流程执行失败。"))
        sys.exit(1)

def handle_ai_task_cmd(args: argparse.Namespace, config_main: Dict[str, Any]):
    """处理 'ai-task' 子命令的函数。"""
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.ai_task")
    logger_cmd.info(_("开始AI任务 '{}'...").format(args.task_type))
    run_ai_task(
        config=config_main,
        input_file=args.input_file,
        output_dir=args.output_dir,
        source_column=args.source_column,
        new_column=args.new_column,
        task_type=args.task_type,
        custom_prompt_template=args.prompt,
        status_callback=logger_cmd.info
    )
    logger_cmd.info(_("AI任务完成。"))


def handle_convert_xlsx_cmd(args: argparse.Namespace, config_main: Optional[Dict[str, Any]]):
    """处理 'convert-xlsx-to-csv' 子命令的函数。"""
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.convert")
    logger_cmd.info(_("正在转换 '{}'...").format(args.input_path))
    success, result_path = convert_xlsx_to_single_csv(args.input_path, args.output_path)
    if success:
        logger_cmd.info(_("成功转换并保存至 '{}'。").format(result_path))
    else:
        logger_cmd.error(_("转换时出错: {}").format(result_path))
        sys.exit(1)


def handle_generate_config_cmd(args: argparse.Namespace, config_main: Optional[Dict[str, Any]]):
    """处理 'generate-config' 子命令的函数。"""
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.generate_config")
    logger_cmd.info(_("正在于 '{}' 生成默认配置文件...").format(args.output_dir))
    success, main_path, gs_path = generate_default_config_files(args.output_dir, overwrite=args.overwrite)
    if success:
        logger_cmd.info(_("默认文件生成成功:\n- {}\n- {}").format(main_path, gs_path))
    else:
        logger_cmd.error(_("生成部分或全部配置文件失败。请检查现有文件或权限。"))
        sys.exit(1)


def handle_get_ai_models_cmd(args: argparse.Namespace, config_main: Optional[Dict[str, Any]]):
    """处理 'get-ai-models' 子命令的函数。"""
    logger_cmd = logging.getLogger(f"{APP_NAME_FOR_I18N}.cli.get_ai_models")
    logger_cmd.info(_("正在为服务商 '{}' 获取模型列表...").format(args.provider))
    try:
        models = AIWrapper.get_models(
            provider=args.provider,
            api_key=args.api_key,
            base_url=args.base_url,
        )
        if models:
            for model in models:
                print(model)
        else:
            logger_cmd.warning(_("未找到任何模型。"))
    except Exception as e:
        logger_cmd.critical(_("获取模型列表时发生严重错误: {}").format(e), exc_info=True)
        sys.exit(1)


def cli_main_entry():
    """CLI主入口函数"""
    # 预解析语言参数，以便帮助信息可以被翻译
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--lang", default=os.getenv("FCGT_LANG", "zh-hans"),
                            help="Language setting (e.g., en, zh-hans).")
    pre_args, remaining_argv = pre_parser.parse_known_args()
    global _
    _ = setup_cli_i18n(language_code=pre_args.lang, app_name=APP_NAME_FOR_I18N)

    # 主解析器
    parser = argparse.ArgumentParser(
        description=_("棉花基因组分析工具包 (Cotton Toolkit)"),
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--version', action='version', version=f'%(prog)s {APP_VERSION}',
                        help=_("显示程序版本号并退出。"))
    parser.add_argument('--about', action='version', version=get_about_text(), help=_("显示关于本软件的信息。"))
    parser.add_argument("--config", type=str, default="config.yml", help=_("配置文件路径 (YAML)。"))
    parser.add_argument("--lang", default=os.getenv("FCGT_LANG", "zh-hans"), help=_("语言设置 (例如: en, zh-hans)。"))
    parser.add_argument("--verbose", "-v", action="store_true", help=_("启用详细日志输出。"))

    subparsers = parser.add_subparsers(dest="command", title=_("可用命令"), help=_("选择子命令执行"))
    subparsers.required = True

    # 下载命令
    parser_download = subparsers.add_parser("download", help=_("下载基因组数据。"))
    parser_download.add_argument('--versions', default=None, help=_("要下载的基因组版本列表，以逗号分隔。默认为全部。"))
    parser_download.add_argument('--force', action='store_true', default=None, help=_("即使文件已存在也强制重新下载。"))
    parser_download.add_argument('--proxy', action='store_true', default=None, help=_("使用配置文件中定义的代理。"))
    parser_download.set_defaults(func=handle_download_cmd)

    # 联合分析命令
    parser_integrate = subparsers.add_parser("integrate", help=_("联合分析BSA与HVG数据。"))
    parser_integrate.add_argument('--excel-path', default=None, help=_("覆盖配置文件中的输入Excel文件路径。"))
    parser_integrate.set_defaults(func=handle_integrate_cmd)

    # 同源映射命令
    parser_homology = subparsers.add_parser("homology", help=_("对基因列表进行同源映射。"))
    parser_homology.add_argument('--genes', required=True, help=_("源基因ID列表，以逗号分隔。"))
    parser_homology.add_argument('--source-asm', default=None, help=_("覆盖源基因组版本ID。"))
    parser_homology.add_argument('--target-asm', default=None, help=_("覆盖目标基因组版本ID。"))
    parser_homology.add_argument('--output-csv', default=None, help=_("保存输出CSV文件的路径。"))
    parser_homology.set_defaults(func=handle_homology_cmd)

    # GFF查询命令
    parser_gff_query = subparsers.add_parser("gff-query", help=_("从GFF文件查询基因信息。"))
    parser_gff_query.add_argument('--assembly-id', required=True, help=_("要查询的基因组版本ID。"))
    parser_gff_query.add_argument('--genes', default=None, help=_("基因ID列表，以逗号分隔。"))
    parser_gff_query.add_argument('--region', default=None, help=_("区域字符串，例如: 'chr1:1000-5000'。"))
    parser_gff_query.add_argument('--output-csv', default=None, help=_("保存输出CSV文件的路径。"))
    parser_gff_query.set_defaults(func=handle_gff_query_cmd)

    # 功能注释命令
    parser_annotate = subparsers.add_parser("annotate", help=_("对基因列表进行功能注释。"))
    parser_annotate.add_argument('--input-file', required=True, type=str, help=_("包含基因ID的输入文件 (Excel或CSV)。"))
    parser_annotate.add_argument('--output-dir', default='annotation_results', help=_("保存注释结果的目录。"))
    parser_annotate.add_argument('--types', required=True,
                                 help=_("注释类型列表，以逗号分隔 (go, ipr, kegg_orthologs, kegg_pathways)。"))
    parser_annotate.add_argument('--gene-column', default='gene', help=_("包含基因ID的列名。"))
    parser_annotate.set_defaults(func=handle_annotate_cmd)

    # AI任务命令
    parser_ai_task = subparsers.add_parser("ai-task", help=_("在CSV文件上运行批量AI任务。"))
    parser_ai_task.add_argument('--input-file', required=True, type=str, help=_("输入的CSV文件。"))
    parser_ai_task.add_argument('--output-dir', default='ai_results', help=_("保存AI任务结果的目录。"))
    parser_ai_task.add_argument('--source-column', required=True, help=_("要处理的源列名。"))
    parser_ai_task.add_argument('--new-column', required=True, help=_("要创建的新列名。"))
    parser_ai_task.add_argument('--task-type', choices=['translate', 'analyze'], default='translate',
                                help=_("要执行的AI任务类型。"))
    parser_ai_task.add_argument('--prompt', default=None, help=_("自定义提示词模板。必须包含 {text}。"))
    parser_ai_task.set_defaults(func=handle_ai_task_cmd)

    # locus-convert 命令（位点转换）
    parser_locus_convert = subparsers.add_parser("locus-convert",
                                                 help=_("将指定基因组的位点（区域）转换为另一个基因组的相应位点。"))
    parser_locus_convert.add_argument('--source-assembly', required=True, help=_("源基因组版本ID。"))
    parser_locus_convert.add_argument('--target-assembly', required=True, help=_("目标基因组版本ID。"))
    parser_locus_convert.add_argument('--region', required=True, help=_("要转换的区域，格式例如: 'chr1:1000-5000'。"))
    parser_locus_convert.add_argument('--output-csv', default=None, help=_("保存输出CSV文件的路径。"))
    parser_locus_convert.set_defaults(func=handle_locus_convert_cmd)


    # XLSX转换命令
    parser_convert = subparsers.add_parser("convert-xlsx-to-csv", help=_("将XLSX文件的所有工作表转换为单个CSV文件。"))
    parser_convert.add_argument('--input-path', required=True, type=str, help=_("输入的XLSX文件路径。"))
    parser_convert.add_argument('--output-path', default=None, help=_("输出的CSV文件路径。如果未提供，将自动生成。"))
    parser_convert.set_defaults(func=handle_convert_xlsx_cmd)

    # 生成配置命令
    parser_gen_config = subparsers.add_parser("generate-config",
                                              help=_("生成默认的 config.yml 和 genome_sources_list.yml 文件。"))
    parser_gen_config.add_argument('--output-dir', default='.', help=_("生成默认配置文件的目录。"))
    parser_gen_config.add_argument('--overwrite', action='store_true', help=_("覆盖已存在的配置文件。"))
    parser_gen_config.set_defaults(func=handle_generate_config_cmd)

    # 获取AI模型命令
    parser_get_models = subparsers.add_parser("get-ai-models", help=_("获取指定AI服务商的模型列表。"))
    parser_get_models.add_argument("--provider", required=True, help=_("AI服务商的标识 (例如: google, openai)。"))
    parser_get_models.add_argument("--api-key", required=True, help=_("该服务商的API Key。"))
    parser_get_models.add_argument("--base-url", default=None, help=_("可选的自定义API地址。"))
    parser_get_models.set_defaults(func=handle_get_ai_models_cmd)

    # --- 解析参数并执行命令 ---
    args = parser.parse_args(remaining_argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        stream=sys.stdout)

    # 加载配置（对于不需要配置的命令则跳过）
    config = None
    if args.command not in ['generate-config', 'get-ai-models', 'convert-xlsx-to-csv']:
        if not os.path.exists(args.config):
            print(_("错误：配置文件 '{}' 未找到。").format(args.config), file=sys.stderr)
            sys.exit(1)
        config = load_config(args.config)
        if not config:
            print(_("错误：未能加载配置文件 '{}'。").format(args.config), file=sys.stderr)
            sys.exit(1)

    if hasattr(args, 'func'):
        try:
            args.func(args, config)
        except Exception as e_cmd:
            logging.getLogger(APP_NAME_FOR_I18N).critical(
                _("执行命令 '{}' 时发生未捕获的错误: {}").format(args.command, e_cmd),
                exc_info=True
            )
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    cli_main_entry()