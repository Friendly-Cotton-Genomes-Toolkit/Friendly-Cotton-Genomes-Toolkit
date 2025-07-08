# cotton_toolkit/cli.py
import builtins
import logging
import os
import signal
import sys
import textwrap
import threading
from typing import Callable

import pandas as pd
import click

from . import VERSION, PUBLISH_URL
from .pipelines import (
    run_download_pipeline,
    run_homology_mapping,
    run_ai_task, run_gff_lookup, run_functional_annotation, run_preprocess_annotation_files, run_enrichment_pipeline,
    run_locus_conversion, run_xlsx_to_csv,
)
from .config.loader import load_config, generate_default_config_files, MainConfig, get_genome_data_sources, \
    check_annotation_file_status
from .core.ai_wrapper import AIWrapper
from .utils.gene_utils import parse_region_string
from .utils.localization import setup_localization
from .utils.logger import setup_global_logger
from ui.utils.gui_helpers import identify_genome_from_gene_ids


cancel_event = threading.Event()
logger = logging.getLogger("cotton_toolkit.gui")


def get_config(config_path: str) -> MainConfig:
    """Helper to load config and handle CLI-specific errors."""
    try:
        config_obj = load_config(config_path)
        if not config_obj:
            click.echo(_("错误: 无法从 '{}' 加载配置。文件可能为空或格式不正确。").format(config_path), err=True)
            raise click.Abort()
        return config_obj
    except FileNotFoundError:
        click.echo(_("错误: 配置文件 '{}' 未找到。请检查路径或运行 'init' 命令。").format(config_path), err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(_("错误: 加载配置文件时发生意外错误: {}").format(e), err=True)
        raise click.Abort()


def signal_handler(sig, frame):
    """捕获到 Ctrl+C (SIGINT) 信号时调用的函数。"""
    click.echo(click.style(_("\n捕获到中断信号！正在尝试优雅地取消任务..."), fg='yellow'), err=True)
    cancel_event.set()

signal.signal(signal.SIGINT, signal_handler)

class AppContext:
    def __init__(self, config: MainConfig, verbose: bool):
        self.config = config
        self.verbose = verbose
        self.logger = logging.getLogger("cotton_toolkit.cli")
        self.cancel_event = cancel_event

@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.version_option(VERSION, '--version', message='%(prog)s, version %(version)s')
@click.option('--config', type=click.Path(exists=True, dir_okay=False), default='config.yml', help=_("配置文件路径。"))
@click.option('--lang', default='zh-hans', help="语言设置 (例如: en, zh-hans)。")
@click.option('-v', '--verbose', is_flag=True, default=False, help=_("启用详细日志输出。"))
@click.pass_context
def cli(ctx, config, lang, verbose):
    """棉花基因组分析工具包 (Cotton Toolkit) - 一个现代化的命令行工具。"""
    builtins._ = setup_localization(language_code=lang)
    global _
    _ = builtins._  # 确保 _ 是全局可用的

    if ctx.invoked_subcommand == 'init':
        ctx.obj = AppContext(config=MainConfig(), verbose=verbose)
        setup_global_logger(log_level_str="DEBUG" if verbose else "INFO")
    else:
        loaded_config = get_config(config)
        log_level_to_set = "DEBUG" if verbose else loaded_config.log_level
        setup_global_logger(log_level_str=log_level_to_set)
        ctx.obj = AppContext(config=loaded_config, verbose=verbose)

def _create_cli_progress_callback(bar: click.progressbar) -> Callable[[int, str], None]:
    """创建一个用于更新Click进度条的回调函数。"""
    def cli_progress_callback(percentage: int, message: str):
        bar.label = f"{message.ljust(40)}"
        current_pos = bar.pos
        steps_to_advance = percentage - current_pos
        if steps_to_advance > 0:
            bar.update(steps_to_advance)
    return cli_progress_callback


@cli.command()
@click.option('--output-dir', default='.', help=_("生成配置文件的目录。"))
@click.option('--overwrite', is_flag=True, help=_("覆盖已存在的配置文件。"))
@click.pass_context
def init(ctx, output_dir, overwrite):
    """生成默认的配置文件和目录结构。"""
    ctx.obj.logger.info(_("正在于 '{}' 生成默认配置文件...").format(output_dir))
    success, main_path, gs_path = generate_default_config_files(output_dir, overwrite=overwrite)
    if success:
        click.echo(_("默认文件生成成功:\n- {}\n- {}").format(main_path, gs_path))
    else:
        click.echo(_("生成部分或全部配置文件失败。"), err=True); sys.exit(1)

@cli.command()
@click.option('--versions', help=_("要下载的基因组版本列表，以逗号分隔。默认为全部。"))
@click.option('--force', is_flag=True, help=_("即使文件已存在也强制重新下载。"))
@click.option('--use-download-proxy', is_flag=True, help=_("为本次下载强制使用代理（覆盖配置）。"))
@click.pass_context
def download(ctx, versions, force, use_download_proxy):
    """下载基因组注释和同源数据。"""
    cli_overrides = {
        "versions": versions.split(',') if versions else None,
        "force": force,
        "use_proxy_for_download": use_download_proxy
    }
    with click.progressbar(length=100, label=_("准备下载...").ljust(40)) as bar:
        run_download_pipeline(
            config=ctx.obj.config,
            cli_overrides=cli_overrides,
            status_callback=ctx.obj.logger.info,
            progress_callback=_create_cli_progress_callback(bar),
            cancel_event=ctx.obj.cancel_event
        )

@cli.command()
@click.option('--genes', help=_("源基因ID列表，以逗号分隔。"))
@click.option('--region', help=_("源基因组区域, 格式如 'Chr01:1000-5000'。"))
@click.option('--source-asm', required=True, help=_("源基因组版本ID。"))
@click.option('--target-asm', required=True, help=_("目标基因组版本ID。"))
@click.option('--output-csv', type=click.Path(), help=_("保存输出CSV文件的路径。"))
@click.option('--top-n', type=int, help=_("为每个基因保留的最佳同源匹配数(0表示所有)。"))
@click.option('--evalue', type=float, help=_("E-value阈值。"))
@click.option('--pid', type=float, help=_("序列一致性百分比(PID)阈值。"))
@click.option('--score', type=float, help=_("BLAST得分(Score)阈值。"))
@click.option('--no-strict-priority', is_flag=True, default=False, help=_("禁用严格的同亚组/同源染色体匹配模式。"))
@click.pass_context
def homology(ctx, genes, region, source_asm, target_asm, output_csv, top_n, evalue, pid, score, no_strict_priority):
    """对基因列表或区域进行高级同源映射。"""
    if not genes and not region:
        raise click.UsageError(_("错误: 必须提供 --genes 或 --region 参数之一。"))

    gene_list = [g.strip() for g in genes.split(',')] if genes else None
    region_tuple = None
    if region:
        try:
            chrom, pos = region.split(':')
            start, end = map(int, pos.split('-'))
            region_tuple = (chrom, start, end)
        except ValueError:
            raise click.BadParameter(_("区域格式无效。请使用 'chr:start-end' 格式。"), param_hint='--region')

    criteria_overrides = {
        "top_n": top_n, "evalue_threshold": evalue, "pid_threshold": pid,
        "score_threshold": score, "strict_subgenome_priority": not no_strict_priority
    }

    if no_strict_priority:
        click.secho(_("警告: 严格模式已关闭，可能导致不同染色体的基因发生错配。"), fg='red', err=True)

    with click.progressbar(length=100, label=_("准备同源映射...").ljust(40)) as bar:
        run_homology_mapping(
            config=ctx.obj.config, gene_ids=gene_list, region=region_tuple,
            source_assembly_id=source_asm, target_assembly_id=target_asm,
            output_csv_path=output_csv, criteria_overrides=criteria_overrides,
            status_callback=ctx.obj.logger.info,
            progress_callback=_create_cli_progress_callback(bar),
            cancel_event=ctx.obj.cancel_event
        )

@cli.command('ai-task')
@click.option('--input-file', required=True, type=click.Path(exists=True, dir_okay=False), help=_("输入的CSV文件。"))
@click.option('--source-column', required=True, help=_("要处理的源列名。"))
@click.option('--new-column', required=True, help=_("要创建的新列名。"))
@click.option('--output-file', type=click.Path(), help=_("指定输出CSV文件的完整路径。默认为自动生成。"))
@click.option('--task-type', type=click.Choice(['translate', 'analyze']), default='translate', help=_("AI任务类型。"))
@click.option('--prompt', help=_("自定义提示词模板。必须包含 {text}。"))
@click.option('--temperature', type=float, help=_("控制模型输出的随机性。"))
@click.option('--use-ai-proxy', is_flag=True, help=_("为本次AI任务强制使用代理（覆盖配置）。"))
@click.pass_context
def ai_task(ctx, input_file, source_column, new_column, output_file, task_type, prompt, temperature, use_ai_proxy):
    """在CSV文件上运行批量AI任务。"""
    cli_overrides = {
        "temperature": temperature,
        "use_proxy_for_ai": use_ai_proxy
    }
    with click.progressbar(length=100, label=_("准备AI任务...").ljust(40)) as bar:
        run_ai_task(
            config=ctx.obj.config, input_file=input_file, source_column=source_column,
            new_column=new_column, task_type=task_type, custom_prompt_template=prompt,
            cli_overrides=cli_overrides, status_callback=ctx.obj.logger.info,
            progress_callback=_create_cli_progress_callback(bar),
            cancel_event=ctx.obj.cancel_event, output_file=output_file
        )

@cli.command('gff-query')
@click.option('--assembly-id', required=True, help=_("要查询的基因组版本ID。"))
@click.option('--genes', help=_("要查询的基因ID列表，以逗号分隔。"))
@click.option('--region', help=_("要查询的染色体区域，格式如 'A01:10000-20000'。"))
@click.option('--output-csv', type=click.Path(), help=_("【可选】保存结果的CSV文件路径。不提供则自动命名。"))
@click.pass_context
def gff_query(ctx, assembly_id, genes, region, output_csv):
    """从GFF文件中查询基因信息。"""
    if not genes and not region:
        raise click.UsageError(_("错误: 必须提供 --genes 或 --region 参数之一。"))
    if genes and region:
        click.echo(_("警告: 同时提供了 --genes 和 --region，将优先使用 --genes。"), err=True)
        region = None

    gene_list = [g.strip() for g in genes.split(',')] if genes else None
    region_tuple = None
    if region:
        try:
            chrom, pos_range = region.split(':')
            start, end = map(int, pos_range.split('-'))
            region_tuple = (chrom.strip(), start, end)
        except ValueError:
            raise click.BadParameter(_("区域格式无效。请使用 'Chr:Start-End' 格式。"), param_hint='--region')

    with click.progressbar(length=100, label=_("准备GFF查询...").ljust(40)) as bar:
        success = run_gff_lookup(
            config=ctx.obj.config,
            assembly_id=assembly_id,
            gene_ids=gene_list,
            region=region_tuple,
            output_csv_path=output_csv,
            status_callback=lambda msg, level: click.echo(f"[{level}] {msg}", err=True),
            progress_callback=_create_cli_progress_callback(bar),
            cancel_event=ctx.obj.cancel_event
        )

    if success:
        click.echo(_("GFF查询任务成功完成。"))
    else:
        click.echo(_("GFF查询任务失败或无结果。"), err=True)

@cli.command('locus-convert')
@click.option('--source-asm', required=True, help=_("源基因组版本ID。"))
@click.option('--target-asm', required=True, help=_("目标基因组版本ID。"))
@click.option('--region', required=True, help=_("要转换的源基因组区域, 格式如 'Chr:Start-End' 或 'Chr:Start..End'。"))
@click.option('--output-csv', required=True, type=click.Path(), help=_("保存输出CSV文件的路径。"))
@click.pass_context
def locus_convert(ctx, source_asm, target_asm, region, output_csv):
    """在不同基因组版本间进行位点坐标的同源转换。"""
    region_tuple = parse_region_string(region)
    if not region_tuple:
        raise click.BadParameter(_("区域格式无效。请使用 'Chr:Start-End' 格式。"), param_hint='--region')

    with click.progressbar(length=100, label=_("准备位点转换...").ljust(40)) as bar:
        result_message = run_locus_conversion(
            config=ctx.obj.config,
            source_assembly_id=source_asm,
            target_assembly_id=target_asm,
            region=region_tuple,
            output_path=output_csv,
            status_callback=lambda msg, level: click.echo(f"[{level}] {msg}", err=True),
            progress_callback=_create_cli_progress_callback(bar),
            cancel_event=ctx.obj.cancel_event
        )
    if result_message and "成功" in result_message:
        click.secho(result_message, fg='green')
    else:
        click.secho(_("位点转换失败。请查看日志获取详情。"), fg='red')
        raise click.Abort()

@cli.command('xlsx-to-csv')
@click.option('--input-excel', required=True, type=click.Path(exists=True, dir_okay=False), help=_("输入的Excel (.xlsx) 文件路径。"))
@click.option('--output-csv', required=True, type=click.Path(), help=_("输出的CSV文件路径。"))
@click.pass_context
def xlsx_to_csv(ctx, input_excel, output_csv):
    """将一个Excel文件(.xlsx)的所有工作表合并并转换为一个CSV文件。"""
    with click.progressbar(length=100, label=_("准备转换Excel...").ljust(40)) as bar:
        success = run_xlsx_to_csv(
            excel_path=input_excel,
            output_csv_path=output_csv,
            status_callback=lambda msg, level: click.echo(f"[{level}] {msg}", err=True),
            progress_callback=_create_cli_progress_callback(bar),
            cancel_event=ctx.obj.cancel_event
        )
    if success:
        click.secho(_("文件转换成功！"), fg='green')
    else:
        click.secho(_("文件转换失败。"), fg='red')
        raise click.Abort()

@cli.command('identify-genome')
@click.argument('genes', nargs=-1, required=True)
@click.pass_context
def identify_genome(ctx, genes):
    """根据基因ID列表，自动识别其最可能的基因组版本。"""
    if not genes:
        click.echo(_("请输入至少一个基因ID。"), err=True)
        return

    gene_list = list(genes)
    click.echo(_("正在为 {} 个基因ID进行基因组鉴定...").format(len(gene_list)))

    genome_sources = get_genome_data_sources(ctx.obj.config, logger_func=lambda msg, level: click.echo(f"[{level}] {msg}", err=True))
    if not genome_sources:
        click.secho(_("错误: 未能加载基因组源数据，无法进行鉴定。"), fg='red', err=True)
        raise click.Abort()

    identified_assembly = identify_genome_from_gene_ids(
        gene_ids=gene_list,
        genome_sources=genome_sources,
        status_callback=lambda msg, level: click.echo(f"[{level}] {msg}", err=True)
    )

    if identified_assembly:
        click.secho(_("鉴定结果: {}").format(identified_assembly), fg='green', bold=True)
    else:
        click.secho(_("未能识别到匹配的基因组版本。"), fg='yellow')

@cli.command('annotate')
@click.option('--genes', required=True, help=_("要注释的基因ID列表，以逗号分隔。或包含基因列表的文件路径。"))
@click.option('--assembly-id', required=True, help=_("基因ID所属的基因组版本。"))
@click.option('--types', default='go,ipr', help=_("要执行的注释类型，以逗号分隔 (go,ipr,kegg_orthologs,kegg_pathways)。"))
@click.option('--output-path', type=click.Path(), help=_("【可选】指定完整的输出CSV文件路径。"))
@click.pass_context
def annotate(ctx, genes, assembly_id, types, output_path):
    """对基因列表进行功能注释。"""
    gene_ids_list = []
    gene_list_file = None
    if os.path.exists(genes):
        gene_list_file = genes
        click.echo(_("从文件读取基因列表: {}").format(genes))
    else:
        gene_ids_list = [g.strip() for g in genes.split(',') if g.strip()]
        click.echo(_("从命令行参数读取 {} 个基因ID。").format(len(gene_ids_list)))

    if not gene_ids_list and not gene_list_file:
        raise click.UsageError(_("错误: 'genes' 参数既不是有效的文件路径，也不是基因ID列表。"))

    anno_types = [t.strip() for t in types.split(',') if t.strip()]
    if not anno_types:
        raise click.BadParameter(_("必须至少提供一种注释类型。"), param_hint='--types')

    output_dir = os.path.join(os.getcwd(), "annotation_results")

    with click.progressbar(length=100, label=_("准备功能注释...").ljust(40)) as bar:
        run_functional_annotation(
            config=ctx.obj.config,
            source_genome=assembly_id,
            target_genome=assembly_id,
            bridge_species=ctx.obj.config.integration_pipeline.bridge_species_name,
            annotation_types=anno_types,
            gene_ids=gene_ids_list,
            gene_list_path=gene_list_file,
            output_dir=output_dir,
            output_path=output_path,
            status_callback=lambda msg, level: click.echo(f"[{level}] {msg}", err=True),
            progress_callback=_create_cli_progress_callback(bar),
            cancel_event=ctx.obj.cancel_event
        )

@cli.command('enrich')
@click.option('--genes', required=True, help=_("要进行富集分析的基因ID列表 (逗号分隔), 或包含基因列表的文件路径。"))
@click.option('--assembly-id', required=True, help=_("基因ID所属的基因组版本。"))
@click.option('--analysis-type', type=click.Choice(['go', 'kegg'], case_sensitive=False), default='go', show_default=True, help=_("富集分析的类型。"))
@click.option('--output-dir', required=True, type=click.Path(file_okay=False), help=_("富集结果和图表的输出目录。"))
@click.option('--plot-types', default='bubble,bar', show_default=True, help=_("要生成的图表类型, 逗号分隔 (可选: bubble, bar, upset, cnet)。"))
@click.option('--top-n', type=int, default=20, show_default=True, help=_("在图表中显示的前N个富集条目。"))
@click.option('--collapse-transcripts', is_flag=True, default=False, show_default=True, help=_("将转录本ID合并为其父基因ID进行分析。"))
@click.pass_context
def enrich(ctx, genes, assembly_id, analysis_type, output_dir, plot_types, top_n, collapse_transcripts):
    """对基因列表进行GO或KEGG富集分析并生成图表。"""
    config = ctx.obj.config
    cancel_event = ctx.obj.cancel_event

    gene_ids_list = []
    if os.path.exists(genes):
        click.echo(_("从文件读取基因列表: {}").format(genes))
        try:
            gene_ids_list = pd.read_csv(genes, header=None).iloc[:, 0].dropna().unique().tolist()
        except Exception as e:
            raise click.UsageError(_("读取基因文件失败: {}").format(e))
    else:
        gene_ids_list = [g.strip() for g in genes.split(',') if g.strip()]

    if not gene_ids_list:
        raise click.UsageError(_("错误: 未提供任何有效的基因ID。"))

    click.echo(_("共找到 {} 个唯一基因ID用于分析。").format(len(gene_ids_list)))
    plot_types_list = [p.strip().lower() for p in plot_types.split(',') if p.strip()]

    with click.progressbar(length=100, label=_("准备富集分析...").ljust(40)) as bar:
        run_enrichment_pipeline(
            config=config,
            assembly_id=assembly_id,
            study_gene_ids=gene_ids_list,
            analysis_type=analysis_type,
            plot_types=plot_types_list,
            output_dir=output_dir,
            top_n=top_n,
            collapse_transcripts=collapse_transcripts,
            status_callback=lambda msg, level: click.echo(f"[{level.upper()}] {msg}", err=True),
            progress_callback=_create_cli_progress_callback(bar),
            cancel_event=cancel_event
        )
    click.secho(_("富集分析流程执行完毕。结果已保存至: {}").format(output_dir), fg='green')

@cli.command('status')
@click.pass_context
def status(ctx):
    """显示所有基因组注释文件的下载和预处理状态。"""
    config = ctx.obj.config
    genome_sources = get_genome_data_sources(config)
    if not genome_sources:
        click.echo(_("错误: 未能加载基因组源数据。"), err=True)
        return

    click.secho(f"{'Genome':<25} {'File Type':<20} {'Status'}", bold=True)
    click.echo("-" * 60)

    status_colors = {'processed': 'green', 'not_processed': 'yellow', 'not_downloaded': 'red'}
    anno_keys = ['GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs']
    for genome_id, genome_info in genome_sources.items():
        for key in anno_keys:
            if hasattr(genome_info, f"{key}_url") and getattr(genome_info, f"{key}_url"):
                file_status = check_annotation_file_status(config, genome_info, key)
                click.echo(f"{genome_id:<25} {key:<20} ", nl=False)
                click.secho(file_status, fg=status_colors.get(file_status, 'white'))

@cli.command('preprocess-annos')
@click.pass_context
def preprocess_annos(ctx):
    """预处理所有已下载的注释文件，转换为标准的CSV格式。"""
    with click.progressbar(length=100, label=_("准备预处理...").ljust(40)) as bar:
        run_preprocess_annotation_files(
            config=ctx.obj.config,
            status_callback=lambda msg, level: click.echo(f"[{level}] {msg}", err=True),
            progress_callback=_create_cli_progress_callback(bar),
            cancel_event=ctx.obj.cancel_event
        )

@cli.command('test-ai')
@click.option('--provider', help=_("要测试的服务商密钥 (例如 'google', 'openai')。默认为配置文件中的默认服务商。"))
@click.pass_context
def test_ai(ctx, provider):
    """测试配置文件中指定的AI服务商连接。"""
    config = ctx.obj.config
    provider_key = provider if provider else config.ai_services.default_provider
    click.echo(_("正在测试服务商: {}...").format(provider_key))

    provider_config = config.ai_services.providers.get(provider_key)
    if not provider_config:
        click.secho(_("错误: 在配置文件中未找到服务商 '{}' 的配置。").format(provider_key), fg='red')
        return

    api_key = provider_config.api_key
    model = provider_config.model
    base_url = provider_config.base_url

    proxies = None
    if config.ai_services.use_proxy_for_ai:
        if config.proxies and (config.proxies.http or config.proxies.https):
            proxies = config.proxies.to_dict()
            click.echo(f"INFO: 将使用代理进行连接测试: {proxies}")

    success, message = AIWrapper.test_connection(
        provider=provider_key,
        api_key=api_key,
        model=model,
        base_url=base_url,
        proxies=proxies
    )

    if success:
        click.secho(f"✅ {message}", fg='green')
    else:
        click.secho(f"❌ {message}", fg='red')


@cli.command('about')
@click.pass_context
def about(ctx):
    """显示关于本软件的全面信息，包括简介、致谢和完整的引文。"""
    # --- Header ---
    click.secho(f"--- {_('友好棉花基因组工具包 (FCGT)')} ---", fg='cyan', bold=True)
    click.echo(f"Version: {VERSION}")
    click.echo(_('本软件遵守 Apache-2.0 license 开源协议'))
    click.echo("")

    # --- Introduction ---
    click.secho(f"--- {_('软件简介')} ---", fg='cyan', bold=True)
    intro_text = _(
        "FCGT 是一款专为棉花研究者，特别是那些没有生物信息专业背景的科研人员和学生设计的基因组数据分析工具箱。它致力于将复杂的数据处理流程封装在简洁的图形界面（GUI）和命令行（CLI）背后，让您无需进行繁琐的环境配置和代码编写，即可“开箱即用”。本工具包提供了一系列强大的棉花基因组数据处理工具，包括多版本间的同源基因映射（Liftover）、功能注释、富集分析和AI助手等。")
    click.echo(textwrap.fill(intro_text, width=80))
    click.echo("")

    # --- Core Features ---
    click.secho(f"--- {_('核心亮点')} ---", fg='cyan', bold=True)
    click.echo(_("  • {feature}: 图形界面优先，无需复杂配置，多语言支持。").format(
        feature=click.style(_('极致友好，开箱即用'), bold=True)))
    click.echo(_("  • {feature}: 多线程加速，支持复杂的批量任务。").format(
        feature=click.style(_('高效的自动化与批量处理'), bold=True)))
    click.echo(_("  • {feature}: 棉花版 Liftover，一站式数据工具，标准化数据下载。").format(
        feature=click.style(_('精准的基因组工具集'), bold=True)))
    click.echo(_("  • {feature}: 为Windows/macOS提供预编译可执行文件，随处可用。").format(
        feature=click.style(_('跨平台，易于分发'), bold=True)))
    click.echo("")

    # --- Project Link ---
    click.secho(f"--- {_('获取更多信息')} ---", fg='cyan', bold=True)
    click.echo(_('项目开源地址: ') + click.style(PUBLISH_URL, fg='bright_blue', underline=True))
    click.echo("")

    # --- Data Sources & Citations ---
    click.secho(f"--- {_('数据来源与引文')} ---", fg='cyan', bold=True)
    click.echo(_("本工具依赖 CottonGen 提供的权威数据，感谢其团队持续的开放和维护。"))

    click.echo(f"\n{_('CottonGen 主要引文:')}")
    click.echo(
        "  - Yu, J, Jung S, et al. (2021) CottonGen: The Community Database for Cotton Genomics, Genetics, and Breeding Research. Plants 10(12), 2805.")
    click.echo(
        "  - Yu J, Jung S, et al. (2014) CottonGen: a genomics, genetics and breeding database for cotton research. Nucleic Acids Research 42(D1), D1229-D1236.")

    click.echo(f"\n{_('基因组引用文献:')}")
    full_genome_citations = [
        ("NAU-NBI_v1.1",
         "Zhang et. al., Sequencing of allotetraploid cotton (Gossypium hirsutum L. acc. TM-1) provides a resource for fiber improvement. Nature Biotechnology. 33, 531–537. 2015"),
        ("UTX-JGI-Interim-release_v1.1",
         "Haas, B.J., Delcher, A.L., Mount, S.M., Wortman, J.R., Smith Jr, R.K., Jr., Hannick, L.I., Maiti, R., Ronning, C.M., Rusch, D.B., Town, C.D. et al. (2003) Improving the Arabidopsis genome annotation using maximal transcript alignment assemblies. http://nar.oupjournals.org/cgi/content/full/31/19/5654 [Nucleic Acids Res, 31, 5654-5666].\n"
         "Smit, AFA, Hubley, R & Green, P. RepeatMasker Open-3.0. 1996-2011 .\n"
         "Yeh, R.-F., Lim, L. P., and Burge, C. B. (2001) Computational inference of homologous gene structures in the human genome. Genome Res. 11: 803-816.\n"
         "Salamov, A. A. and Solovyev, V. V. (2000). Ab initio gene finding in Drosophila genomic DNA. Genome Res 10, 516-22."),
        ("HAU_v1 / v1.1",
         "Wang et al. Reference genome sequences of two cultivated allotetraploid cottons, Gossypium hirsutum and Gossypium barbadense. Nature genetics. 2018 Dec 03"),
        ("ZJU-improved_v2.1_a1",
         "Hu et al. Gossypium barbadense and Gossypium hirsutum genomes provide insights into the origin and evolution of allotetraploid cotton. Nature genetics. 2019 Jan;51(1):164."),
        ("CRI_v1",
         "Yang Z, Ge X, Yang Z, Qin W, Sun G, Wang Z, Li Z, Liu J, Wu J, Wang Y, Lu L, Wang P, Mo H, Zhang X, Li F. Extensive intraspecific gene order and gene structural variations in upland cotton cultivars. Nature communications. 2019 Jul 05; 10(1):2989."),
        ("WHU_v1",
         "Huang, G. et al., Genome sequence of Gossypium herbaceum and genome updates of Gossypium arboreum and Gossypium hirsutum provide insights into cotton A-genome evolution. Nature Genetics. 2020. doi.org/10.1038/s41588-020-0607-4"),
        ("UTX_v2.1",
         "Chen ZJ, Sreedasyam A, Ando A, Song Q, De Santiago LM, Hulse-Kemp AM, Ding M, Ye W, Kirkbride RC, Jenkins J, Plott C, Lovell J, Lin YM, Vaughn R, Liu B, Simpson S, Scheffler BE, Wen L, Saski CA, Grover CE, Hu G, Conover JL, Carlson JW, Shu S, Boston LB, Williams M, Peterson DG, McGee K, Jones DC, Wendel JF, Stelly DM, Grimwood J, Schmutz J. Genomic diversifications of five Gossypium allopolyploid species and their impact on cotton improvement. Nature genetics. 2020 Apr 20."),
        ("HAU_v2.0",
         "Chang, Xing, Xin He, Jianying Li, Zhenping Liu, Ruizhen Pi, Xuanxuan Luo, Ruipeng Wang et al. \"High-quality Gossypium hirsutum and Gossypium barbadense genome assemblies reveal the landscape and evolution of centromeres.\" Plant Communications 5, no. 2 (2024). doi.org/10.1016/j.xplc.2023.100722")
    ]

    for name, citation_text in full_genome_citations:
        click.echo(f"  - {click.style(name, fg='green')}:")
        # Wrap long citation text and keep indentation for readability
        wrapped_text = textwrap.indent(textwrap.fill(citation_text, width=76), '    ')
        click.echo(wrapped_text)
    click.echo("")

    # --- Acknowledgements ---
    click.secho(f"--- {_('致谢')} ---", fg='cyan', bold=True)
    thanks_text = _(
        "感谢所有为本项目提供数据、算法和灵感的科研人员与开源社区。此软件由 Gemini AI 协助开发，功能持续迭代，欢迎学术交流和贡献。")
    click.echo(textwrap.fill(thanks_text, width=80))


if __name__ == '__main__':
    cli()