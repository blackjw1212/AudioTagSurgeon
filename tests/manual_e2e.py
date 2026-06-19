# -*- coding: utf-8 -*-
"""手動端對端驗證：cleaner -> tagger.apply（含寫 Tag 與重命名）。非單元測試。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cleaner
import tagger
from mutagen.easyid3 import EasyID3


def make_dummy_mp3(path):
    # 以 MPEG frame sync 位元組構成一個 mutagen 可接受的最小 MP3。
    with open(path, "wb") as f:
        f.write(b"\xff\xfb\x90\x00" + b"\x00" * 800)


def main():
    tmp = tempfile.mkdtemp(prefix="ats_e2e_")
    # 雜亂檔名：含簡體 + Live 雜訊
    src = os.path.join(tmp, "蔡依林-说爱你+(Live).mp3")
    make_dummy_mp3(src)

    stem, ext = os.path.splitext(os.path.basename(src))
    r = cleaner.parse_filename(stem, ext)
    print("parse ->", r.artist, "/", r.title, "/ parsable:", r.parsable)
    assert r.artist == "蔡依林" and r.title == "說愛你"

    res = tagger.apply(src, r.artist, r.title)
    print("apply ->", res.status, "/", os.path.basename(res.new_path))
    assert res.status == tagger.STATUS_OK

    new_name = os.path.basename(res.new_path)
    assert new_name == "蔡依林 - 說愛你.mp3", new_name

    tags = EasyID3(res.new_path)
    print("tags  ->", tags.get("artist"), tags.get("title"))
    assert tags["artist"] == ["蔡依林"]
    assert tags["title"] == ["說愛你"]

    # 衝突測試：再放一個會碰撞同目標名的檔
    src2 = os.path.join(tmp, "蔡依林-说爱你.mp3")
    make_dummy_mp3(src2)
    res2 = tagger.apply(src2, "蔡依林", "說愛你")
    print("conflict ->", res2.status)
    assert res2.status == tagger.STATUS_CONFLICT

    print("E2E PASS")


if __name__ == "__main__":
    main()
