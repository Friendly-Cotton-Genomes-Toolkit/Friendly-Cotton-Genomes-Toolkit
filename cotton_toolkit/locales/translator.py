# 注意，使用该脚本需要以下的额外依赖。请自行安装：
# openai
# polib
# tenacity
# tqdm
import copy
import locale
# 使用样例：
# python translate_po.py /path/to/your/app.po -t "Japanese" -s "English" --threads 10 --rate-limit 60 --model "gpt-4"

# 参数说明：file：(必需) 你的 .po 文件路径。
# file：必需参数。您的源 .po 文件路径。
#
# -t, --target-langs：必需参数。一个或多个目标语言，用空格分开。如果语言名称包含空格，请用引号括起来，例如 "Simplified Chinese"。
#
# -s, --source-lang：源文件中的语言，默认为 English。
#
# --threads：并发线程数，默认为 5。提高此数值可以加快速度，但也会增加API请求频率。
#
# --rate-limit：每分钟API最大请求数，默认为 40。这是保护您API账号的“看门狗”。如果遇到API限速错误，可以适当调低此数值。
#
# --model：指定使用的OpenAI模型，默认为 gpt-4o-mini，性价比高。您也可以使用 gpt-4-turbo 等更强大的模型。
#
# --api-key：直接在命令行提供API密钥，不推荐在公共服务器上使用。
#
# --base-url：高级功能。用于指定非官方的API地址。例如，连接本地模型 http://localhost:1234/v1 或 Azure OpenAI 端点。
#
# --ui-lang：特色功能。手动指定脚本界面的显示语言。

import os
import sys
import threading
import queue
import time
import argparse
from tqdm import tqdm
try:
    import polib
    from openai import OpenAI, APITimeoutError, RateLimitError, APIConnectionError
    from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
except:
    raise RuntimeError('缺少额外依赖，需要自行安装！')


