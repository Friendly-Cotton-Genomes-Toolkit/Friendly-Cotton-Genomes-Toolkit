# cotton_toolkit/cli.py
import builtins
import logging
import os
import signal
import sys
import threading

import pandas as pd

from cotton_toolkit.casestudies.bsa_hvg_integration import run_integrate_pipeline
from cotton_toolkit.core.ai_wrapper import AIWrapper
from .utils.localization import setup_localization
from .utils.logger import setup_global_logger
import click

from . import VERSION
from .pipelines import (
    run_download_pipeline,
    run_homology_mapping,
    run_ai_task, run_gff_lookup, run_functional_annotation, run_preprocess_annotation_files, run_enrichment_pipeline,

)
from .config.loader import load_config, generate_default_config_files, MainConfig, get_genome_data_sources, \
    check_annotation_file_status

cancel_event = threading.Event()
_ = lambda s: str(s) # 占位符
logger = logging.getLogger("cotton_toolkit.gui")


def get_config(config_path: str) -> MainConfig:
    """Helper to load config and handle CLI-specific errors."""
    try:
        config_obj = load_config(config_path)
        if not config_obj:
            click.echo(f"错误: 无法从 '{config_path}' 加载配置。文件可能为空或格式不正确。", err=True)
            raise click.Abort()
        return config_obj
    except FileNotFoundError:
        click.echo(f"错误: 配置文件 '{config_path}' 未找到。请检查路径或运行 'init' 命令。", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"错误: 加载配置文件时发生意外错误: {e}", err=True)
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

