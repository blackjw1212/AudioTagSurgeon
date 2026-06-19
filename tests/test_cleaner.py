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
        r = cleaner.resolve("李佳薇-天后", ".flac", "李佳薇", "天后 (盲目盲目Live版)")
        self.assertEqual(r.title, "天后 (盲目盲目Live版)")

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
        r = cleaner.resolve("胡凯儿-菸瘾", ".flac", "胡凯儿", None)
        self.assertTrue(r.parsable)
        self.assertEqual(r.artist, "胡凱兒")
        self.assertEqual(r.title, "菸癮")

    def test_safe_component(self):
        # 非法字元被替換，不產生非法檔名。
        name = cleaner.build_target_name("AC/DC", "T:N*T?", ".mp3")
        for ch in '\\/:*?"<>|':
            self.assertNotIn(ch, name)


if __name__ == "__main__":
    unittest.main()