i18n = {
    'en': {
        'description': "Translate a .po file into multiple languages using the OpenAI API.",
        'help_file': "Path to the source .po file to be translated.",
        'help_target_langs': "One or more target languages, separated by spaces (e.g., Chinese French German).\nUse quotes for names with spaces, e.g., \"Simplified Chinese\".",
        'help_source_lang': "Source language (default: English).",
        'help_threads': "Number of concurrent threads (default: 5).",
        'help_rate_limit': "Maximum number of requests per minute (default: 40).",
        'help_model': "OpenAI model to use (default: gpt-4o-mini).",
        'help_api_key': "OpenAI API key. If not provided, reads from 'OPENAI_API_KEY' environment variable.",
        'help_base_url': "Custom OpenAI API endpoint address.",
        'help_ui_lang': "Set the display language of the script interface.",
        'error_api_key_not_found': "Error: OpenAI API key not found.",
        'error_file_not_found': "Error: File '{file}' not found.",
        'error_parse_po': "Error: Failed to parse PO file. Details: {e}",
        'info_loading_po': "Loading source PO file: {file}",
        'info_custom_endpoint': "Info: Using custom API Endpoint: {base_url}",
        'info_entries_found': "File loaded. Found {count} entries to translate/update.",
        'info_all_translated': "All entries are already translated or up-to-date. No action needed.",
        'proc_start_translation': "\n--- Starting translation to: {lang} ---",
        'proc_translating_lang': "Translating ({lang})",
        'warn_no_results': "Warning: Failed to get any translation results for language '{lang}'.",
        'ok_lang_saved': "✅ Successfully updated {count} entries for '{lang}'. File saved to: {output_file}",
        'error_lang_save': "❌ Error: Failed to save file for '{lang}'. Details: {e}",
        'ok_all_done': "\nAll translation tasks are complete!",
        'warn_retry': "\nWarning: Request failed, retrying attempt {num}... ({err})",
    },
    'ja': {
        'description': "OpenAI APIを使用して、.poファイルを複数の言語に翻訳します。",
        'help_file': "翻訳するソース.poファイルへのパス。",
        'help_target_langs': "一つ以上のターゲット言語をスペースで区切って指定します (例: Chinese French German)。\nスペースを含む言語名は引用符で囲んでください (例: \"Simplified Chinese\")。",
        'help_source_lang': "ソース言語 (デフォルト: English)。",
        'help_threads': "並行スレッド数 (デフォルト: 5)。",
        'help_rate_limit': "1分あたりの最大リクエスト数 (デフォルト: 40)。",
        'help_model': "使用するOpenAIモデル (デフォルト: gpt-4o-mini)。",
        'help_api_key': "OpenAI APIキー。指定しない場合は、環境変数 'OPENAI_API_KEY' から読み取ります。",
        'help_base_url': "カスタムOpenAI APIエンドポイントアドレス。",
        'help_ui_lang': "スクリプトインターフェースの表示言語を設定します。",
        'error_api_key_not_found': "エラー：OpenAI APIキーが見つかりません。",
        'error_file_not_found': "エラー：ファイル '{file}' が見つかりません。",
        'error_parse_po': "エラー：POファイルの解析に失敗しました。詳細：{e}",
        'info_loading_po': "ソースPOファイルを読み込み中：{file}",
        'info_custom_endpoint': "情報：カスタムAPIエンドポイントを使用中：{base_url}",
        'info_entries_found': "ファイルの読み込み完了。翻訳/更新が必要なエントリが{count}件見つかりました。",
        'info_all_translated': "すべてのエントリは既に翻訳済みか最新の状態です。操作は不要です。",
        'proc_start_translation': "\n--- {lang}への翻訳を開始します ---",
        'proc_translating_lang': "翻訳中 ({lang})",
        'warn_no_results': "警告：言語 '{lang}' の翻訳結果を取得できませんでした。",
        'ok_lang_saved': "✅ 言語 '{lang}' の{count}件のエントリを正常に更新しました。ファイル保存先：{output_file}",
        'error_lang_save': "❌ エラー：言語 '{lang}' のファイル保存中にエラーが発生しました。詳細：{e}",
        'ok_all_done': "\nすべての翻訳タスクが完了しました！",
        'warn_retry': "\n警告：リクエスト失敗、再試行{num}回目... ({err})",
    },
    'zh-CN': {
        'description': "使用 OpenAI API 将一个 .po 文件翻译成多种语言。",
        'help_file': "要翻译的源 .po 文件路径。",
        'help_target_langs': "一个或多个目标语言，用空格分隔 (例如: Chinese French German)。\n如果语言名称包含空格，请使用引号，例如 \"Simplified Chinese\"。",
        'help_source_lang': "源语言 (默认为 English)。",
        'help_threads': "并发线程数 (默认为 5)。",
        'help_rate_limit': "每分钟允许的最大请求数 (默认为 40)。",
        'help_model': "使用的 OpenAI 模型 (默认为 gpt-4o-mini)。",
        'help_api_key': "OpenAI API 密钥。如果未提供，则从环境变量 'OPENAI_API_KEY' 读取。",
        'help_base_url': "自定义 OpenAI API 的 endpoint 地址。",
        'help_ui_lang': "设置脚本界面的显示语言。",
        'error_api_key_not_found': "错误：未找到 OpenAI API 密钥。",
        'error_file_not_found': "错误：文件 '{file}' 不存在。",
        'error_parse_po': "错误：无法解析 PO 文件。详情: {e}",
        'info_loading_po': "正在加载源 PO 文件: {file}",
        'info_custom_endpoint': "提示：使用自定义 API Endpoint: {base_url}",
        'info_entries_found': "文件加载完成。共找到 {count} 个需要翻译/更新的条目。",
        'info_all_translated': "所有条目均已翻译或为最新状态。无需操作。",
        'proc_start_translation': "\n--- 开始翻译到: {lang} ---",
        'proc_translating_lang': "翻译中 ({lang})",
        'warn_no_results': "警告：未能为语言 '{lang}' 获取任何翻译结果。",
        'ok_lang_saved': "✅ 成功为 '{lang}' 更新 {count} 个条目，文件已保存到: {output_file}",
        'error_lang_save': "❌ 错误：为 '{lang}' 保存文件时发生错误: {e}",
        'ok_all_done': "\n所有翻译任务已完成！",
        'warn_retry': "\n警告：请求失败，正在进行第 {num} 次重试... ({err})",
    },
    'zh-TW': {
        'description': "使用 OpenAI API 將一個 .po 檔案翻譯成多種語言。",
        'help_file': "要翻譯的來源 .po 檔案路徑。",
        'help_target_langs': "一個或多個目標語言，用空格分隔 (例如: Chinese French German)。\n如果語言名稱包含空格，請使用引號，例如 \"Simplified Chinese\"。",
        'help_source_lang': "來源語言 (預設為 English)。",
        'help_threads': "並行執行緒數 (預設為 5)。",
        'help_rate_limit': "每分鐘允許的最大請求數 (預設為 40)。",
        'help_model': "使用的 OpenAI 模型 (預設為 gpt-4o-mini)。",
        'help_api_key': "OpenAI API 金鑰。如果未提供，則從環境變數 'OPENAI_API_KEY' 讀取。",
        'help_base_url': "自訂 OpenAI API 的 endpoint 位址。",
        'help_ui_lang': "設定腳本介面的顯示語言。",
        'error_api_key_not_found': "錯誤：未找到 OpenAI API 金鑰。",
        'error_file_not_found': "錯誤：檔案 '{file}' 不存在。",
        'error_parse_po': "錯誤：無法解析 PO 檔案。詳情: {e}",
        'info_loading_po': "正在載入來源 PO 檔案: {file}",
        'info_custom_endpoint': "提示：使用自訂 API Endpoint: {base_url}",
        'info_entries_found': "檔案載入完成。共找到 {count} 個需要翻譯/更新的條目。",
        'info_all_translated': "所有條目均已翻譯或為最新狀態。無需操作。",
        'proc_start_translation': "\n--- 開始翻譯至: {lang} ---",
        'proc_translating_lang': "翻譯中 ({lang})",
        'warn_no_results': "警告：未能為語言 '{lang}' 取得任何翻譯結果。",
        'ok_lang_saved': "✅ 成功為 '{lang}' 更新 {count} 個條目，檔案已儲存至: {output_file}",
        'error_lang_save': "❌ 錯誤：為 '{lang}' 儲存檔案時發生錯誤: {e}",
        'ok_all_done': "\n所有翻譯任務已完成！",
        'warn_retry': "\n警告：請求失敗，正在進行第 {num} 次重試... ({err})",
    }
}