@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.version_option(VERSION, '--version', message='%(prog)s, version %(version)s')
@click.option('--config', type=click.Path(exists=True, dir_okay=False), default='config.yml', help=_("配置文件路径。"))
@click.option('--lang', default='zh-hans', help="语言设置 (例如: en, zh-hans)。")
@click.option('-v', '--verbose', is_flag=True, default=False, help=_("启用详细日志输出。"))
@click.pass_context
def cli(ctx, config, lang, verbose):
    """棉花基因组分析工具包 (Cotton Toolkit) - 一个现代化的命令行工具。"""
    builtins._ = setup_localization(language_code=lang)

    if ctx.invoked_subcommand == 'init':
        # init 命令不需要预加载配置
        ctx.obj = AppContext(config=MainConfig(), verbose=verbose)
        setup_global_logger(log_level_str="DEBUG" if verbose else "INFO")
    else:
        loaded_config = get_config(config)
        log_level_to_set = "DEBUG" if verbose else loaded_config.log_level
        setup_global_logger(log_level_str=log_level_to_set)
        ctx.obj = AppContext(config=loaded_config, verbose=verbose)


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
    run_download_pipeline(ctx.obj.config, cli_overrides, ctx.obj.logger.info, cancel_event=cancel_event)

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

    # --- 修改点 ---
    # 根据新的开关设置参数
    criteria_overrides = {
        "top_n": top_n, "evalue_threshold": evalue, "pid_threshold": pid,
        "score_threshold": score, "strict_subgenome_priority": not no_strict_priority
    }

    # 如果关闭了严格模式，显示红色警告
    if no_strict_priority:
        click.secho(_("警告: 严格模式已关闭，可能导致不同染色体的基因发生错配。"), fg='red', err=True)

    run_homology_mapping(
        config=ctx.obj.config, gene_ids=gene_list, region=region_tuple,
        source_assembly_id=source_asm, target_assembly_id=target_asm,
        output_csv_path=output_csv, criteria_overrides=criteria_overrides,
        status_callback=ctx.obj.logger.info,
        cancel_event=cancel_event

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
    # --- 修改点: 传递新的代理标志 ---
    cli_overrides = {
        "temperature": temperature,
        "use_proxy_for_ai": use_ai_proxy
    }
    # --- 修改结束 ---
    run_ai_task(
        config=ctx.obj.config, input_file=input_file, source_column=source_column,
        new_column=new_column, task_type=task_type, custom_prompt_template=prompt,
        cli_overrides=cli_overrides, status_callback=ctx.obj.logger.info,
        cancel_event=cancel_event, output_file=output_file
    )


@cli.command('gff-query')
@click.option('--assembly-id', required=True, help=_("要查询的基因组版本ID。"))
@click.option('--genes', help=_("要查询的基因ID列表，以逗号分隔。"))
@click.option('--region', help=_("要查询的染色体区域，格式如 'A01:10000-20000'。"))
@click.option('--output-csv', type=click.Path(), help=_("【可选】保存结果的CSV文件路径。不提供则自动命名。"))
@click.pass_context
def gff_query(ctx, assembly_id, genes, region, output_csv):
    """
    从GFF文件中查询基因信息。
    可根据基因ID列表或染色体区域进行查询。
    """
    # 输入验证
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

    click.echo(_("正在启动GFF查询..."))

    # 调用后端流水线
    success = run_gff_lookup(
        config=ctx.obj.config,
        assembly_id=assembly_id,
        gene_ids=gene_list,
        region=region_tuple,
        output_csv_path=output_csv,
        status_callback=lambda msg, level: click.echo(f"[{level}] {msg}"),
        cancel_event=cancel_event
    )

    if success:
        click.echo(_("GFF查询任务成功完成。"))
    else:
        click.echo(_("GFF查询任务失败。"), err=True)


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

    # 准备备用输出目录
    output_dir = os.path.join(os.getcwd(), "annotation_results")

    run_functional_annotation(
        config=ctx.obj.config,
        source_genome=assembly_id,
        target_genome=assembly_id,  # 在CLI中，假定源和目标相同
        bridge_species=ctx.obj.config.integration_pipeline.bridge_species_name,
        annotation_types=anno_types,
        gene_ids=gene_ids_list,
        gene_list_path=gene_list_file,
        output_dir=output_dir,
        output_path=output_path,
        status_callback=lambda msg, level: click.echo(f"[{level}] {msg}"),
        cancel_event=cancel_event

    )


@cli.command('enrich')
@click.option('--genes', required=True, help=_("要进行富集分析的基因ID列表 (逗号分隔), 或包含基因列表的文件路径。"))
@click.option('--assembly-id', required=True, help=_("基因ID所属的基因组版本。"))
@click.option('--analysis-type', type=click.Choice(['go', 'kegg'], case_sensitive=False), default='go',
              show_default=True, help=_("富集分析的类型。"))
@click.option('--output-dir', required=True, type=click.Path(file_okay=False), help=_("富集结果和图表的输出目录。"))
@click.option('--plot-types', default='bubble,bar', show_default=True,
              help=_("要生成的图表类型, 逗号分隔 (可选: bubble, bar, upset, cnet)。"))
@click.option('--top-n', type=int, default=20, show_default=True, help=_("在图表中显示的前N个富集条目。"))
@click.option('--collapse-transcripts', is_flag=True, default=False, show_default=True,
              help=_("将转录本ID合并为其父基因ID进行分析。"))
@click.pass_context
def enrich(ctx, genes, assembly_id, analysis_type, output_dir, plot_types, top_n, collapse_transcripts):
    """对基因列表进行GO或KEGG富集分析并生成图表。"""
    config = ctx.obj.config
    cancel_event = ctx.obj.cancel_event

    # 解析基因列表输入 (可以是字符串或文件路径)
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

    # 解析图表类型
    plot_types_list = [p.strip().lower() for p in plot_types.split(',') if p.strip()]

    click.echo(_("启动 {} 富集分析...").format(analysis_type.upper()))

    # 调用后端的富集分析流程
    try:
        run_enrichment_pipeline(
            config=config,
            assembly_id=assembly_id,
            study_gene_ids=gene_ids_list,
            analysis_type=analysis_type,
            plot_types=plot_types_list,
            output_dir=output_dir,
            top_n=top_n,
            collapse_transcripts=collapse_transcripts,
            status_callback=lambda msg, level: click.echo(f"[{level.upper()}] {msg}"),
            cancel_event=cancel_event
        )
        click.secho(_("富集分析流程执行完毕。结果已保存至: {}").format(output_dir), fg='green')
    except Exception as e:
        click.secho(_("富集分析过程中发生错误: {}").format(e), fg='red')
        # 如果需要更详细的错误调试信息，可以取消下面这行的注释
        # traceback.print_exc()
        raise click.Abort()


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

    status_colors = {
        'processed': 'green',
        'not_processed': 'yellow',
        'not_downloaded': 'red'
    }

    anno_keys = ['GO', 'IPR', 'KEGG_pathways', 'KEGG_orthologs']
    for genome_id, genome_info in genome_sources.items():
        for key in anno_keys:
            # 只显示配置了URL的文件类型
            if hasattr(genome_info, f"{key}_url") and getattr(genome_info, f"{key}_url"):
                file_status = check_annotation_file_status(config, genome_info, key)
                click.echo(f"{genome_id:<25} {key:<20} ", nl=False)
                click.secho(file_status, fg=status_colors.get(file_status, 'white'))


@cli.command('preprocess-annos')
@click.pass_context
def preprocess_annos(ctx):
    """预处理所有已下载的注释文件，转换为标准的CSV格式。"""
    click.echo(_("正在启动注释文件预处理流程..."))
    run_preprocess_annotation_files(
        config=ctx.obj.config,
        status_callback=lambda msg, level: click.echo(f"[{level}] {msg}"),
        cancel_event=cancel_event
    )


@cli.command('test-ai')
@click.option('--provider', help=_("要测试的服务商密钥 (例如 'google', 'openai')。默认为配置文件中的默认服务商。"))
@click.pass_context
def test_ai(ctx, provider):
    """测试配置文件中指定的AI服务商连接。"""
    config = ctx.obj.config

    # 如果未指定，则使用默认服务商
    provider_key = provider if provider else config.ai_services.default_provider
    click.echo(_("正在测试服务商: {}...").format(provider_key))

    provider_config = config.ai_services.providers.get(provider_key)
    if not provider_config:
        click.secho(_("错误: 在配置文件中未找到服务商 '{}' 的配置。").format(provider_key), fg='red')
        return

    # 从配置中获取参数
    api_key = provider_config.api_key
    model = provider_config.model
    base_url = provider_config.base_url

    # 假设CLI也可能需要代理
    proxies = None
    if config.ai_services.use_proxy_for_ai:
        if config.proxies and (config.proxies.http or config.proxies.https):
            proxies = config.proxies.to_dict()
            click.echo(f"INFO: 将使用代理进行连接测试: {proxies}")

    # 调用后端的测试函数
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


@cli.command()
@click.option('--excel-path', type=click.Path(exists=True, dir_okay=False), help=_("覆盖配置文件中的输入Excel文件路径。"))
@click.option('--log2fc-threshold', type=float, help=_("覆盖配置文件中的 Log2FC 阈值。"))
@click.pass_context
def integrate(ctx, excel_path, log2fc_threshold):
    """
    (高级案例) 运行整合分析流程，筛选候选基因。
    """
    config_obj = ctx.obj.config

    # 覆盖配置
    if excel_path:
        config_obj.integration_pipeline.input_excel_path = excel_path
    if log2fc_threshold is not None:
        config_obj.integration_pipeline.common_hvg_log2fc_threshold = log2fc_threshold

    run_integrate_pipeline(
        config=config_obj,
        cli_overrides=None,
        status_callback=lambda msg, level: click.echo(f"[{level}] {msg}"),
        progress_callback=lambda p, m: click.echo(f"[{p}%] {m}"),
        cancel_event=cancel_event
    )

if __name__ == '__main__':
    cli()