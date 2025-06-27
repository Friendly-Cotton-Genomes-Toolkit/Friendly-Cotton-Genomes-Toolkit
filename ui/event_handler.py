import json
import logging
import os
import threading
import traceback
import webbrowser
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable, Dict, Optional, Any

import customtkinter as ctk

from cotton_toolkit import VERSION as PKG_VERSION, HELP_URL as PKG_HELP_URL, PUBLISH_URL as PKG_PUBLISH_URL
from cotton_toolkit.config.loader import load_config, save_config, generate_default_config_files, \
    get_genome_data_sources
from cotton_toolkit.config.models import MainConfig
from .dialogs import MessageDialog
from .utils.gui_helpers import identify_genome_from_gene_ids

# 避免循环导入，同时为IDE提供类型提示
if TYPE_CHECKING:
    from .gui_app import CottonToolkitApp
    import tkinter as tk

# 全局翻译函数
try:
    from builtins import _
except ImportError:
    _ = lambda s: str(s)

# 使用标准日志记录器
logger = logging.getLogger(__name__)


class EventHandler:
    """处理所有用户交互、后台消息和任务启动。"""

    def __init__(self, app: "CottonToolkitApp"):
        self.app = app
        self.message_handlers = self.initialize_message_handlers()
        self.error_dialog_lock = threading.Lock()

    def initialize_message_handlers(self) -> Dict[str, Callable]:
        """返回消息类型到其处理函数的映射。"""
        return {
            "startup_complete": self._handle_startup_complete,
            "startup_failed": self._handle_startup_failed,
            "config_load_task_done": self._handle_config_load_task_done,
            "task_done": self._handle_task_done,
            "error": self._handle_error,
            "status": self._handle_status,
            "progress": self._handle_progress,
            "hide_progress_dialog": self.app.ui_manager._hide_progress_dialog,
            "update_sheets_dropdown": self._handle_update_sheets_dropdown,
            "csv_columns_fetched": self._handle_csv_columns_fetched,
            "ai_models_fetched": self._handle_ai_models_fetched,
            "ai_models_failed": self._handle_ai_models_failed,
            "ai_test_result": self._handle_ai_test_result,
            "auto_identify_success": self._handle_auto_identify_success,
            "auto_identify_fail": self._handle_auto_identify_fail,
            "auto_identify_error": self._handle_auto_identify_error,
        }

    # --- 后台消息处理方法 ---

    def _handle_csv_columns_fetched(self, data: tuple):
        """处理从后台线程获取到的CSV列名。"""
        columns, error_msg = data
        if 'ai_assistant' in self.app.tool_tab_instances:
            ai_tab = self.app.tool_tab_instances['ai_assistant']
            if hasattr(ai_tab, 'update_column_dropdown_ui'):
                ai_tab.update_column_dropdown_ui(columns, error_msg)

    def _handle_startup_complete(self, data: dict):
        """处理后台启动任务完成的消息。"""
        app = self.app
        app.ui_manager._hide_progress_dialog()
        app.genome_sources_data = data.get("genome_sources")
        config_data = data.get("config")
        config_path_from_load = data.get("config_path")

        if config_data:
            app.current_config = config_data
            app.config_path = config_path_from_load
            logger.info(_("默认配置文件加载成功。"))
        else:
            logger.warning(_("未找到或无法加载默认配置文件。"))

        app.ui_manager.update_ui_from_config()
        app.ui_manager.update_language_ui()
        app.ui_manager.update_button_states()

    def _handle_startup_failed(self, data: str):
        """处理启动失败消息。"""
        self.app.ui_manager._hide_progress_dialog()
        self.app.ui_manager.show_error_message(_("启动错误"), str(data))
        self.app.ui_manager.update_button_states()

    def _handle_config_load_task_done(self, data: tuple):
        """处理配置加载任务完成消息。"""
        app = self.app
        app.ui_manager._hide_progress_dialog()
        success, result_data, filepath = data
        if success:
            app.current_config = result_data
            app.config_path = os.path.abspath(filepath)
            app.ui_manager.show_info_message(_("加载完成"), _("配置文件已成功加载并应用。"))
            app.genome_sources_data = get_genome_data_sources(app.current_config, logger_func=logger.info)
            app.ui_manager.update_ui_from_config()
        else:
            app.ui_manager.show_error_message(_("加载失败"), str(result_data))

    def _handle_task_done(self, data: tuple):
        """处理后台任务完成消息。"""
        app = self.app
        success, task_display_name, result_data = data
        app.ui_manager._finalize_task_ui(task_display_name, success, result_data)

        if "富集分析" in task_display_name:
            if success and result_data:
                app.ui_manager._show_plot_results(result_data)
            elif success:
                app.ui_manager.show_info_message(_("分析完成"), _("富集分析完成，但没有发现任何显著富集的结果，因此未生成图表。"))
        elif task_display_name == _("位点转换"):
            locus_conversion_tab = app.tool_tab_instances.get('locus_conversion')
            if locus_conversion_tab and hasattr(locus_conversion_tab, 'result_textbox'):
                textbox = locus_conversion_tab.result_textbox
                textbox.configure(state="normal")
                textbox.delete("1.0", "end")
                if success and result_data is not None and not result_data.empty:
                    textbox.insert("1.0", result_data.to_string(index=False))
                elif success:
                    textbox.insert("1.0", _("未找到有效的同源区域。"))
                else:
                    textbox.insert("1.0", _("任务执行失败，无结果。"))
                textbox.configure(state="disabled")

    def _handle_error(self, data: str):
        """处理错误消息。"""
        app = self.app
        app.ui_manager.show_error_message(_("任务执行出错"), data)
        app.ui_manager._finalize_task_ui(app.active_task_name or _("未知任务"), success=False)
        if hasattr(app, 'status_label') and app.status_label.winfo_exists():
            status_text = f"{_('任务终止于')}: {str(data)[:100]}..."
            app.status_label.configure(text=status_text)
        if self.error_dialog_lock.locked():
            self.error_dialog_lock.release()

    def _handle_status(self, data: str):
        """处理状态更新消息。"""
        if hasattr(self.app, 'status_label') and self.app.status_label.winfo_exists():
            self.app.status_label.configure(text=str(data)[:150])

    def _handle_progress(self, data: tuple):
        """处理进度更新消息。"""
        percentage, text = data
        if self.app.ui_manager.progress_dialog and self.app.ui_manager.progress_dialog.winfo_exists():
            self.app.ui_manager.progress_dialog.update_progress(percentage, text)

    def _handle_ai_models_fetched(self, data: tuple):
        """处理AI模型列表获取成功消息。"""
        provider_key, models = data
        logger.info(f"{provider_key} {_('模型列表获取成功。')}")
        self.app.ui_manager.update_ai_model_dropdown(provider_key, models)
        self.app.ui_manager.show_info_message(_("刷新成功"), f"{_('已成功获取并更新')} {provider_key} {_('的模型列表。')}")

    def _handle_ai_models_failed(self, data: tuple):
        """处理AI模型列表获取失败消息。"""
        provider_key, error_msg = data
        logger.error(f"{provider_key} {_('模型列表获取失败:')} {error_msg}")
        self.app.ui_manager.update_ai_model_dropdown(provider_key, [], error=True)
        self.app.ui_manager.show_warning_message(_("刷新失败"), f"{_('获取模型列表失败，请检查API Key或网络连接，并手动输入模型名称。')}\n\n{_('错误详情:')} {error_msg}")

    def _handle_update_sheets_dropdown(self, data: tuple):
        """处理 Excel 工作表下拉菜单更新消息。"""
        sheet_names, excel_path, error = data
        self.app.excel_sheet_cache[excel_path] = sheet_names
        if error:
            logger.warning(f"Failed to load Excel sheets from {excel_path}: {error}")
        else:
            logger.info(f"Successfully loaded sheets for {excel_path}.")

    def _handle_ai_test_result(self, data: tuple):
        """处理AI连接测试结果。"""
        if self.app.ui_manager.progress_dialog:
            self.app.ui_manager.progress_dialog.close()
        success, message = data
        if success:
            self.app.ui_manager.show_info_message(_("测试成功"), message)
        else:
            self.app.ui_manager.show_error_message(_("测试失败"), message)

    def _handle_auto_identify_success(self, data: tuple):
        """处理基因组自动识别成功消息。"""
        target_var, assembly_id = data
        if self.app.genome_sources_data and assembly_id in self.app.genome_sources_data:
            if isinstance(target_var, ctk.StringVar):
                target_var.set(assembly_id)
                logger.debug(f"UI已自动更新基因为: {assembly_id}")

    def _handle_auto_identify_fail(self, data=None):
        """处理基因组自动识别失败消息。"""
        pass

    def _handle_auto_identify_error(self, data: str):
        """处理基因组自动识别错误消息。"""
        logger.error(f"自动识别基因组时发生错误: {data}")

    # --- 用户界面事件处理 ---

    def on_closing(self):
        """处理应用程序关闭事件。"""
        app = self.app
        dialog = MessageDialog(parent=app, title=_("退出程序"), message=_("您确定要退出吗?"), icon_type="question", buttons=[_("确定"), _("取消")], app_font=app.app_font)
        dialog.wait_window()
        if dialog.result == _("确定"):
            app.destroy()

    def on_language_change(self, selected_display_name: str):
        """处理语言改变事件。"""
        app = self.app
        new_language_code = app.LANG_NAME_TO_CODE.get(selected_display_name, "zh-hans")
        if app.current_config and app.config_path:
            app.current_config.i18n_language = new_language_code
            try:
                if save_config(app.current_config, app.config_path):
                    logger.info(_("语言设置 '{}' 已成功保存到 {}").format(new_language_code, os.path.basename(app.config_path)))
                else:
                    raise IOError(_("保存配置时返回False"))
            except Exception as e:
                app.ui_manager.show_error_message(_("保存失败"), _("无法将新的语言设置保存到配置文件中: {}").format(e))
        else:
            app.ui_manager.show_warning_message(_("无法保存"), _("请先加载一个配置文件才能更改并保存语言设置。"))
        app.ui_manager.update_language_ui(new_language_code)

    def change_appearance_mode_event(self, new_mode_display: str):
        """处理外观模式改变事件。"""
        app = self.app
        mode_map_from_display = {_("浅色"): "Light", _("深色"): "Dark", _("系统"): "System"}
        new_mode = mode_map_from_display.get(new_mode_display, "System")
        ctk.set_appearance_mode(new_mode)
        app.ui_settings['appearance_mode'] = new_mode
        self._save_ui_settings()
        app.ui_manager._update_log_tag_colors()

    def toggle_log_viewer(self):
        """切换日志文本框的可见性。"""
        app = self.app
        if app.log_viewer_visible:
            app.log_textbox.grid_remove()
            app.toggle_log_button.configure(text=_("显示日志"))
            app.log_viewer_visible = False
        else:
            app.log_textbox.grid()
            app.toggle_log_button.configure(text=_("隐藏日志"))
            app.log_viewer_visible = True

    def clear_log_viewer(self):
        """清除日志查看器内容。"""
        if hasattr(self.app, 'log_textbox'):
            self.app.log_textbox.configure(state="normal")
            self.app.log_textbox.delete("1.0", "end")
            self.app.log_textbox.configure(state="disabled")
            logger.info(_("日志已清除。"))

    def load_config_file(self, filepath: Optional[str] = None):
        """加载配置文件，并异步应用到UI。"""
        if not filepath:
            filepath = filedialog.askopenfilename(title=_("选择配置文件"), filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*")))
        if filepath:
            logger.info(f"{_('尝试加载配置文件:')} {filepath}")
            self.app.ui_manager._show_progress_dialog(title=_("加载配置中..."), message=_("正在加载配置文件并应用到UI..."), on_cancel=None)
            threading.Thread(target=self._load_config_thread, args=(filepath,), daemon=True).start()
        else:
            logger.info(_("用户取消加载配置文件。"))

    def _load_config_thread(self, filepath: str):
        """在后台线程中加载配置。"""
        try:
            config_data = load_config(os.path.abspath(filepath))
            self.app.message_queue.put(("config_load_task_done", (True, config_data, filepath)))
        except Exception as e:
            detailed_error = f"{e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
            self.app.message_queue.put(("config_load_task_done", (False, detailed_error, None)))

    def save_config_file(self, config_data: Optional[Dict] = None, show_dialog: bool = False) -> bool:
        """保存当前配置, 可选择是否弹出另存为对话框。"""
        app = self.app
        if config_data is None:
            config_data = app.current_config
        if not config_data:
            app.ui_manager.show_error_message(_("错误"), _("没有可保存的配置。"))
            return False
        save_path = app.config_path
        if show_dialog or not save_path:
            save_path = filedialog.asksaveasfilename(title=_("配置文件另存为"), filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*")), defaultextension=".yml")
        if save_path:
            try:
                if save_config(config_data, save_path):
                    app.config_path = save_path
                    app.current_config = config_data
                    app.ui_manager.update_ui_from_config()
                    app.ui_manager.show_info_message(_("保存成功"), _("配置文件已保存至: {}").format(save_path))
                    return True
                else:
                    app.ui_manager.show_error_message(_("保存失败"), _("保存配置文件时发生未知错误，请检查日志。"))
                    return False
            except Exception as e:
                app.ui_manager.show_error_message(_("保存失败"), f"{_('保存配置文件时发生错误:')} {e}")
                return False
        return False

    def on_config_updated(self, new_config_data: Dict):
        """当外部窗口(如编辑器)更新了配置后，由此方法通知主窗口。"""
        self.app.current_config = new_config_data
        self.app.ui_manager.update_ui_from_config()
        logger.info(_("配置已从高级编辑器更新。"))

    def _generate_default_configs_gui(self):
        """处理“生成默认配置”按钮的点击事件。"""
        app = self.app
        output_dir = filedialog.askdirectory(title=_("选择生成默认配置文件的目录"))
        if not output_dir:
            logger.info(_("用户取消了目录选择。"))
            return
        logger.info(f"{_('用户选择的配置目录:')} {output_dir}")
        main_config_filename = "config.yml"
        main_config_path = os.path.join(output_dir, main_config_filename)
        should_overwrite = False
        if os.path.exists(main_config_path):
            dialog = MessageDialog(parent=app, title=_("文件已存在"), message=_("配置文件 '{}' 已存在于所选目录中。\n\n您想覆盖它吗？\n(选择“否”将直接加载现有文件)").format(main_config_filename), buttons=[_("是 (覆盖)"), _("否 (加载)")], icon_type="question", app_font=app.app_font)
            dialog.wait_window()
            user_choice = dialog.result
            if user_choice == _("是 (覆盖)"):
                should_overwrite = True
            elif user_choice == _("否 (加载)"):
                self.load_config_file(filepath=main_config_path)
                return
            else:
                logger.info(_("用户取消了操作。"))
                return
        try:
            logger.info(_("正在生成默认配置文件..."))
            success, new_main_cfg_path, new_gs_cfg_path = generate_default_config_files(output_dir, overwrite=should_overwrite, main_config_filename=main_config_filename)
            if success:
                msg = f"{_('默认配置文件已成功生成到:')}\n{new_main_cfg_path}\n{new_gs_cfg_path}\n\n{_('是否立即加载新生成的配置文件?')}"
                load_dialog = MessageDialog(parent=app, title=_("生成成功"), message=msg, buttons=[_("是"), _("否")], icon_type="info", app_font=app.app_font)
                load_dialog.wait_window()
                if load_dialog.result == _("是"):
                    self.load_config_file(filepath=new_main_cfg_path)
            else:
                app.ui_manager.show_error_message(_("生成失败"), _("生成默认配置文件失败，请检查日志获取详细信息。"))
        except Exception as e:
            app.ui_manager.show_error_message(_("生成错误"), f"{_('生成默认配置文件时发生未知错误:')} {e}")

    def _show_about_window(self):
        """显示经过美化的“关于”窗口。(从 gui_app.py 移动)"""
        app = self.app
        if hasattr(app, 'about_window') and app.about_window is not None and app.about_window.winfo_exists():
            app.about_window.focus()
            return

        app.about_window = ctk.CTkToplevel(app)
        app.about_window.title(_("关于 FCGT"))
        app.about_window.geometry("850x700")
        app.about_window.transient(app)
        app.about_window.grab_set()

        def _on_about_window_close():
            if app.about_window:
                app.about_window.destroy()
                app.about_window = None

        app.about_window.protocol("WM_DELETE_WINDOW", _on_about_window_close)

        scrollable_frame = ctk.CTkScrollableFrame(app.about_window, corner_radius=0, fg_color="transparent")
        scrollable_frame.pack(expand=True, fill="both")
        scrollable_frame.grid_columnconfigure(0, weight=1)

        base_font_family = app.app_font.cget("family")
        title_font = ctk.CTkFont(family=base_font_family, size=20, weight="bold")
        header_font = ctk.CTkFont(family=base_font_family, size=16, weight="bold")
        text_font = ctk.CTkFont(family=base_font_family, size=14)
        version_font = ctk.CTkFont(family=base_font_family, size=12)
        link_font = ctk.CTkFont(family=base_font_family, size=14, underline=False)
        link_font_underline = ctk.CTkFont(family=base_font_family, size=14, underline=True)

        header_frame = ctk.CTkFrame(scrollable_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        header_frame.grid_columnconfigure(1, weight=1)

        logo_label = ctk.CTkLabel(header_frame, text="", image=app.logo_image)
        logo_label.grid(row=0, column=0, rowspan=2, padx=(0, 15))

        title_label = ctk.CTkLabel(header_frame, text=_("友好棉花基因组工具包 (FCGT)"), font=title_font)
        title_label.grid(row=0, column=1, sticky="w")

        version_label = ctk.CTkLabel(header_frame, text=f"Version: {PKG_VERSION}", font=version_font, text_color="gray")
        version_label.grid(row=1, column=1, sticky="w")

        version_label = ctk.CTkLabel(header_frame, text=_('本软件遵守 Apache-2.0 license 开源协议'), font=version_font,
                                     text_color="gray")
        version_label.grid(row=2, column=1, sticky="w")

        def add_section_header(parent, title_text, top_pady=20):
            ctk.CTkLabel(parent, text=title_text, font=header_font).grid(row=parent.grid_size()[1], column=0,
                                                                         sticky="w", padx=20, pady=(top_pady, 5))
            ctk.CTkFrame(parent, height=2, fg_color="gray50").grid(row=parent.grid_size()[1], column=0, sticky="ew",
                                                                   padx=20)

        def add_section_content(parent, content_text):
            ctk.CTkLabel(parent, text=content_text, font=text_font, wraplength=780, justify="left").grid(
                row=parent.grid_size()[1], column=0, sticky="w", padx=25, pady=(5, 0))

        def create_hyperlink(parent, text, url):
            link_label = ctk.CTkLabel(parent, text=text, text_color=("#0000EE", "#ADD8E6"), cursor="hand2",
                                      font=link_font)
            link_label.bind("<Button-1>", lambda e: webbrowser.open_new(url))
            link_label.bind("<Enter>", lambda e: link_label.configure(font=link_font_underline))
            link_label.bind("<Leave>", lambda e: link_label.configure(font=link_font))
            return link_label

        add_section_header(scrollable_frame, _("开发与致谢"))
        dev_frame = ctk.CTkFrame(scrollable_frame, fg_color="transparent")
        dev_frame.grid(row=scrollable_frame.grid_size()[1], column=0, sticky="ew", padx=25, pady=5)
        dev_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(dev_frame, text=_("作者:"), font=text_font).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(dev_frame, text="PureAmaya", font=text_font).grid(row=0, column=1, sticky="w", padx=10)

        ctk.CTkLabel(dev_frame, text=_("致谢:"), font=text_font).grid(row=1, column=0,
                                                                      sticky="w", pady=(5, 0))
        ctk.CTkLabel(dev_frame, text=_("开源社区和科研工作者"), font=text_font).grid(row=1, column=1, sticky="w",
                                                                                     padx=10, pady=(5, 0))

        add_section_header(scrollable_frame, _("版权与许可"))
        add_section_content(scrollable_frame,
                            (
                                "• requests (Apache-2.0 License)\n"
                                "• tqdm (MIT License)\n"
                                "• gffutils (MIT License)\n"
                                "• pandas (BSD 3-Clause License)\n"
                                "• PyYAML (MIT License)\n"
                                "• numpy (BSD License)\n"
                                "• pillow (MIT-CMU License)\n"
                                "• diskcache (Apache 2.0 License)\n"
                                "• openpyxl (MIT License)\n"
                                "• customtkinter (MIT License)\n"

                            ))

        add_section_header(scrollable_frame, _("在线资源与文档"))

        links_frame = ctk.CTkFrame(scrollable_frame, fg_color="transparent")
        links_frame.grid(row=scrollable_frame.grid_size()[1], column=0, sticky="ew", padx=25, pady=5)
        links_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(links_frame, text=_("项目仓库 (GitHub):"), font=text_font).grid(row=0, column=0, sticky="w")
        create_hyperlink(links_frame, PKG_PUBLISH_URL, PKG_PUBLISH_URL).grid(row=0, column=1, sticky="w", padx=10)
        ctk.CTkLabel(links_frame, text=_("在线帮助文档:"), font=text_font).grid(row=1, column=0, sticky="w",
                                                                                pady=(5, 0))
        create_hyperlink(links_frame, PKG_HELP_URL, PKG_HELP_URL).grid(row=1, column=1, sticky="w", padx=10,
                                                                       pady=(5, 0))

        ctk.CTkLabel(links_frame, text="CottonGen:", font=text_font).grid(row=2, column=0, sticky="w", pady=(5, 0))
        create_hyperlink(links_frame, "https://www.cottongen.org/",
                         "https://www.cottongen.org/").grid(row=2, column=1, sticky="w", padx=10, pady=(5, 0))

        genome_citations = (
            "• NAU-NBI_v1.1:\n Zhang et. al., Sequencing of allotetraploid cotton (Gossypium hirsutum L. acc. TM-1) provides a resource for fiber improvement. Nature Biotechnology. 33, 531–537. 2015\n\n"
            "• UTX-JGI-Interim-release_v1.1:\n  - Haas, B.J., Delcher, A.L., Mount, S.M., Wortman, J.R., Smith Jr, R.K., Jr., Hannick, L.I., Maiti, R., Ronning, C.M., Rusch, D.B., Town, C.D. et al. (2003) Improving the Arabidopsis genome annotation using maximal transcript alignment assemblies. http://nar.oupjournals.org/cgi/content/full/31/19/5654 [Nucleic Acids Res, 31, 5654-5666].\n  - Smit, AFA, Hubley, R & Green, P. RepeatMasker Open-3.0. 1996-2011.\n  - Yeh, R.-F., et al. (2001) Computational inference of homologous gene structures in the human genome. Genome Res. 11: 803-816.\n  - Salamov, A. A. and Solovyev, V. V. (2000). Ab initio gene finding in Drosophila genomic DNA. Genome Res 10, 516-22.\n\n"
            "• HAU_v1 / v1.1:\n Wang et al. Reference genome sequences of two cultivated allotetraploid cottons, Gossypium hirsutum and Gossypium barbadense. Nature genetics. 2018 Dec 03\n\n"
            "• ZJU-improved_v2.1_a1:\n Hu et al. Gossypium barbadense and Gossypium hirsutum genomes provide insights into the origin and evolution of allotetraploid cotton.\n\n"
            "• CRI_v1:\n Yang Z, Ge X, Yang Z, Qin W, Sun G, Wang Z, Li Z, Liu J, Wu J, Wang Y, Lu L, Wang P, Mo H, Zhang X, Li F. Extensive intraspecific gene order and gene structural variations in upland cotton cultivars. Nature communications. 2019 Jul 05; 10(1):2989.\n\n"
            "• WHU_v1:\n Huang, G. et al., Genome sequence of Gossypium herbaceum and genome updates of Gossypium arboreum and Gossypium hirsutum provide insights into cotton A-genome evolution. Nature Genetics. 2020. doi.org/10.1038/s41588-020-0607-4\n\n"
            "• UTX_v2.1:\n Chen ZJ, Sreedasyam A, Ando A, Song Q, De Santiago LM, Hulse-Kemp AM, Ding M, Ye W, Kirkbride RC, Jenkins J, Plott C, Lovell J, Lin YM, Vaughn R, Liu B, Simpson S, Scheffler BE, Wen L, Saski CA, Grover CE, Hu G, Conover JL, Carlson JW, Shu S, Boston LB, Williams M, Peterson DG, McGee K, Jones DC, Wendel JF, Stelly DM, Grimwood J, Schmutz J. Genomic diversifications of five Gossypium allopolyploid species and their impact on cotton improvement. Nature genetics. 2020 Apr 20.\n\n"
            '• HAU_v2.0:\n Chang, Xing, Xin He, Jianying Li, Zhenping Liu, Ruizhen Pi, Xuanxuan Luo, Ruipeng Wang et al. "High-quality Gossypium hirsutum and Gossypium barbadense genome assemblies reveal the landscape and evolution of centromeres." Plant Communications 5, no. 2 (2024). doi.org/10.1016/j.xplc.2023.100722'
        )

        add_section_header(scrollable_frame, _("基因组引用文献"))
        add_section_content(scrollable_frame, genome_citations)

        add_section_header(scrollable_frame, _("免责声明"))
        add_section_content(scrollable_frame, _("上述基因组的数据下载均由用户执行，本工具仅进行通用的分析操作。"))

        close_button = ctk.CTkButton(scrollable_frame, text=_("关闭"), command=_on_about_window_close,
                                     font=app.app_font)
        close_button.grid(row=scrollable_frame.grid_size()[1], column=0, pady=30)


    def _open_online_help(self):
        """打开在线帮助文档。"""
        try:
            logger.info(_("正在浏览器中打开在线帮助文档..."))
            webbrowser.open(PKG_HELP_URL)
        except Exception as e:
            self.app.ui_manager.show_error_message(_("错误"), _("无法打开帮助链接: {}").format(e))

    def _save_ui_settings(self):
        """保存UI设置，现在只处理外观模式。"""
        app = self.app
        settings_path = os.path.join(os.getcwd(), "ui_settings.json")
        try:
            data_to_save = {"appearance_mode": app.ui_settings.get("appearance_mode", "System")}
            with open(settings_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4)
            logger.debug(_("外观模式设置已保存。"))
        except IOError as e:
            logger.error(f"{_('错误: 无法保存外观设置:')} {e}")

    # --- 任务启动与管理 ---

    def start_app_async_startup(self):
        """启动应用的异步加载流程。"""
        self.app.ui_manager._show_progress_dialog(title=_("图形界面启动中..."), message=_("正在初始化应用程序和加载配置，请稍候..."), on_cancel=None)
        threading.Thread(target=self._initial_load_thread, daemon=True).start()

    def _initial_load_thread(self):
        """后台加载线程。"""
        app = self.app
        loaded_config: Optional[MainConfig] = None
        genome_sources = None
        config_path_to_send = None
        try:
            default_config_path = "config.yml"
            if os.path.exists(default_config_path):
                app.message_queue.put(("progress", (10, _("加载配置文件..."))))
                config_path_to_send = os.path.abspath(default_config_path)
                loaded_config = load_config(config_path_to_send)
            if loaded_config:
                app.message_queue.put(("progress", (30, _("加载基因组源数据..."))))
                genome_sources = get_genome_data_sources(loaded_config, logger_func=logger.info)
            startup_data = {"config": loaded_config, "genome_sources": genome_sources, "config_path": config_path_to_send}
            app.message_queue.put(("startup_complete", startup_data))
        except Exception as e:
            error_message = f"{_('应用启动失败')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
            app.message_queue.put(("startup_failed", error_message))
        finally:
            app.message_queue.put(("hide_progress_dialog", None))

    def _start_task(self, task_name: str, target_func: Callable, kwargs: Dict[str, Any]):
        """启动一个后台任务的通用方法。"""
        app = self.app
        if app.active_task_name:
            app.ui_manager.show_warning_message(_("任务进行中"), f"{_('另一个任务')} '{app.active_task_name}' {_('正在运行，请稍候。')}")
            return
        app.ui_manager.update_button_states(is_task_running=True)
        app.active_task_name = task_name
        logger.info(f"{_(task_name)} {_('任务开始...')}")
        app.cancel_current_task_event.clear()
        app.ui_manager._show_progress_dialog(title=_(task_name), message=_("正在处理..."), on_cancel=app.cancel_current_task_event.set)
        kwargs['cancel_event'] = app.cancel_current_task_event
        kwargs['status_callback'] = self.gui_status_callback
        kwargs['progress_callback'] = self.gui_progress_callback
        threading.Thread(target=self._task_wrapper, args=(target_func, kwargs, task_name), daemon=True).start()

    def _task_wrapper(self, target_func, kwargs, task_name):
        """后台任务的包装器，用于捕获异常。"""
        try:
            result_data = target_func(**kwargs)
            if self.app.cancel_current_task_event.is_set():
                self.app.message_queue.put(("task_done", (False, task_name, "CANCELLED")))
            else:
                self.app.message_queue.put(("task_done", (True, task_name, result_data)))
        except Exception as e:
            detailed_error = f"{_('一个意外的严重错误发生')}: {e}\n--- TRACEBACK ---\n{traceback.format_exc()}"
            self.app.message_queue.put(("error", detailed_error))

    # --- 其他辅助方法 ---

    def _browse_file(self, entry_widget: Optional[ctk.CTkEntry], filetypes_list: list) -> Optional[str]:
        """打开文件选择对话框并填充到输入框。"""
        filepath = filedialog.askopenfilename(title=_("选择文件"), filetypes=filetypes_list)
        if filepath and entry_widget:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, filepath)
        return filepath

    def _browse_save_file(self, entry_widget: ctk.CTkEntry, filetypes_list: list):
        """打开文件保存对话框并填充到输入框。"""
        filepath = filedialog.asksaveasfilename(title=_("保存文件为"), filetypes=filetypes_list, defaultextension=filetypes_list[0][1].replace("*", ""))
        if filepath and entry_widget:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, filepath)

    def _browse_directory(self, entry_widget: ctk.CTkEntry):
        """打开目录选择对话框并填充到输入框。"""
        directory = filedialog.askdirectory(title=_("选择目录"))
        if directory and entry_widget:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, directory)

    def _auto_identify_genome_version(self, gene_input_textbox: ctk.CTkTextbox, target_assembly_var: ctk.StringVar):
        """通过基因ID列表自动识别基因组版本。"""
        current_text = gene_input_textbox.get("1.0", "end").strip()
        is_placeholder = any(current_text == _(ph) for ph in self.app.placeholders.values())
        if not current_text or is_placeholder:
            return
        gene_ids = [gene.strip() for gene in current_text.replace(",", "\n").splitlines() if gene.strip()]
        if not gene_ids or not self.app.genome_sources_data:
            if not self.app.genome_sources_data:
                logger.warning(_("警告: 基因组源数据未加载，无法自动识别基因组。"))
            return
        logger.info(_("正在尝试自动识别基因组版本..."))
        threading.Thread(target=self._identify_genome_thread, args=(gene_ids, target_assembly_var), daemon=True).start()

    def _identify_genome_thread(self, gene_ids, target_assembly_var):
        """在后台线程中识别基因组。"""
        try:
            identified_assembly_id = identify_genome_from_gene_ids(gene_ids, self.app.genome_sources_data, status_callback=logger.info)
            if identified_assembly_id:
                self.app.message_queue.put(("auto_identify_success", (target_assembly_var, identified_assembly_id)))
            else:
                self.app.message_queue.put(("auto_identify_fail", None))
        except Exception as e:
            self.app.message_queue.put(("auto_identify_error", str(e)))

    def gui_status_callback(self, message: str, level: str = "INFO"):
        """线程安全的回调函数，用于更新状态栏和日志。"""
        level_upper = level.upper()
        if level_upper == "ERROR":
            if self.error_dialog_lock.acquire(blocking=False):
                self.app.message_queue.put(("error", message))
        else:
            self.app.message_queue.put(("status", message))
        # Log to standard logger, which is captured by the UI queue handler
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(str(message))

    def gui_progress_callback(self, percentage: float, message: str):
        """进度回调函数。"""
        self.app.message_queue.put(("progress", (percentage, message)))