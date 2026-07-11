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

# 首選切分：前後有空白的破折號（「A-Lin - 歌名」不會被切壞）；無則退回第一個裸分隔符。
_SPACED_SPLIT = re.compile(r"\s[-－—–]\s")

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

# 標籤垃圾 token：如來源軟體殘留的色碼 #0000FF（含其前置分隔符一併去除）。
# 限定 6~8 位十六進位，避免誤傷 #1、#Beautiful 這類正當標題。
_JUNK_TOKENS = re.compile(r"\s*[/／,;，；&＆]?\s*#[0-9A-Fa-f]{6,8}\b")

# 收尾：壓縮多餘空白
_MULTISPACE = re.compile(r"\s{2,}")
# 收尾：移除字串前後孤立的雜質符號
_EDGE_SYMBOLS = re.compile(r"^[\s+＋_\-－—–·•|]+|[\s+＋_\-－—–·•|]+$")

# Windows 檔名非法字元
_ILLEGAL_FS = re.compile(r'[\\/:*?"<>|]')


_cc_singleton = None
_cc_t2s_singleton = None


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


def _get_t2s():
    """惰性建立 OpenCC('t2s') 單例（僅用於偵測文字是否已含繁體字）。"""
    global _cc_t2s_singleton
    if _cc_t2s_singleton is None:
        _cc_t2s_singleton = OpenCC("t2s")
    return _cc_t2s_singleton


def to_traditional(text):
    """
    簡體 → 台灣正體（含慣用語）。

    冪等性防護：若欄位已含繁體專有字（t2s 轉換會改變它），視為已是繁體、
    原樣返回。否則 OpenCC 的歧義字會被二次轉換而出錯——
    例如姓氏「范」：從簡體『范玮琪』詞組轉換正確保留『范瑋琪』，
    但把已是繁體的『范瑋琪』再轉會錯誤變成『範瑋琪』。
    """
    if not text:
        return text
    if _get_t2s().convert(text) != text:
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


def _split_stem(stem):
    """切分檔名為兩半。優先「空白-空白」形式，退回第一個裸分隔符；無則 None。"""
    m = _SPACED_SPLIT.search(stem)
    if m:
        return stem[:m.start()], stem[m.end():]
    idx = _find_split_index(stem)
    if idx == -1:
        return None
    return stem[:idx], stem[idx + 1:]


# 比對用正規化：去除空白、常見分隔/裝飾符，供檔名兩半與標籤交叉比對。
_MATCH_STRIP = re.compile(r"[\s&＆/／,;，；、·×.．\-－—–_+＋()\[\]（）【】'’!！?？]+")


def _norm_for_match(text):
    """比對鍵：簡轉繁 -> 去垃圾 token -> 去分隔符/標點 -> casefold。"""
    text = to_traditional(text)
    text = _JUNK_TOKENS.sub("", text)
    return _MATCH_STRIP.sub("", text).casefold()


def _match(a, b):
    """檔名片段與標籤是否指同一內容（相等或含入，短字串門檻防誤判）。"""
    na, nb = _norm_for_match(a), _norm_for_match(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(shorter) >= 2 and shorter in longer


def _denoise_title(title):
    """套用去雜訊規則表 + 垃圾 token + 收尾清理。"""
    for pat in NOISE_PATTERNS:
        title = pat.sub(" ", title)
    title = _JUNK_TOKENS.sub("", title)
    title = _MULTISPACE.sub(" ", title)
    title = _EDGE_SYMBOLS.sub("", title)
    return title.strip()


def _clean_artist(artist):
    """剃除前導曲目編號 + 垃圾 token + 收尾清理。"""
    artist = LEADING_TRACK.sub("", artist)
    artist = _JUNK_TOKENS.sub("", artist)
    artist = _MULTISPACE.sub(" ", artist)
    artist = _EDGE_SYMBOLS.sub("", artist)
    return artist.strip()


def parse_filename(stem, ext=""):
    """
    解析單一檔名（不含副檔名）為 ParseResult。

    流程：切分 -> 簡轉繁 -> 去雜訊。
    找不到分隔符時 parsable=False，artist/title 留空（不修改該檔）。
    """
    parts = _split_stem(stem)
    if parts is None:
        return ParseResult(original_stem=stem, ext=ext, artist="", title="", parsable=False)

    raw_artist, raw_title = parts

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


def _prefer_tag_form(fn_value, tag_raw, cleaner_fn):
    """
    檔名值與標籤值只差「檔名安全替換字元」（如 ／ vs /）時，優先用標籤原字，
    避免全形替換字被寫回標籤污染資料；實質不同（如 & vs /）仍以檔名為準。
    """
    tag_clean = cleaner_fn(to_traditional(tag_raw))
    if tag_clean and tag_clean != fn_value and safe_component(tag_clean) == safe_component(fn_value):
        return tag_clean
    return fn_value


def _from_tags(stem, ext, tag_artist, tag_title):
    """以標籤為來源建 ParseResult；清理後任一欄為空回 None。"""
    artist = _clean_artist(to_traditional(tag_artist))
    title = _denoise_title(to_traditional(tag_title))
    if artist and title:
        return ParseResult(stem, ext, artist, title, True)
    return None


def resolve(stem, ext, tag_artist=None, tag_title=None):
    """
    決定單一檔案的演出者/歌曲名稱（檔名優先，標籤交叉校驗）。

    1. 檔名切成兩半後與標籤比對：
       - 正序吻合（前半≈標籤演出者、後半≈標籤歌名）→ 用「檔名」內容
         （檔名寫 L8R&阿林 就維持 &，不被標籤的 / 蓋掉）。
       - 反序吻合 → 檔名是「歌名 - 演出者」順序，對調校正
         （Zombie - The Cranberries → 演出者 The Cranberries）。
       - 皆不吻合 → 檔名切分不可信（如 A-Lin 被裸切），改用標籤。
    2. 檔名無分隔符 → 用標籤。
    3. 標籤缺失 → 純檔名解析；兩者都失敗 → 無法解析。
    純函式、無 IO，便於單元測試。
    """
    parts = _split_stem(stem)
    has_tags = bool(tag_artist) and bool(tag_title)

    if parts is not None:
        raw_a, raw_b = parts
        if has_tags:
            if _match(raw_a, tag_artist) and _match(raw_b, tag_title):
                artist = _clean_artist(to_traditional(raw_a))
                title = _denoise_title(to_traditional(raw_b))
                if artist and title:
                    artist = _prefer_tag_form(artist, tag_artist, _clean_artist)
                    title = _prefer_tag_form(title, tag_title, _denoise_title)
                    return ParseResult(stem, ext, artist, title, True)
            elif _match(raw_a, tag_title) and _match(raw_b, tag_artist):
                artist = _clean_artist(to_traditional(raw_b))
                title = _denoise_title(to_traditional(raw_a))
                if artist and title:
                    artist = _prefer_tag_form(artist, tag_artist, _clean_artist)
                    title = _prefer_tag_form(title, tag_title, _denoise_title)
                    return ParseResult(stem, ext, artist, title, True)
            result = _from_tags(stem, ext, tag_artist, tag_title)
            if result:
                return result
        return parse_filename(stem, ext)

    if has_tags:
        result = _from_tags(stem, ext, tag_artist, tag_title)
        if result:
            return result
    return ParseResult(stem, ext, "", "", False)


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
