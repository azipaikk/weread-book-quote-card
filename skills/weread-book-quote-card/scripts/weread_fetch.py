# -*- coding: utf-8 -*-
"""从微信读书 Agent API 取一本书的封面和热门划线。

用法：
  python -X utf8 weread_fetch.py search "百年孤独"
  python -X utf8 weread_fetch.py fetch --book-id 935536 --out-dir OUT

API Key 只从环境变量 WEREAD_API_KEY 读取，不会被打印、不会写入任何文件。
接口返回里的 userVid（划线者的用户 ID）属于他人信息，一律丢弃。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cardlib as C  # noqa: E402

C.ensure_utf8()


def collect_books(search_data):
    seen, out = set(), []
    for group in search_data.get("results", []) or []:
        for b in group.get("books", []) or []:
            info = b.get("bookInfo", {}) or {}
            bid = info.get("bookId")
            if not bid or bid in seen:
                continue
            seen.add(bid)
            out.append(
                {
                    "bookId": bid,
                    "title": info.get("title"),
                    "author": info.get("author"),
                    "rating_count": info.get("newRatingCount"),
                    "cover": info.get("cover"),
                }
            )
    return out


def cmd_search(args):
    key = C.get_api_key()
    data = C.gateway_call(key, "/store/search", keyword=args.keyword)
    books = collect_books(data)[: args.limit]
    if not books:
        print("没有搜到《%s》。请换个书名或加上作者再试。" % args.keyword)
        return 3
    print("搜索《%s》的结果（按接口返回顺序）：" % args.keyword)
    for i, b in enumerate(books, 1):
        print(
            "  %d. 《%s》 作者：%s  评分人数：%s  bookId=%s"
            % (i, b["title"], b["author"], b["rating_count"], b["bookId"])
        )
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(books, f, ensure_ascii=False, indent=2)
        print("已保存：%s" % args.out)
    return 0


def cover_variants(url):
    """详情接口给的是 t6_ 开头的封面（约 250x357）。微信读书的封面链接靠前缀区分尺寸，
    这里顺手试几个更大的前缀；试不到就用原图。这是猜测，失败无害。"""
    out = [url]
    m = re.match(r"^(.*/)(s_|t\d+_)([^/]+)$", url or "")
    if m:
        base, _, name = m.groups()
        for prefix in ("t9_", "t8_", "t7_"):
            out.append(base + prefix + name)
    return out


def fetch_cover(url, out_dir, probe=True):
    attempts, best = [], None
    for u in (cover_variants(url) if probe else [url]):
        if not u:
            continue
        try:
            data = C.download(u)
            size = C.image_size(data)
            attempts.append({"url": u, "ok": True, "size": list(size) if size else None})
            area = (size[0] * size[1]) if size else 0
            if best is None or area > best[0]:
                best = (area, u, data, size)
        except Exception as e:  # noqa: BLE001
            attempts.append({"url": u, "ok": False, "error": str(e)[:80]})
    if best is None:
        return None, None, attempts
    _, u, data, size = best
    ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
    path = os.path.join(out_dir, "cover" + ext)
    with open(path, "wb") as f:
        f.write(data)
    return path, (list(size) if size else None), attempts


def cmd_fetch(args):
    key = C.get_api_key()
    book_id = str(args.book_id)
    info = C.gateway_call(key, "/book/info", bookId=book_id)
    title = info.get("title") or "book"
    out_dir = args.out_dir or os.path.join("weread_cards", C.safe_name(title))
    os.makedirs(out_dir, exist_ok=True)

    bm = C.gateway_call(key, "/book/bestbookmarks", bookId=book_id)
    chapters = {c.get("chapterUid"): c.get("title") for c in (bm.get("chapters") or [])}
    highlights = []
    for idx, it in enumerate(bm.get("items") or [], 1):
        raw = it.get("markText") or ""
        text = C.normalize_text(raw)
        if not text:
            continue
        highlights.append(
            {
                "id": idx,
                "text": text,
                "raw_text": raw,
                "heat": it.get("totalCount"),
                "chapter": chapters.get(it.get("chapterUid"), str(it.get("chapterUid"))),
                "chapter_uid": it.get("chapterUid"),
                "range": it.get("range"),
                "bookmark_id": it.get("bookmarkId"),
                # 故意不保存 userVid
            }
        )
    if not highlights:
        print("这本书没有取到热门划线。可能是冷门书，换一本试试。")
        return 3

    cover_path, cover_size, attempts = fetch_cover(info.get("cover"), out_dir, probe=not args.no_probe)
    book = {
        "schema": 1,
        "source": "微信读书 Agent API：/book/info、/book/bestbookmarks",
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "book": {
            "bookId": book_id,
            "title": info.get("title"),
            "author": info.get("author"),
            "category": info.get("category"),
            "cover_url": info.get("cover"),
            "cover_file": os.path.abspath(cover_path) if cover_path else None,
            "cover_size": cover_size,
            "cover_attempts": attempts,
        },
        "highlights": highlights,
    }
    out_json = os.path.join(out_dir, "book.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=2)

    print("《%s》 作者：%s" % (info.get("title"), info.get("author")))
    print("热门划线：%d 条（热度最高 %s 人，最低 %s 人）" % (
        len(highlights),
        max(h["heat"] or 0 for h in highlights),
        min(h["heat"] or 0 for h in highlights),
    ))
    if cover_path:
        print("封面：%s  像素 %s" % (cover_path, "x".join(map(str, cover_size)) if cover_size else "未知"))
        for a in attempts:
            print("   尝试 %s -> %s" % (a["url"].rsplit("/", 1)[-1][:28], ("成功 " + "x".join(map(str, a["size"]))) if a["ok"] and a.get("size") else ("成功" if a["ok"] else "失败")))
        if cover_size and cover_size[0] < 200:
            print("⚠ 封面像素很小，成品里封面会偏糊。")
    else:
        print("⚠ 没能下载封面，渲染时会用纯色背景加书名代替。可用 --cover 手动指定封面图。")
    print("已保存：%s" % out_json)
    return 0


def main():
    ap = argparse.ArgumentParser(description="微信读书：搜书、取封面和热门划线")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="按书名搜索，列出候选书")
    s.add_argument("keyword")
    s.add_argument("--limit", type=int, default=6)
    s.add_argument("--out", help="把候选列表另存为 JSON")
    s.set_defaults(func=cmd_search)

    f = sub.add_parser("fetch", help="取封面和热门划线，写成 book.json")
    f.add_argument("--book-id", required=True)
    f.add_argument("--out-dir")
    f.add_argument("--no-probe", action="store_true", help="不尝试更大尺寸的封面链接")
    f.set_defaults(func=cmd_fetch)

    args = ap.parse_args()
    try:
        return args.func(args)
    except C.ApiError as e:
        print("出错了：%s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
