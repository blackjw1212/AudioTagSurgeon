# -*- coding: utf-8 -*-
"""
app.py — AudioTagSurgeon Tkinter GUI

流程：選擇/拖入資料夾 -> 深度掃描 .mp3/.flac -> 預覽對照表 -> 確認修改才寫硬碟。
未點「確認修改」前，絕不對硬碟做任何變更。
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cleaner
import tagger

# 拖放為選用功能：取得不到 tkinterdnd2 時退化為純按鈕模式。
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

AUDIO_EXTS = (".mp3", ".flac")

# 狀態文字
ST_PENDING = "待修改"
ST_UNPARSABLE = "無法解析"
ST_DONE = "✓ 已完成"
ST_CONFLICT = "✗ 衝突"
ST_ERROR = "✗ 錯誤"


class AudioTagSurgeonApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AudioTagSurgeon — 音訊標籤外科手術工具")
        self.root.geometry("980x560")

        # rows: 每列 dict {path, result(ParseResult), status, tree_id}
        self.rows = []

        self._build_widgets()

    # ---------- UI 建構 ----------
    def _build_widgets(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")

        ttk.Button(top, text="選擇資料夾", command=self.on_pick_folder).pack(side="left")
        ttk.Button(top, text="加入檔案", command=self.on_add_files).pack(side="left", padx=(6, 0))
        hint = "（可拖曳資料夾或音訊檔到視窗）" if _DND_AVAILABLE else "（未安裝 tkinterdnd2，拖放停用）"
        ttk.Label(top, text=hint).pack(side="left", padx=8)

        self.folder_var = tk.StringVar(value="尚未選擇資料夾")
        ttk.Label(top, textvariable=self.folder_var, foreground="#555").pack(side="left", padx=8)

        # 對照表
        mid = ttk.Frame(self.root, padding=(8, 0))
        mid.pack(fill="both", expand=True)

        cols = ("sel", "original", "artist", "title", "preview", "status")
        headers = {
            "sel": "修改",
            "original": "原始檔名",
            "artist": "演出者",
            "title": "歌曲名稱",
            "preview": "預覽 (演出者 - 歌曲名稱)",
            "status": "狀態",
        }
        widths = {"sel": 44, "original": 280, "artist": 130, "title": 170, "preview": 270, "status": 90}

        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="none")
        for c in cols:
            self.tree.heading(c, text=headers[c])
            self.tree.column(c, width=widths[c], anchor="center" if c == "sel" else "w")
        # 點「修改」欄標題 = 全選/全不選；點各列的「修改」欄 = 切換單列
        self.tree.heading("sel", command=self.on_toggle_all)
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.tag_configure("unparsable", foreground="#999")
        self.tree.tag_configure("done", foreground="#2a7")
        self.tree.tag_configure("bad", foreground="#c33")

        vsb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 底部
        bottom = ttk.Frame(self.root, padding=8)
        bottom.pack(fill="x")
        self.summary_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.summary_var).pack(side="left")
        self.confirm_btn = ttk.Button(bottom, text="確認修改", command=self.on_confirm, state="disabled")
        self.confirm_btn.pack(side="right")

        # 註冊拖放（僅當視窗為 TkinterDnD 根視窗時）
        if _DND_AVAILABLE and hasattr(self.root, "drop_target_register"):
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self.on_drop)

    # ---------- 事件 ----------
    def on_pick_folder(self):
        folder = filedialog.askdirectory(title="選擇要整理的資料夾")
        if folder:
            self.load_folder(folder)

    def on_add_files(self):
        paths = filedialog.askopenfilenames(
            title="選擇要加入的音訊檔",
            filetypes=[("音訊檔", "*.mp3 *.flac"), ("所有檔案", "*.*")],
        )
        audio = [p for p in paths if p.lower().endswith(AUDIO_EXTS)]
        if audio:
            self.add_paths(audio)
        elif paths:
            messagebox.showwarning("提示", "僅支援 .mp3 與 .flac 檔案。")

    def on_drop(self, event):
        # event.data 可能含大括號包覆與多個路徑；資料夾與音訊檔都接受。
        paths = self.root.tk.splitlist(event.data)
        dirs = [p for p in paths if os.path.isdir(p)]
        files = [p for p in paths if os.path.isfile(p) and p.lower().endswith(AUDIO_EXTS)]

        if files:
            # 拖入含檔案 → 附加模式（資料夾內容一併附加）
            for d in dirs:
                files.extend(self._scan_folder(d))
            self.add_paths(files)
        elif dirs:
            # 只拖入資料夾 → 維持原行為：重新載入第一個資料夾
            self.load_folder(dirs[0])
        else:
            messagebox.showwarning("提示", "請拖入資料夾或 .mp3 / .flac 檔案。")

    def _scan_folder(self, folder):
        """深度掃描資料夾，回傳音訊檔路徑清單。無法存取的子資料夾略過並警告。"""
        files = []
        scan_errors = []

        def _on_walk_error(err):
            # 權限不足／路徑失效的資料夾：記錄後略過，不中斷整體掃描。
            scan_errors.append(err)

        for dirpath, _dirs, filenames in os.walk(folder, onerror=_on_walk_error):
            for name in filenames:
                if name.lower().endswith(AUDIO_EXTS):
                    files.append(os.path.join(dirpath, name))
        if scan_errors:
            messagebox.showwarning(
                "掃描警告",
                f"有 {len(scan_errors)} 個資料夾無法存取（權限或路徑問題），已略過。",
            )
        return files

    def load_folder(self, folder):
        """深度掃描資料夾並重建預覽表。此步驟不修改任何檔案。"""
        self.folder_var.set(folder)
        self.tree.delete(*self.tree.get_children())
        self.rows = []

        files = self._scan_folder(folder)
        if not files:
            self._refresh_summary()
            self.confirm_btn.config(state="disabled")
            messagebox.showinfo("掃描結果", "此資料夾（含子資料夾）找不到 .mp3 或 .flac 檔案。")
            return
        self.add_paths(files)

    def add_paths(self, paths):
        """附加音訊檔到預覽表（自動去重）。此步驟不修改任何檔案。"""
        existing = {os.path.normcase(os.path.abspath(r["path"])) for r in self.rows}
        for path in sorted(paths):
            key = os.path.normcase(os.path.abspath(path))
            if key in existing:
                continue
            existing.add(key)
            stem, ext = os.path.splitext(os.path.basename(path))
            try:
                # 內建標籤優先：先讀檔內 artist/title，缺失時才回退檔名解析。
                tag_artist, tag_title = tagger.read_tags(path)
                result = cleaner.resolve(stem, ext, tag_artist, tag_title)
            except Exception:  # noqa: BLE001 - 單檔讀取失敗不應中斷整批載入
                result = cleaner.resolve(stem, ext, None, None)
            self._add_row(path, result)

        self._refresh_summary()
        # 只要有可修改項就啟用按鈕。
        has_actionable = any(r["result"].parsable for r in self.rows)
        self.confirm_btn.config(state="normal" if has_actionable else "disabled")

    def _add_row(self, path, result):
        if result.parsable:
            # 預覽欄只顯示「演出者 - 歌曲名稱」，不含副檔名（重命名時才補上真實副檔名）。
            preview = f"{result.artist} - {result.title}"
            status = ST_PENDING
            tags = ()
            selected = True
            sel_char = "☑"
        else:
            preview = "—"
            status = ST_UNPARSABLE
            tags = ("unparsable",)
            selected = False
            sel_char = "—"

        tree_id = self.tree.insert(
            "", "end",
            values=(sel_char, result.original_stem + result.ext,
                    result.artist, result.title, preview, status),
            tags=tags,
        )
        self.rows.append({
            "path": path, "result": result, "status": status,
            "tree_id": tree_id, "selected": selected,
        })

    def on_toggle_all(self):
        """點「修改」欄標題：尚有未勾選者 → 全選；否則全不選。"""
        pending = [r for r in self.rows
                   if r["result"].parsable and r["status"] == ST_PENDING]
        if not pending:
            return
        target = not all(r["selected"] for r in pending)
        for row in pending:
            row["selected"] = target
            self._set_cell(row["tree_id"], "sel", "☑" if target else "☐")
        self._refresh_summary()

    def on_tree_click(self, event):
        """點擊「修改」欄切換該列勾選（僅限尚可修改的列）。"""
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        for row in self.rows:
            if row["tree_id"] == item:
                if row["result"].parsable and row["status"] == ST_PENDING:
                    row["selected"] = not row["selected"]
                    self._set_cell(item, "sel", "☑" if row["selected"] else "☐")
                    self._refresh_summary()
                return

    def on_confirm(self):
        actionable = [r for r in self.rows
                      if r["result"].parsable and r["status"] == ST_PENDING and r["selected"]]
        if not actionable:
            messagebox.showinfo("提示", "沒有勾選任何可寫入的項目。")
            return

        if not messagebox.askyesno("確認修改", f"即將寫入標籤並重命名 {len(actionable)} 個檔案，確定執行？"):
            return

        self.confirm_btn.config(state="disabled")
        for row in actionable:
            res = tagger.apply(row["path"], row["result"].artist, row["result"].title)
            if res.status == tagger.STATUS_OK:
                row["path"] = res.new_path
                row["status"] = ST_DONE
                self.tree.item(row["tree_id"], tags=("done",))
                new_name = os.path.basename(res.new_path)
                self._set_cell(row["tree_id"], "status", ST_DONE)
                self._set_cell(row["tree_id"], "original", new_name)
                self._set_cell(row["tree_id"], "sel", "✓")
            elif res.status == tagger.STATUS_CONFLICT:
                row["status"] = ST_CONFLICT
                self.tree.item(row["tree_id"], tags=("bad",))
                self._set_cell(row["tree_id"], "status", ST_CONFLICT)
            else:
                row["status"] = ST_ERROR
                self.tree.item(row["tree_id"], tags=("bad",))
                self._set_cell(row["tree_id"], "status", ST_ERROR)

        self._refresh_summary(done=True)
        messagebox.showinfo("完成", "已完成處理。請查看狀態欄。")

    # ---------- 工具 ----------
    def _set_cell(self, tree_id, col, value):
        cols = ("sel", "original", "artist", "title", "preview", "status")
        idx = cols.index(col)
        values = list(self.tree.item(tree_id, "values"))
        values[idx] = value
        self.tree.item(tree_id, values=values)

    def _refresh_summary(self, done=False):
        total = len(self.rows)
        pending = sum(1 for r in self.rows if r["result"].parsable)
        unparsable = total - pending
        if done:
            ok = sum(1 for r in self.rows if r["status"] == ST_DONE)
            bad = sum(1 for r in self.rows if r["status"] in (ST_CONFLICT, ST_ERROR))
            self.summary_var.set(f"共 {total} 檔｜成功 {ok}｜衝突/錯誤 {bad}｜無法解析 {unparsable}")
        else:
            checked = sum(1 for r in self.rows
                          if r["result"].parsable and r["status"] == ST_PENDING and r["selected"])
            self.summary_var.set(
                f"共 {total} 檔｜已勾選 {checked}/{pending}｜無法解析 {unparsable}")


def main():
    root = TkinterDnD.Tk() if _DND_AVAILABLE else tk.Tk()
    AudioTagSurgeonApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