STRINGS = {}


# ⭐ 新增：更智能的UI语言自动检测函数
def detect_best_ui_language():
    """Detects the system's locale and returns a supported language code."""
    try:
        # getlocale is more specific than getdefaultlocale
        lang_code = locale.getlocale(locale.LC_MESSAGES)[0] or locale.getdefaultlocale()[0]
        if not lang_code:
            return 'en'

        lang_lower = lang_code.lower()
        if lang_lower.startswith('zh'):
            if 'cn' in lang_lower or 'sg' in lang_lower:
                return 'zh-CN'
            if 'tw' in lang_lower or 'hk' in lang_lower or 'mo' in lang_lower:
                return 'zh-TW'
            return 'zh-CN'  # Default to Simplified for other 'zh' variants
        if lang_lower.startswith('ja'):
            return 'ja'
    except Exception:
        return 'en'  # Default to English on any error
    return 'en'


# --- 核心翻译函数 (无改动) ---
@retry(
    wait=wait_exponential(multiplier=1, min=4, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((APITimeoutError, RateLimitError, APIConnectionError, IOError)),
    before_sleep=lambda rs: print(STRINGS['warn_retry'].format(num=rs.attempt_number, err=rs.outcome.exception()))
)
def translate_text(client, text, target_lang, source_lang, model):
    if not text.strip(): return ""
    prompt = (f"Translate the following text for a software interface from {source_lang} to {target_lang}. "
              "Do not add any extra explanations, comments, or quotation marks. "
              "Only return the translated text. "
              "If the original text contains placeholders like %s, %d, or {{name}}, "
              "preserve them exactly as they are in the translation.\n\n"
              f"Original text:\n```\n{text}\n```")
    response = client.chat.completions.create(model=model, messages=[
        {"role": "system", "content": "You are a professional translator for software localization."},
        {"role": "user", "content": prompt}], temperature=0.3, max_tokens=2048, timeout=30)
    translation = response.choices[0].message.content.strip()
    if translation.startswith(('"', "'")) and translation.endswith(('"', "'")):
        translation = translation[1:-1]
    return translation


# --- 线程工作单元 (无改动) ---
def worker(task_queue, results_dict, client, target_lang, source_lang, model, pbar, rate_limit_delay):
    while True:
        try:
            entry = task_queue.get(timeout=1)
            if entry is None: break
            if entry.msgid:
                translated_msg = translate_text(client, entry.msgid, target_lang, source_lang, model)
                if translated_msg: results_dict[entry.msgid] = translated_msg
            pbar.update(1)
            task_queue.task_done()
            time.sleep(rate_limit_delay)
        except queue.Empty:
            break
        except Exception:
            continue


# --- 单语言翻译流程 (使用 STRINGS) ---
def translate_for_language(entries, client, target_lang, source_lang, model, threads, rate_limit):
    print(STRINGS['proc_start_translation'].format(lang=target_lang))
    task_queue, results, thread_list = queue.Queue(), {}, []
    rate_limit_delay = 60.0 / rate_limit
    desc = STRINGS['proc_translating_lang'].format(lang=target_lang)
    with tqdm(total=len(entries), desc=desc, ncols=100) as pbar:
        for _ in range(threads):
            thread = threading.Thread(target=worker, args=(
                task_queue, results, client, target_lang, source_lang, model, pbar, rate_limit_delay))
            thread.daemon = True
            thread.start()
            thread_list.append(thread)
        for entry in entries: task_queue.put(entry)
        task_queue.join()
        for _ in range(threads): task_queue.put(None)
        for thread in thread_list: thread.join()
    return results


# --- 主函数 ---
def main():
    global STRINGS

    # ⭐ 确定UI语言
    # 优先使用 --ui-lang 参数，否则自动检测
    lang_code = sys.argv[sys.argv.index('--ui-lang') + 1] if '--ui-lang' in sys.argv else detect_best_ui_language()
    STRINGS = i18n.get(lang_code, i18n['en'])

    # --- 使用加载好的语言文本来构建命令行解析器 ---
    parser = argparse.ArgumentParser(
        description=STRINGS['description'],
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("file", help=STRINGS['help_file'])
    parser.add_argument("-t", "--target-langs", nargs='+', required=True, help=STRINGS['help_target_langs'])
    parser.add_argument("-s", "--source-lang", default="English", help=STRINGS['help_source_lang'])
    parser.add_argument("--threads", type=int, default=5, help=STRINGS['help_threads'])
    parser.add_argument("--rate-limit", type=int, default=40, help=STRINGS['help_rate_limit'])
    parser.add_argument("--model", default="gpt-4o-mini", help=STRINGS['help_model'])
    parser.add_argument("--api-key", help=STRINGS['help_api_key'])
    parser.add_argument("--base-url", help=STRINGS['help_base_url'])
    # ⭐ 更新UI语言参数的选项
    parser.add_argument("--ui-lang", choices=['en', 'ja', 'zh-CN', 'zh-TW'], help=STRINGS['help_ui_lang'])

    args = parser.parse_args()

    # --- 后续逻辑使用 STRINGS 进行输出 ---
    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print(STRINGS['error_api_key_not_found'])
        sys.exit(1)
    if not os.path.exists(args.file):
        print(STRINGS['error_file_not_found'].format(file=args.file))
        sys.exit(1)

    client_args = {"api_key": api_key}
    if args.base_url:
        client_args["base_url"] = args.base_url
    client = OpenAI(**client_args)

    print(STRINGS['info_loading_po'].format(file=args.file))
    if args.base_url:
        print(STRINGS['info_custom_endpoint'].format(base_url=args.base_url))

    try:
        po_original = polib.pofile(args.file, encoding='utf-8', wrapwidth=0)
    except Exception as e:
        print(STRINGS['error_parse_po'].format(e=e))
        sys.exit(1)

    entries_to_translate = [e for e in po_original if not e.translated() and not e.obsolete]
    if not entries_to_translate:
        print(STRINGS['info_all_translated'])
        sys.exit(0)

    print(STRINGS['info_entries_found'].format(count=len(entries_to_translate)))

    for lang in args.target_langs:
        results = translate_for_language(entries_to_translate, client, lang, args.source_lang, args.model, args.threads,
                                         args.rate_limit)
        if not results:
            print(STRINGS['warn_no_results'].format(lang=lang))
            continue
        po_copy = copy.deepcopy(po_original)
        updated_count = 0
        for entry in po_copy:
            if entry.msgid in results:
                entry.msgstr = results[entry.msgid]
                if 'fuzzy' in entry.flags:
                    entry.flags.remove('fuzzy')
                updated_count += 1
        lang_code = lang.split()[0].lower()
        po_copy.metadata['Language'] = lang_code
        base, ext = os.path.splitext(args.file)
        output_file = f"{base}.{lang_code}{ext}"
        try:
            po_copy.save(output_file)
            print(STRINGS['ok_lang_saved'].format(count=updated_count, lang=lang, output_file=output_file))
        except Exception as e:
            print(STRINGS['error_lang_save'].format(lang=lang, e=e))
    print(STRINGS['ok_all_done'])


if __name__ == "__main__":
    main()