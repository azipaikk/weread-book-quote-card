# -*- coding: utf-8 -*-
"""把 book.json 里的热门划线整理成"候选清单"。

做三件机械的事，方便 Agent 专心做编辑判断：
  1. 用真实字体量一量：每条划线要占几条字幕条（1 条、2 条，或太长放不下）
  2. 太长的划线，列出能放下的"完整句子"选项（编号如 3.1、3.2）
  3. 标出重叠重复的划线，并给出一份按热度打包的建议（Agent 可以按主题重排）

用法：
  python -X utf8 prepare_quotes.py --book OUT/book.json --out OUT/candidates.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cardlib as C  # noqa: E402

C.ensure_utf8()


def parse_range(rng):
    try:
        a, b = str(rng).split("-")
        return int(a), int(b)
    except Exception:  # noqa: BLE001
        return None


def break_quality(lines):
    """两条字幕条的句子：断在标点后记 punct，否则记 midword（可能把词拆开）；单条返回 None。"""
    if not lines or len(lines) < 2:
        return None
    a = lines[0]
    tail = a[-2] if (a[-1] in C.CLOSERS and len(a) > 1) else a[-1]
    return "punct" if tail in C.SOFT_BREAK else "midword"


def make_pieces(text, lay, max_lines, cap=10):
    spans = C.sentence_spans(text)
    if len(spans) < 2:
        return []
    out, seen = [], set()
    for i in range(len(spans)):
        for j in range(i, len(spans)):
            piece = text[spans[i][0]:spans[j][1]].strip()
            if not piece or piece == text or piece in seen:
                continue
            lines = lay.plan_quote(piece, max_lines)
            if lines is None:
                continue
            seen.add(piece)
            out.append({"start": spans[i][0], "text": piece, "chars": len(C.strip_ws(piece)),
                        "bands": len(lines), "lines": lines, "break": break_quality(lines)})
    out.sort(key=lambda p: (p["start"], -p["chars"]))
    out = out[:cap]
    for k, p in enumerate(out, 1):
        p.pop("start")
        p["ref"] = None  # 稍后补
    return out


def main():
    ap = argparse.ArgumentParser(description="整理候选金句")
    ap.add_argument("--book", required=True, help="weread_fetch.py 生成的 book.json")
    ap.add_argument("--out", required=True, help="输出的 candidates.json")
    ap.add_argument("--bands", type=int, default=4, help="每张卡的字幕条数，默认 4")
    ap.add_argument("--max-bands-per-quote", type=int, default=2, help="单句金句最多占几条，默认 2")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--aspect", default="3:4")
    ap.add_argument("--font")
    args = ap.parse_args()

    with open(args.book, encoding="utf-8") as f:
        book = json.load(f)
    lay = C.Layout(width=args.width, aspect=args.aspect, font=args.font)

    cands = []
    for rank, h in enumerate(book["highlights"], 1):
        text = h["text"]
        lines = lay.plan_quote(text, args.max_bands_per_quote)
        rg = parse_range(h.get("range"))
        c = {
            "ref": str(h["id"]),
            "rank": rank,
            "heat": h.get("heat"),
            "chapter": h.get("chapter"),
            "pos": [h.get("chapter_uid") or 0, rg[0] if rg else 0],
            "range": rg,
            "text": text,
            "chars": len(C.strip_ws(text)),
            "bands": len(lines) if lines else None,
            "lines": lines,
            "break": break_quality(lines),
            "dup_of": None,
            "pieces": [],
        }
        pieces = make_pieces(text, lay, args.max_bands_per_quote)
        for k, p in enumerate(pieces, 1):
            p["ref"] = "%s.%d" % (c["ref"], k)
        c["pieces"] = pieces
        cands.append(c)

    # 重叠 / 包含 → 标记为重复，保留热度高的
    for a in cands:
        for b in cands:
            if a is b or a["dup_of"] or b["dup_of"]:
                continue
            if (a["heat"] or 0) < (b["heat"] or 0):
                continue
            same_ch = a["pos"][0] == b["pos"][0]
            overlap = bool(a["range"] and b["range"] and same_ch
                           and a["range"][0] < b["range"][1] and b["range"][0] < a["range"][1])
            contained = C.strip_ws(b["text"]) in C.strip_ws(a["text"]) and a["ref"] != b["ref"]
            if overlap or contained:
                if not a["dup_of"]:
                    b["dup_of"] = a["ref"]

    # 打包建议：按热度贪心，凑满 N 条字幕条，卡内按书中顺序排
    pool = []
    for c in cands:
        if c["dup_of"]:
            continue
        if c["bands"]:
            pool.append({"ref": c["ref"], "bands": c["bands"], "heat": c["heat"] or 0, "pos": c["pos"]})
        elif c["pieces"]:
            best = max(c["pieces"], key=lambda p: p["chars"])
            pool.append({"ref": best["ref"], "bands": best["bands"], "heat": c["heat"] or 0, "pos": c["pos"]})
    pool.sort(key=lambda q: -q["heat"])
    suggestions = []
    while pool:
        first = pool.pop(0)
        chosen, need = [first], args.bands - first["bands"]
        for q in list(pool):
            if need <= 0:
                break
            if q["bands"] <= need:
                chosen.append(q)
                pool.remove(q)
                need -= q["bands"]
        if need == 0:
            chosen.sort(key=lambda q: q["pos"])
            suggestions.append({
                "name": "卡片%d" % (len(suggestions) + 1),
                "quotes": [q["ref"] for q in chosen],
                "avg_heat": round(sum(q["heat"] for q in chosen) / len(chosen)),
            })
        else:
            pool.extend(chosen[1:])  # 第一条凑不满，放弃它，其余放回去
            pool.sort(key=lambda q: -q["heat"])

    result = {
        "layout": {"W": lay.W, "H": lay.H, "band_h": lay.band_h, "usable": lay.usable,
                   "size_min": lay.size_min, "size_max": lay.size_max,
                   "font": lay.font_path, "font_index": lay.font_index},
        "bands_per_card": args.bands,
        "missing_glyphs": lay.missing_glyphs("".join(c["text"] for c in cands)),
        "candidates": cands,
        "suggested_cards": suggestions,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ---- 给人（和 Agent）看的表 ----
    b = book["book"]
    print("《%s》 %s" % (b["title"], b["author"]))
    print("字体：%s   每张卡 %d 条字幕条，一句最多占 %d 条" % (os.path.basename(lay.font_path), args.bands, args.max_bands_per_quote))
    if result["missing_glyphs"]:
        print("⚠ 字体缺少这些字的字形：%s（建议换字体 --font）" % "".join(result["missing_glyphs"]))
    print("")
    print("编号 | 热度(人) | 字数 | 占条 | 章节 | 备注 | 内容")
    for c in cands:
        note = "重复于%s" % c["dup_of"] if c["dup_of"] else ("太长" if c["bands"] is None else ("非标点断行" if c["break"] == "midword" else ""))
        print("%4s | %8s | %4d | %4s | %s | %s | %s" % (
            c["ref"], c["heat"], c["chars"], c["bands"] or "-", c["chapter"], note, c["text"]))
        if c["bands"] is None or (len(c["pieces"]) and not c["dup_of"] and c["bands"] == 2):
            for p in c["pieces"]:
                print("   └ %5s | 占%d条 | %d字 | %s%s" % (p["ref"], p["bands"], p["chars"], "[非标点断行] " if p["break"] == "midword" else "", p["text"]))
    print("")
    ok = sum(1 for c in cands if c["bands"] and not c["dup_of"])
    print("整句可直接用：%d 条；太长需取完整句子：%d 条；重复：%d 条" % (
        ok, sum(1 for c in cands if c["bands"] is None), sum(1 for c in cands if c["dup_of"])))
    print("按热度的打包建议（共 %d 张）：" % len(suggestions))
    for s in suggestions:
        print("  %s：%s  平均热度 %s" % (s["name"], " + ".join(s["quotes"]), s["avg_heat"]))
    print("已保存：%s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
