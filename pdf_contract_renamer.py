# -*- coding: utf-8 -*-
"""
PDF 销售合同批量重命名工具
自动识别 PDF 中的合同编号，并将文件重命名为合同编号。
完全离线运行，无需联网。

使用方式:
  - 双击运行: 打开 GUI 界面
  - 命令行:   python pdf_contract_renamer.py "C:\合同文件夹"
"""

import os
import re
import sys
import logging
import tempfile

from PIL import Image
import pymupdf
from rapidocr_onnxruntime import RapidOCR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
_logger = logging.getLogger(__name__)


def _get_base_path() -> str:
    """获取资源文件的基础路径（兼容 PyInstaller 打包后的环境）。"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

# =========================================================
#  合同编号格式配置（根据实际情况修改）
# =========================================================
# 当前格式: 6位数字-4位数字（如 190816-2501）
# 如果你的编号是其他格式，只需修改下面的正则表达式
CONTRACT_NO_PATTERN = re.compile(r'(\d{6}-\d{4})')

# 用于定位合同编号所在行的关键词
CONTRACT_KEYWORDS = ['合同编号', 'Contract No', 'ContractNo', '合同号']


# =========================================================
#  核心功能：PDF 合同编号提取
# =========================================================

def extract_contract_no(pdf_path: str, ocr_engine: RapidOCR) -> str | None:
    """从 PDF 中提取合同编号。

    优先尝试直接提取文字（非扫描件），失败后使用 OCR。

    Args:
        pdf_path: PDF 文件的完整路径
        ocr_engine: RapidOCR 实例

    Returns:
        合同编号字符串，未找到则返回 None
    """
    try:
        doc = pymupdf.open(pdf_path)
        page = doc[0]

        # 策略 1：直接提取文字（非扫描件）
        text = page.get_text()
        if text.strip():
            contract_no = _find_contract_no_in_text(text)
            if contract_no:
                doc.close()
                return contract_no

        # 策略 2：OCR 识别（扫描件）
        mat = pymupdf.Matrix(2, 2)  # 2x 放大提高识别率
        pix = page.get_pixmap(matrix=mat)

        # 使用系统临时目录，避免权限问题
        fd, temp_img = tempfile.mkstemp(suffix='.png', prefix='ocr_')
        os.close(fd)
        pix.save(temp_img)

        try:
            result, _ = ocr_engine(temp_img)
        finally:
            if os.path.exists(temp_img):
                os.remove(temp_img)

        doc.close()

        if not result:
            return None

        full_text = '\n'.join(str(line[1]) for line in result)
        return _find_contract_no_in_text(full_text)

    except Exception as e:
        _logger.error(f'处理 {pdf_path} 时出错: {e}')
        return None


def _find_contract_no_in_text(text: str) -> str | None:
    """在文本中查找合同编号。

    优先匹配含关键词的行，否则匹配全文第一个符合格式的编号。

    Args:
        text: 要搜索的文本

    Returns:
        合同编号字符串，未找到则返回 None
    """
    for line in text.split('\n'):
        has_keyword = any(kw in line for kw in CONTRACT_KEYWORDS)
        if has_keyword:
            match = CONTRACT_NO_PATTERN.search(line)
            if match:
                return match.group(1)

    match = CONTRACT_NO_PATTERN.search(text)
    if match:
        return match.group(1)

    return None


def batch_scan(folder: str, ocr_engine: RapidOCR) -> list[dict]:
    """扫描文件夹中所有 PDF 并提取合同编号。

    Args:
        folder: 文件夹路径
        ocr_engine: RapidOCR 实例

    Returns:
        包含扫描结果的字典列表
    """
    pdf_files = sorted(f for f in os.listdir(folder) if f.lower().endswith('.pdf'))
    results = []

    for i, filename in enumerate(pdf_files):
        pdf_path = os.path.join(folder, filename)
        _logger.info(f'[{i + 1}/{len(pdf_files)}] 识别: {filename}')

        contract_no = extract_contract_no(pdf_path, ocr_engine)
        ext = os.path.splitext(filename)[1]

        results.append({
            'original': filename,
            'contract_no': contract_no or '未识别',
            'new_name': f'{contract_no}{ext}' if contract_no else None,
            'folder': folder,
            'success': contract_no is not None,
        })

    return results


def do_rename(results: list[dict], dry_run: bool = False) -> tuple[int, list[str]]:
    """执行重命名。

    Args:
        results: batch_scan 返回的结果列表
        dry_run: 仅预览不实际重命名

    Returns:
        (成功数, 错误信息列表)
    """
    to_rename = [r for r in results if r['success']]

    # 检查重名冲突
    new_names = [r['new_name'] for r in to_rename]
    duplicates = {n for n in new_names if new_names.count(n) > 1}
    if duplicates:
        return 0, [f'新文件名重复: {", ".join(duplicates)}']

    renamed = 0
    errors = []

    for r in to_rename:
        src = os.path.join(r['folder'], r['original'])
        dst = os.path.join(r['folder'], r['new_name'])

        if os.path.exists(dst) and os.path.normcase(src) != os.path.normcase(dst):
            errors.append(f'{r["new_name"]} 已存在，跳过')
            continue

        if dry_run:
            print(f'  {r["original"]}  →  {r["new_name"]}')
            renamed += 1
        else:
            try:
                os.rename(src, dst)
                renamed += 1
                _logger.info(f'已重命名: {r["original"]} → {r["new_name"]}')
            except OSError as e:
                errors.append(f'{r["original"]}: {e}')

    return renamed, errors


# =========================================================
#  GUI 界面（tkinter）
# =========================================================

def run_gui():
    """启动 GUI 界面。"""
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    import threading

    class ContractRenamerApp:

        def __init__(self, root: tk.Tk):
            self.root = root
            self.root.title('PDF 合同批量重命名工具')
            self.root.geometry('820x580')
            self.root.minsize(700, 450)

            self.ocr_engine = None
            self.results: list[dict] = []
            self.folder_path = tk.StringVar()

            self._build_ui()

        def _build_ui(self):
            style = ttk.Style()
            style.configure('TButton', padding=4)

            # 顶部：文件夹选择
            top = ttk.Frame(self.root, padding=10)
            top.pack(fill=tk.X)

            ttk.Label(top, text='PDF 文件夹:').pack(side=tk.LEFT)
            ttk.Entry(top, textvariable=self.folder_path, width=50).pack(
                side=tk.LEFT, padx=5, fill=tk.X, expand=True
            )
            ttk.Button(top, text='选择文件夹', command=self._select_folder).pack(side=tk.LEFT, padx=2)
            self.scan_btn = ttk.Button(top, text='🔍 扫描识别', command=self._start_scan)
            self.scan_btn.pack(side=tk.LEFT, padx=2)

            # 提示
            hint = ttk.Frame(self.root, padding=(10, 0, 10, 5))
            hint.pack(fill=tk.X)
            ttk.Label(
                hint,
                text='合同编号格式: XXXXXX-XXXX（如 190816-2501）。'
                     '如格式不同请修改脚本中 CONTRACT_NO_PATTERN。',
                foreground='gray',
            ).pack(anchor=tk.W)

            # 表格
            table = ttk.Frame(self.root, padding=10)
            table.pack(fill=tk.BOTH, expand=True)

            cols = ('status', 'original', 'contract_no', 'new_name')
            self.tree = ttk.Treeview(table, columns=cols, show='headings', selectmode='extended')
            self.tree.heading('status', text='状态')
            self.tree.heading('original', text='原文件名')
            self.tree.heading('contract_no', text='识别合同编号')
            self.tree.heading('new_name', text='新文件名')
            self.tree.column('status', width=60, anchor=tk.CENTER)
            self.tree.column('original', width=230)
            self.tree.column('contract_no', width=140, anchor=tk.CENTER)
            self.tree.column('new_name', width=230)

            sb = ttk.Scrollbar(table, orient=tk.VERTICAL, command=self.tree.yview)
            self.tree.configure(yscrollcommand=sb.set)
            self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb.pack(side=tk.RIGHT, fill=tk.Y)

            # 底部
            bot = ttk.Frame(self.root, padding=10)
            bot.pack(fill=tk.X)

            self.progress = ttk.Progressbar(bot, mode='determinate')
            self.progress.pack(fill=tk.X, pady=(0, 8))

            self.status_label = ttk.Label(bot, text='请选择 PDF 所在文件夹，然后点击「扫描识别」')
            self.status_label.pack(side=tk.LEFT)

            self.rename_btn = ttk.Button(
                bot, text='✅ 执行重命名', command=self._do_rename, state=tk.DISABLED
            )
            self.rename_btn.pack(side=tk.RIGHT)

        def _select_folder(self):
            path = filedialog.askdirectory(title='选择包含 PDF 的文件夹')
            if path:
                self.folder_path.set(path)

        def _start_scan(self):
            folder = self.folder_path.get().strip()
            if not folder or not os.path.isdir(folder):
                messagebox.showwarning('提示', '请先选择一个有效的文件夹！')
                return
            self.scan_btn.config(state=tk.DISABLED)
            self.rename_btn.config(state=tk.DISABLED)
            self.tree.delete(*self.tree.get_children())
            self.results.clear()
            threading.Thread(target=self._scan_worker, args=(folder,), daemon=True).start()

        def _scan_worker(self, folder: str):
            if self.ocr_engine is None:
                self.root.after(0, lambda: self.status_label.config(
                    text='正在加载 OCR 引擎（首次较慢，请稍候）...'
                ))
                self.ocr_engine = RapidOCR()

            pdf_files = sorted(f for f in os.listdir(folder) if f.lower().endswith('.pdf'))
            total = len(pdf_files)

            if total == 0:
                self.root.after(0, lambda: self.status_label.config(text='该文件夹中没有找到 PDF 文件'))
                self.root.after(0, lambda: self.scan_btn.config(state=tk.NORMAL))
                return

            self.root.after(0, lambda: self.progress.config(maximum=total, value=0))
            ok = 0

            for i, fn in enumerate(pdf_files):
                self.root.after(0, lambda fn=fn, i=i: self.status_label.config(
                    text=f'正在识别 ({i + 1}/{total}): {fn}'
                ))
                pdf_path = os.path.join(folder, fn)
                cno = extract_contract_no(pdf_path, self.ocr_engine)
                ext = os.path.splitext(fn)[1]

                r = {
                    'original': fn,
                    'contract_no': cno or '未识别',
                    'new_name': f'{cno}{ext}' if cno else '—',
                    'folder': folder,
                    'success': cno is not None,
                }
                self.results.append(r)
                status = '✅' if cno else '❌'
                if cno:
                    ok += 1

                self.root.after(0, lambda r=r, s=status: self.tree.insert(
                    '', tk.END, values=(s, r['original'], r['contract_no'], r['new_name'])
                ))
                self.root.after(0, lambda i=i: self.progress.config(value=i + 1))

            fail = total - ok
            self.root.after(0, lambda: self.status_label.config(
                text=f'扫描完成！成功 {ok} 个，失败 {fail} 个'
            ))
            self.root.after(0, lambda: self.scan_btn.config(state=tk.NORMAL))
            if ok > 0:
                self.root.after(0, lambda: self.rename_btn.config(state=tk.NORMAL))

        def _do_rename(self):
            to_rename = [r for r in self.results if r['success']]
            if not to_rename:
                messagebox.showinfo('提示', '没有可重命名的文件')
                return

            new_names = [r['new_name'] for r in to_rename]
            dups = {n for n in new_names if new_names.count(n) > 1}
            if dups:
                messagebox.showwarning('重名冲突', f'以下新文件名重复:\n{", ".join(dups)}')
                return

            if not messagebox.askyesno(
                '确认重命名',
                f'即将重命名 {len(to_rename)} 个文件，是否继续？\n\n此操作不可撤销，建议先备份！'
            ):
                return

            renamed, errors = do_rename(to_rename)
            msg = f'成功重命名 {renamed} 个文件'
            if errors:
                msg += '\n\n以下文件出错:\n' + '\n'.join(errors)
            messagebox.showinfo('完成', msg)
            self.rename_btn.config(state=tk.DISABLED)

    # 高 DPI 适配 (Windows)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    ContractRenamerApp(root)
    root.mainloop()


# =========================================================
#  命令行模式
# =========================================================

def run_cli(folder: str):
    """命令行模式运行。"""
    if not os.path.isdir(folder):
        print(f'错误: 文件夹不存在 - {folder}')
        sys.exit(1)

    print(f'正在加载 OCR 引擎...')
    ocr_engine = RapidOCR()

    print(f'扫描文件夹: {folder}\n')
    results = batch_scan(folder, ocr_engine)

    # 打印结果
    print('\n' + '=' * 60)
    print(f'{"原文件名":<30} {"合同编号":<15} {"新文件名":<30}')
    print('-' * 60)

    ok = 0
    for r in results:
        status = '✅' if r['success'] else '❌'
        print(f'{status} {r["original"]:<28} {r["contract_no"]:<13} {r["new_name"] or "—":<28}')
        if r['success']:
            ok += 1

    print('=' * 60)
    print(f'共 {len(results)} 个文件，成功识别 {ok} 个\n')

    if ok == 0:
        print('没有可重命名的文件。')
        return

    # 预览
    print('即将执行以下重命名:')
    do_rename([r for r in results if r['success']], dry_run=True)

    answer = input('\n确认重命名？(y/n): ').strip().lower()
    if answer != 'y':
        print('已取消。')
        return

    renamed, errors = do_rename(results)
    print(f'\n完成！成功重命名 {renamed} 个文件。')
    if errors:
        print('错误:')
        for e in errors:
            print(f'  - {e}')


# =========================================================
#  入口
# =========================================================

def main():
    if len(sys.argv) > 1:
        run_cli(sys.argv[1])
    else:
        try:
            run_gui()
        except ImportError:
            print('错误: 当前环境不支持 GUI（缺少 tkinter）')
            print(f'请使用命令行模式: python {sys.argv[0]} <PDF文件夹路径>')
            sys.exit(1)


if __name__ == '__main__':
    main()
