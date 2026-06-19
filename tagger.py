# -*- coding: utf-8 -*-
"""
tagger.py — 寫入內建 Tag 與實體重命名（唯一動硬碟的模組）

外科手術式原則：
  - MP3 只設 EasyID3 的 artist / title，不碰其他 frame 與音訊資料。
  - FLAC 只設 Vorbis Comment 的 artist / title。
  - 重命名同目錄進行；目標已存在則跳過（不覆蓋）。
"""

import os
from dataclasses import dataclass

from mutagen.flac import FLAC
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError

from cleaner import build_target_name


# apply() 的結果狀態
STATUS_OK = "ok"
STATUS_CONFLICT = "conflict"
STATUS_ERROR = "error"


@dataclass
class ApplyResult:
    status: str          # STATUS_OK / STATUS_CONFLICT / STATUS_ERROR
    new_path: str        # 成功時為新路徑，否則為原路徑
    message: str = ""    # 錯誤或衝突說明


def read_tags(path):
    """讀取既有內嵌 artist / title。讀不到或無此欄位回傳 (None, None)。"""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".mp3":
            audio = EasyID3(path)
        elif ext == ".flac":
            audio = FLAC(path)
        else:
            return (None, None)
    except Exception:  # noqa: BLE001 - 無標頭 / 損毀等一律視為無標籤
        return (None, None)

    artist = audio.get("artist")
    title = audio.get("title")
    artist = artist[0] if artist else None
    title = title[0] if title else None
    return (artist, title)


def write_tags(path, artist, title):
    """依副檔名寫入 artist / title 內建標籤。只動這兩個欄位。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".mp3":
        try:
            audio = EasyID3(path)
        except ID3NoHeaderError:
            # 檔案尚無 ID3 標頭，建立一個空的再寫入。
            audio = EasyID3()
        audio["artist"] = artist
        audio["title"] = title
        audio.save(path)
    elif ext == ".flac":
        audio = FLAC(path)
        audio["artist"] = artist
        audio["title"] = title
        audio.save()
    else:
        raise ValueError(f"不支援的副檔名：{ext}")


def rename_file(path, target_name):
    """同目錄重命名。目標已存在（且非自身）則回傳 None 表示衝突。"""
    directory = os.path.dirname(path)
    new_path = os.path.join(directory, target_name)

    # 與原檔名相同（僅大小寫差異或無變化）時直接視為成功。
    if os.path.normcase(os.path.abspath(new_path)) == os.path.normcase(os.path.abspath(path)):
        return path

    if os.path.exists(new_path):
        return None  # 衝突，不覆蓋

    os.rename(path, new_path)
    return new_path


def apply(path, artist, title):
    """
    對單一檔案執行：先寫 Tag、後重命名。
    回傳 ApplyResult。任何例外都被捕捉為 STATUS_ERROR，不中斷批次。
    """
    try:
        write_tags(path, artist, title)
    except Exception as exc:  # noqa: BLE001 - 將錯誤回報給 GUI，不讓單檔失敗中斷整批
        return ApplyResult(status=STATUS_ERROR, new_path=path, message=f"寫入標籤失敗：{exc}")

    ext = os.path.splitext(path)[1]
    target_name = build_target_name(artist, title, ext)

    try:
        new_path = rename_file(path, target_name)
    except Exception as exc:  # noqa: BLE001
        return ApplyResult(status=STATUS_ERROR, new_path=path, message=f"重命名失敗：{exc}")

    if new_path is None:
        return ApplyResult(
            status=STATUS_CONFLICT,
            new_path=path,
            message=f"目標檔名已存在，已跳過：{target_name}",
        )

    return ApplyResult(status=STATUS_OK, new_path=new_path)
