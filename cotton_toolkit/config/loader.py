# cotton_toolkit/config/loader.py
import shutil
import yaml
import os
from typing import Dict, Any, Optional, Tuple
from .models import MainConfig, GenomeSourcesConfig
from dataclasses import asdict, is_dataclass

# 国际化函数占位符
try:
    import builtins

    _ = builtins._
except (AttributeError, ImportError):
    def _(text: str) -> str:
        return text


class Dumper(yaml.Dumper):
    """自定义YAML Dumper，用于正确序列化dataclass"""

    def represent_data(self, data):
        if is_dataclass(data):
            return self.represent_dict(asdict(data))
        return super().represent_data(data)


def save_config(config_obj: Any, file_path: str) -> bool:
    """将配置对象 (dataclass) 保存为YAML文件。"""
    try:
        output_dir = os.path.dirname(file_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            print(_("已创建目录: {}").format(output_dir))

        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(asdict(config_obj), f, Dumper=Dumper, allow_unicode=True, sort_keys=False, indent=2)

        print(_("配置文件已成功保存到 '{}'。").format(file_path))
        return True
    except Exception as e:
        print(_("错误: 保存配置文件 '{}' 失败: {}").format(file_path, e))
        return False


def load_config(config_path: str) -> Optional[MainConfig]:
    """加载YAML文件并返回一个MainConfig对象，包含版本校验。"""
    if not os.path.exists(config_path):
        print(_("错误: 配置文件 '{}' 未找到。").format(config_path))
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise TypeError(_("配置文件顶层结构必须是一个字典。"))

        if data.get('config_version') != 1:
            raise ValueError(_("配置文件 '{}' 的版本不兼容。当前程序仅支持版本 1。").format(config_path))

        config_obj = MainConfig.from_dict(data)
        config_obj._config_file_abs_path_ = os.path.abspath(config_path)
        print(_("配置文件 '{}' 加载成功。").format(config_path))
        return config_obj
    except (TypeError, ValueError) as e:
        raise e
    except Exception as e:
        import traceback
        print(_("加载配置文件 '{}' 时发生未知错误: {}").format(config_path, e))
        traceback.print_exc()
        return None


def get_genome_data_sources(main_config: MainConfig) -> Optional[Dict[str, Any]]:
    """从主配置对象中获取或加载基因组数据源。"""

    downloader_cfg = main_config.get('downloader')
    if not downloader_cfg:
        print(_("错误: 配置对象不完整，缺少 'downloader' 部分。"))
        return None

    gs_file_rel = downloader_cfg.get('genome_sources_file')
    if not gs_file_rel:
        print(_("错误: 主配置的 'downloader' 部分缺少 'genome_sources_file' 定义。"))
        return None

    main_config_dir = os.path.dirname(
        main_config._config_file_abs_path_) if main_config._config_file_abs_path_ else os.getcwd()
    gs_file_path_abs = os.path.join(main_config_dir, gs_file_rel) if not os.path.isabs(gs_file_rel) else gs_file_rel

    if not os.path.exists(gs_file_path_abs):
        print(_("错误: 基因组源文件 '{}' 未找到。").format(gs_file_path_abs))
        return None

    try:
        with open(gs_file_path_abs, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        if data.get('list_version') != 1:
            print(_("错误: 基因组源文件 '{}' 的版本不兼容。当前程序仅支持版本 1。").format(gs_file_path_abs))
            return None

        gs_config = GenomeSourcesConfig.from_dict(data)
        return {k: asdict(v) for k, v in gs_config.genome_sources.items()}
    except Exception as e:
        print(_("错误: 加载或解析基因组源文件 '{}' 失败: {}").format(gs_file_path_abs, e))
        return None


def generate_default_config_files(
        output_dir: str,
        main_config_filename: str = "config.yml",
        genome_sources_filename: str = "genome_sources_list.yml",
        overwrite: bool = False
) -> Tuple[bool, str, str]:
    """通过实例化配置类来生成默认的配置文件，并支持覆盖选项。"""
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            print(_("错误: 创建目录 '{}' 失败: {}").format(output_dir, e))
            return False, "", ""

    main_config_path = os.path.join(output_dir, main_config_filename)
    genome_sources_path = os.path.join(output_dir, genome_sources_filename)

    success_main = False
    success_gs = False

    if os.path.exists(main_config_path) and not overwrite:
        print(_("警告: 主配置文件 '{}' 已存在，跳过生成。").format(main_config_path))
        success_main = True
    else:
        main_conf_default = MainConfig()
        main_conf_default.downloader.genome_sources_file = genome_sources_filename
        success_main = save_config(main_conf_default, main_config_path)

    if os.path.exists(genome_sources_path) and not overwrite:
        print(_("警告: 基因组源文件 '{}' 已存在，跳过生成。").format(genome_sources_path))
        success_gs = True
    else:
        gs_conf_default = GenomeSourcesConfig()
        success_gs = save_config(gs_conf_default, genome_sources_path)

    return success_main and success_gs, main_config_path, genome_sources_path