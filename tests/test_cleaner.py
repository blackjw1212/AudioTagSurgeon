# -*- coding: utf-8 -*-
"""
test_cleaner.py — cleaner 純函式測試（不需音訊檔）

執行： python -m pytest tests/   或   python -m unittest tests.test_cleaner
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cleaner  # noqa: E402


class TestCleaner(unittest.TestCase):
    def test_spec_example(self):
        # 規格驗收範例：蔡依林-说爱你+(Live) -> 蔡依林 - 說愛你
        r = cleaner.parse_filename("蔡依林-说爱你+(Live)", ".mp3")
        self.assertTrue(r.parsable)
        self.assertEqual(r.artist, "蔡依林")
        self.assertEqual(r.title, "說愛你")
        self.assertEqual(cleaner.build_target_name(r.artist, r.title, r.ext), "蔡依林 - 說愛你.mp3")

    def test_leading_track_number(self):
        # 前導曲目編號應被剃除，並完成簡轉繁。
        r = cleaner.parse_filename("01.周杰伦-稻香", ".flac")
        self.assertTrue(r.parsable)
        self.assertEqual(r.artist, "周杰倫")
        self.assertEqual(r.title, "稻香")

    def test_no_separator(self):
        # 無分隔符 -> 無法解析，不修改。
        r = cleaner.parse_filename("無分隔符的檔名", ".mp3")
        self.assertFalse(r.parsable)
        self.assertEqual(r.artist, "")
        self.assertEqual(r.title, "")

    def test_fullwidth_dash(self):
        # 全形破折號也應能切分（並驗證簡轉繁：邓->鄧、丽->麗）。
        r = cleaner.parse_filename("邓丽君－漫步人生路", ".mp3")
        self.assertTrue(r.parsable)
        self.assertEqual(r.artist, "鄧麗君")
        self.assertEqual(r.title, "漫步人生路")

    def test_extra_spaces(self):
        # 多餘空格收斂。
        r = cleaner.parse_filename("  邓紫棋  -   泡沫  ", ".flac")
        self.assertTrue(r.parsable)
        self.assertEqual(r.artist, "鄧紫棋")
        self.assertEqual(r.title, "泡沫")

    def test_quality_marker(self):
        # 音質/來源標記應被剃除。
        r = cleaner.parse_filename("五月天-倔强 320K", ".mp3")
        self.assertTrue(r.parsable)
        self.assertEqual(r.artist, "五月天")
        self.assertEqual(r.title, "倔強")

    def test_junk_color_code_stripped(self):
        # 檔名優先：檔名與標籤（去垃圾色碼後）吻合 → 用檔名內容，維持 &。
        r = cleaner.resolve("L8R&阿林 - 窃爱者", ".flac", "L8R/阿林/#0000FF", "窃爱者")
        self.assertEqual(r.artist, "L8R&阿林")
        self.assertEqual(r.title, "竊愛者")
        self.assertEqual(cleaner._denoise_title("歌名 #DEADBEEF"), "歌名")
        # 純標籤路徑（無檔名可依）仍會剃除色碼。
        r2 = cleaner.resolve("無分隔符", ".flac", "L8R/阿林/#0000FF", "窃爱者")
        self.assertEqual(r2.artist, "L8R/阿林")

    def test_swapped_filename_corrected(self):
        # 檔名為「歌名 - 演出者」順序，與標籤反序吻合 → 對調校正。
        r = cleaner.resolve("Zombie - The Cranberries", ".flac", "The Cranberries", "Zombie")
        self.assertEqual(r.artist, "The Cranberries")
        self.assertEqual(r.title, "Zombie")
        # 標籤歌名帶 (Demo) 尾綴也能經含入比對認出反序。
        r2 = cleaner.resolve("香烟与吻痕 - Hogee", ".flac", "Hogee", "香烟与吻痕 (Demo)")
        self.assertEqual(r2.artist, "Hogee")
        self.assertEqual(r2.title, "香菸與吻痕")

    def test_filename_first_when_matching(self):
        # 正序吻合 → 內容以檔名為準（簡轉繁自檔名字串）。
        r = cleaner.resolve("张信哲 - 别怕我伤心", ".flac", "张信哲", "别怕我伤心")
        self.assertEqual(r.artist, "張信哲")
        self.assertEqual(r.title, "別怕我傷心")

    def test_spaced_split_protects_hyphen_artist(self):
        # 「A-Lin - 歌名」有空白破折號 → 切分正確，不需標籤救援。
        r = cleaner.resolve("A-Lin - P.S.我愛你", ".flac", None, None)
        self.assertEqual(r.artist, "A-Lin")
        self.assertEqual(r.title, "P.S.我愛你")

    def test_hash_titles_not_stripped(self):
        # 正當的 # 標題不可被誤刪（非 6~8 位十六進位）。
        self.assertEqual(cleaner._denoise_title("#1 Crush"), "#1 Crush")
        self.assertEqual(cleaner._denoise_title("#Beautiful"), "#Beautiful")

    def test_conversion_idempotent(self):
        # 冪等性：已是繁體的文字再轉必須原樣不動（歧義字如 范 不可變 範）。
        for text in ("范瑋琪&張韶涵", "說愛你", "菸癮", "周杰倫", "鄧麗君"):
            self.assertEqual(cleaner.to_traditional(text), text, text)
        # 對任意輸入，轉兩次 == 轉一次。
        for text in ("范玮琪&张韶涵", "说爱你", "黄龄", "执一念"):
            once = cleaner.to_traditional(text)
            self.assertEqual(cleaner.to_traditional(once), once, text)

    def test_simplified_still_converts(self):
        # 防護不可影響正常簡轉繁。
        self.assertEqual(cleaner.to_traditional("范玮琪&张韶涵"), "范瑋琪&張韶涵")
        self.assertEqual(cleaner.to_traditional("说爱你"), "說愛你")
        self.assertEqual(cleaner.to_traditional("黄龄"), "黃齡")

    def test_leading_track_not_eat_numeric_artist(self):
        # 數字開頭的團名不可被當成曲目編號刪掉。
        keep = ["1K", "2Cellos", "163braces", "21 Savage", "50 Cent", "2NE1", "4Minute"]
        for name in keep:
            self.assertEqual(cleaner._clean_artist(name), name, name)

    def test_leading_track_still_stripped_with_punct(self):
        # 真正的曲目編號（數字後接標點）仍應被剃除。
        self.assertEqual(cleaner._clean_artist("01.周杰伦"), "周杰伦")
        self.assertEqual(cleaner._clean_artist("03 - 五月天"), "五月天")
        self.assertEqual(cleaner._clean_artist("12、孫燕姿"), "孫燕姿")

    def test_no_substring_overstrip(self):
        # 英文標記不可吃掉單字內的子字串（live/ape/cover/inst/wav...）。
        keep = {
            "Stay Alive": "Stay Alive",
            "Olive": "Olive",
            "Shape of You": "Shape of You",
            "Escape": "Escape",
            "Discover": "Discover",
            "Recover": "Recover",
            "Instinct": "Instinct",
            "Wavelength": "Wavelength",
            "I'm Alive": "I'm Alive",
        }
        for src, expect in keep.items():
            self.assertEqual(cleaner._denoise_title(src), expect, src)

    def test_real_live_marker_still_stripped(self):
        # 真正的結尾 (Live) 標記仍應被剃除（含含 live 字尾的歌名）。
        self.assertEqual(cleaner._denoise_title("Alive (Live)"), "Alive")
        self.assertEqual(cleaner._denoise_title("說愛你 (Live)"), "說愛你")

    def test_fullwidth_paren_live(self):
        # 全形括號 （Live） 也應被剃除（與半形 (Live) 一致）。
        r = cleaner.resolve("李宗盛-問", ".flac", "李宗盛", "問 （Live）")
        self.assertEqual(r.title, "問")

    def test_live_in_version_name_kept(self):
        # 「Live」屬於版本名稱的一部分、非結尾標記時應保留，不可誤刪。
        self.assertEqual(cleaner._denoise_title("天后 (盲目盲目Live版)"), "天后 (盲目盲目Live版)")
        # 檔名優先：檔名寫「天后」→ 標題以檔名為準。
        r = cleaner.resolve("李佳薇-天后", ".flac", "李佳薇", "天后 (盲目盲目Live版)")
        self.assertEqual(r.title, "天后")

    def test_feat_qualifier_kept(self):
        # feat./版本等合理標題修飾詞應保留，不視為雜訊。
        r = cleaner.resolve("x", ".flac", "Taylor Swift", "Treacherous (Taylor's Version)")
        self.assertEqual(r.title, "Treacherous (Taylor's Version)")

    def test_resolve_prefers_tags(self):
        # 內建標籤優先：A-Lin（含連字號）完整保留，標籤 Live 雜訊被去除並簡轉繁。
        r = cleaner.resolve("A-Lin-P.S.我爱你", ".flac", "A-Lin", "说爱你 (Live)")
        self.assertTrue(r.parsable)
        self.assertEqual(r.artist, "A-Lin")
        self.assertEqual(r.title, "說愛你")
        # 原始檔名資訊仍保留供顯示用。
        self.assertEqual(r.original_stem, "A-Lin-P.S.我爱你")
        self.assertEqual(r.ext, ".flac")

    def test_resolve_falls_back_to_filename(self):
        # 標籤缺失時回退檔名解析。
        r = cleaner.resolve("蔡依林-说爱你+(Live)", ".mp3", None, None)
        self.assertTrue(r.parsable)
        self.assertEqual(r.artist, "蔡依林")
        self.assertEqual(r.title, "說愛你")

    def test_resolve_partial_tag_falls_back(self):
        # 只有 artist 沒有 title → 不可靠，回退檔名解析。
        # title「菸癮」已含繁體字 → 冪等防護整欄保留原樣（安全優先）。
        r = cleaner.resolve("胡凯儿-菸癮", ".flac", "胡凯儿", None)
        self.assertTrue(r.parsable)
        self.assertEqual(r.artist, "胡凱兒")
        self.assertEqual(r.title, "菸癮")

    def test_mixed_field_left_untouched(self):
        # 混合欄位（繁體字+個別簡體字）整欄不轉：寧可留下個別簡體字，
        # 也不冒歧義字被改壞的風險（如 范瑋琪 → 範瑋琪）。
        self.assertEqual(cleaner.to_traditional("菸瘾"), "菸瘾")

    def test_safe_component(self):
        # 非法字元被替換，不產生非法檔名。
        name = cleaner.build_target_name("AC/DC", "T:N*T?", ".mp3")
        for ch in '\\/:*?"<>|':
            self.assertNotIn(ch, name)


if __name__ == "__main__":
    unittest.main()
