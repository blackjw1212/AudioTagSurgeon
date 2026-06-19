# -*- coding: utf-8 -*-
"""
cleaner.py — 核心文字外科手術（純函式，無 GUI / 無硬碟 IO）

職責：
  1. 以檔名第一個分隔符切分 [演出者] 與 [歌曲名稱]。
  2. 簡轉繁（台灣正體 s2twp）。
  3. 去雜訊：前導曲目編號、Live/版本標記、音質/來源標記、多餘空格與孤立符號。
  4. 產生安全的目標檔名。

設計原則：極簡。所有去雜訊規則集中在 NOISE_PATTERNS / LEADING_TRACK，
便於日後增修而不動主流程。
"""

import re
from dataclasses import dataclass

try:
    from opencc import OpenCC
except ImportError:  # pragma: no cover - 僅在未安裝套件時觸發
    OpenCC = None


# 分隔符：半形 - 與全形破折號變體，貼近真實檔名習慣。
_SPLIT_CHARS = ("-", "－", "—", "–")

# 前導曲目編號（套用於 Artist 段開頭）：如 "01.", "03 - ", "12、", "1)"。
# 關鍵：數字後「必須」緊跟分隔標點，避免把數字開頭的團名當編號刪掉
#       （否則 1K→K、2Cellos→Cellos、21 Savage→Savage、50 Cent→Cent）。
LEADING_TRACK = re.compile(r"^\s*\d{1,3}\s*[.\-_、)]\s*")

# 去雜訊規則表：依序套用於「標題」。集中於此便於擴充。
# 括號字元類：同時涵蓋半形 ( [ 【 與全形 （，以及對應的右括號。
# 注意：英文標記一律加 \b 詞界，避免吃掉單字內的子字串
#       （否則 Shape→Sh(ape)、Alive→A(live)、Discover→Dis(cover)、Wave→(wav)e）。
NOISE_PATTERNS = [
    # Live / 版本標記（含前置 + 與底線、半形/全形括號 / 方括號形式）
    re.compile(r"\s*[+＋]?\s*[\(\[【（]?\s*\blive\b\s*[\)\]】）]?\s*$", re.IGNORECASE),
    re.compile(r"\s*[+＋_]?\s*[\(\[【（]?\s*(?:修正版|修正|重製版|重制版|完整版|純音樂|纯音乐)\s*[\)\]】）]?\s*", re.IGNORECASE),
    re.compile(r"\s*[\(\[【（]?\s*\b(?:remix|remaster(?:ed)?|cover|acoustic|inst(?:rumental)?)\b\s*[\)\]】）]?\s*", re.IGNORECASE),
    # 音質 / 來源標記
    re.compile(r"\s*[\(\[【（]?\s*\b(?:320k|320kbps|128k|hq|hd|flac|mp3|wav|ape)\b\s*[\)\]】）]?\s*", re.IGNORECASE),
    re.compile(r"\s*[\(\[【（]?\s*(?:官方版|官方|現場版|现场版|無損|无损|高音質|高音质|KTV|MV|伴奏|DJ版)\s*[\)\]】）]?\s*", re.IGNORECASE),
]

# 收尾：壓縮多餘空白
_MULTISPACE = re.compile(r"\s{2,}")
# 收尾：移除字串前後孤立的雜質符號
_EDGE_SYMBOLS = re.compile(r"^[\s+＋_\-－—–·•|]+|[\s+＋_\-－—–·•|]+$")

# Windows 檔名非法字元
_ILLEGAL_FS = re.compile(r'[\\/:*?"<>|]')


_cc_singleton = None


def _get_converter():
    """惰性建立 OpenCC('s2twp') 單例。"""
    global _cc_singleton
    if _cc_singleton is None:
        if OpenCC is None:
            raise RuntimeError(
                "未安裝 opencc-python-reimplemented，請先 pip install -r requirements.txt"
            )
        _cc_singleton = OpenCC("s2twp")
    return _cc_singleton


def to_traditional(text):
    """簡體 → 台灣正體（含慣用語）。"""
    if not text:
        return text
    return _get_converter().convert(text)


@dataclass
class ParseResult:
    original_stem: str   # 原始檔名（不含副檔名）
    ext: str             # 副檔名（含點，原樣保留大小寫）
    artist: str          # 清理後演出者
    title: str           # 清理後歌曲名稱
    parsable: bool       # 是否成功切分


def _find_split_index(stem):
    """回傳第一個分隔符的索引；找不到回傳 -1。"""
    indices = [stem.find(c) for c in _SPLIT_CHARS]
    indices = [i for i in indices if i != -1]
    return min(indices) if indices else -1


def _denoise_title(title):
    """套用去雜訊規則表 + 收尾清理。"""
    for pat in NOISE_PATTERNS:
        title = pat.sub(" ", title)
    title = _MULTISPACE.sub(" ", title)
    title = _EDGE_SYMBOLS.sub("", title)
    return title.strip()


def _clean_artist(artist):
    """剃除前導曲目編號 + 收尾清理。"""
    artist = LEADING_TRACK.sub("", artist)
    artist = _MULTISPACE.sub(" ", artist)
    artist = _EDGE_SYMBOLS.sub("", artist)
    return artist.strip()


def parse_filename(stem, ext=""):
    """
    解析單一檔名（不含副檔名）為 ParseResult。

    流程：切分 -> 簡轉繁 -> 去雜訊。
    找不到分隔符時 parsable=False，artist/title 留空（不修改該檔）。
    """
    idx = _find_split_index(stem)
    if idx == -1:
        return ParseResult(original_stem=stem, ext=ext, artist="", title="", parsable=False)

    raw_artist = stem[:idx]
    raw_title = stem[idx + 1:]

    # 先簡轉繁，再以繁體形式去雜訊（標記多為英文或中文，順序安全）。
    artist = _clean_artist(to_traditional(raw_artist))
    title = _denoise_title(to_traditional(raw_title))

    # 清理後若任一段為空，視為無法可靠解析。
    parsable = bool(artist) and bool(title)
    return ParseResult(
        original_stem=stem,
        ext=ext,
        artist=artist,
        title=title,
        parsable=parsable,
    )


def resolve(stem, ext, tag_artist=None, tag_title=None):
    """
    決定單一檔案的演出者/歌曲名稱來源（內建標籤優先）。

    - 若內嵌標籤的 artist 與 title 皆有值 → 以標籤為準，套用簡轉繁 + 去雜訊。
      （例如標籤 `说爱你 (Live)` → `說愛你`；歌手名 `A-Lin` 完整保留不被切分破壞。）
    - 否則回退到檔名解析 `parse_filename`。
    純函式、無 IO，便於單元測試。
    """
    if tag_artist and tag_title:
        artist = _clean_artist(to_traditional(tag_artist))
        title = _denoise_title(to_traditional(tag_title))
        if artist and title:
            return ParseResult(
                original_stem=stem,
                ext=ext,
                artist=artist,
                title=title,
                parsable=True,
            )
    return parse_filename(stem, ext)


def safe_component(text):
    """將單一檔名片段中的非法字元替換為全形近似字，避免重命名失敗。"""
    replacements = {
        "\\": "＼", "/": "／", ":": "：", "*": "＊",
        "?": "？", '"': "＂", "<": "＜", ">": "＞", "|": "｜",
    }
    return _ILLEGAL_FS.sub(lambda m: replacements[m.group(0)], text)


def build_target_name(artist, title, ext):
    """組合最終實體檔名：'演出者 - 歌曲名稱.副檔名'（含非法字元防護）。"""
    return f"{safe_component(artist)} - {safe_component(title)}{ext}"
