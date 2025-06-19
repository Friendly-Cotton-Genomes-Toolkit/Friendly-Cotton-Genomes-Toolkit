# cotton_toolkit/cli.py
import builtins
import logging
import sys
import threading
from .utils.localization import setup_localization
from .utils.logger import setup_global_logger
import click

from . import VERSION
from .pipelines import (
    run_download_pipeline,
    run_integrate_pipeline,
    run_homology_mapping,
    run_ai_task
)
from .config.loader import load_config, generate_default_config_files, MainConfig


cancel_event = threading.Event()
_ = lambda s: str(s) # 占位符
logger = logging.getLogger("cotton_toolkit.gui")

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
def cli(ctx, config,lang, verbose):
    """棉花基因组分析工具包 (Cotton Toolkit) - 一个现代化的命令行工具。"""

    builtins._ = setup_localization(language_code=lang)

    try:
        loaded_config = load_config(config)
        if not loaded_config:
            if ctx.invoked_subcommand not in ['init']:
                click.echo(_("错误: 配置文件 '{}' 未找到。请先运行 'init' 命令。").format(config), err=True)
                sys.exit(1)
            loaded_config = MainConfig()

        log_level_to_set = "DEBUG" if verbose else loaded_config.log_level
        setup_global_logger(log_level_str=log_level_to_set)
        ctx.obj = AppContext(config=loaded_config, verbose=verbose)
    except Exception as e:
        click.echo(_("加载或解析配置时出错: {}").format(e), err=True)
        sys.exit(1)

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
@click.option('--http-proxy', help=_("用于HTTP请求的代理。"))
@click.option('--https-proxy', help=_("用于HTTPS请求的代理。"))
@click.pass_context
def download(ctx, versions, force, http_proxy, https_proxy):
    """下载基因组注释和同源数据。"""
    cli_overrides = {
        "versions": versions.split(',') if versions else None,
        "force": force,
        "http_proxy": http_proxy,
        "https_proxy": https_proxy
    }
    run_download_pipeline(ctx.obj.config, cli_overrides, ctx.obj.logger.info)

@cli.command()
@click.option('--excel-path', type=click.Path(exists=True, dir_okay=False), help=_("覆盖配置文件中的输入Excel文件路径。"))
@click.option('--log2fc-threshold', type=float, help=_("覆盖配置文件中的 Log2FC 阈值。"))
@click.pass_context
def integrate(ctx, excel_path, log2fc_threshold):
    """联合分析BSA与HVG数据。"""
    cli_overrides = {
        "input_excel_path": excel_path,
        "common_hvg_log2fc_threshold": log2fc_threshold
    }
    run_integrate_pipeline(ctx.obj.config, cli_overrides, ctx.obj.logger.info)


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
        status_callback=ctx.obj.logger.info
    )


@cli.command('ai-task')
@click.option('--input-file', required=True, type=click.Path(exists=True, dir_okay=False), help=_("输入的CSV文件。"))
@click.option('--source-column', required=True, help=_("要处理的源列名。"))
@click.option('--new-column', required=True, help=_("要创建的新列名。"))
@click.option('--task-type', type=click.Choice(['translate', 'analyze']), default='translate', help=_("AI任务类型。"))
@click.option('--prompt', help=_("自定义提示词模板。必须包含 {text}。"))
@click.option('--temperature', type=float, help=_("控制模型输出的随机性。"))
@click.pass_context
def ai_task(ctx, input_file, source_column, new_column, task_type, prompt, temperature):
    """在CSV文件上运行批量AI任务。"""
    cli_overrides = {"temperature": temperature}
    run_ai_task(
        config=ctx.obj.config, input_file=input_file, source_column=source_column,
        new_column=new_column, task_type=task_type, custom_prompt_template=prompt,
        cli_overrides=cli_overrides, status_callback=ctx.obj.logger.info
    )



if __name__ == '__main__':
    cli()