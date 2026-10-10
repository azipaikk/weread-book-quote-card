# -*- coding: utf-8 -*-
"""weread-book-quote-card 的共享工具。

这里只放"确定性"的部分：UTF-8 输出、字体查找、文字规范化与断句、
版面计算、微信读书网关请求。需要判断的事（选哪几句）交给 Agent。
"""
from __future__ import annotations

import json
import os
import re
import struct
import sys
import urllib.error
import urllib.request
from functools import lru_cache

GATEWAY = os.environ.get("WEREAD_GATEWAY_URL", "https://i.weread.qq.com/api/agent/gateway")
SKILL_VERSION = "1.0.3"  # 网关要求每次请求都带的版本号
UA = {"User-Agent": "Mozilla/5.0"}


def ensure_utf8():
    """Windows 上管道输出默认可能是 GBK，遇到"•"之类的字符会报错，统一成 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# 微信读书网关
# --------------------------------------------------------------------------
class ApiError(RuntimeError):
    pass


def get_api_key():
    key = os.environ.get("WEREAD_API_KEY", "").strip()
    if not key:
        raise ApiError(
            "没有找到环境变量 WEREAD_API_KEY。\n"
            "请让用户自己在本机设置（不要让用户把 Key 发进对话）：\n"
            "  Windows PowerShell：setx WEREAD_API_KEY \"wrk-你的Key\"   然后完全退出并重新打开 Codex\n"
            "  macOS/Linux：在 ~/.zshrc 或 ~/.bashrc 里加一行 export WEREAD_API_KEY=wrk-你的Key，重开终端"
        )
    return key


def gateway_call(api_key, api_name, **params):
    body = {"api_name": api_name, "skill_version": SKILL_VERSION}
    body.update(params)
    headers = {"Authorization": "Bearer " + api_key, "Content-Type": "application/json"}
    headers.update(UA)
    req = urllib.request.Request(
        GATEWAY, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ApiError("%s 请求失败，HTTP 状态码 %s" % (api_name, e.code))
    except urllib.error.URLError as e:
        raise ApiError("%s 无法连接：%s（需要能访问 i.weread.qq.com 的本机环境）" % (api_name, e.reason))
    if isinstance(data, dict) and data.get("errcode") not in (None, 0):
        hint = "（-2012 表示登录超时，请回官方页面重新获取 Key）" if data.get("errcode") == -2012 else ""
        raise ApiError(
            "%s 返回错误：errcode=%s errmsg=%s%s" % (api_name, data.get("errcode"), data.get("errmsg", ""), hint)
        )
    return data


def download(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def image_size(data):
    """不依赖 Pillow，直接从文件头读出 PNG / JPEG 的宽高；读不出返回 None。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + seg_len
    return None


# --------------------------------------------------------------------------
# 文字：规范化与断句
# --------------------------------------------------------------------------
_CJK = "\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f\u2018-\u201f\u2026\u2014"
_CJK_GAP = re.compile("(?<=[%s]) +(?=[%s])" % (_CJK, _CJK))

END_PUNCT = "。！？!?；…"
CLOSERS = "”’」』）)》】\"'"
OPENERS = "“‘「『（(《【"
NO_LINE_START = "，。！？、；：,.!?;:”’」』）)》】…—"
SOFT_BREAK = "，、；：。！？,;:"
BINDS_LEFT = "的了着过地得吗呢吧啊么们"      # 这些字紧贴前一个字，不要放在行首
PARTICLES = "的了着过地得"                    # 在它们后面断行比较自然
LEADERS = "在于对把被从向与和及而但却并因所"  # 在它们前面断行比较自然


def normalize_text(s):
    """只做"空白"层面的整理：折叠空白，并去掉中文字符之间多余的空格。

    不改任何文字内容。QA 比对时会忽略全部空白，所以这一步是可验证的。
    """
    s = re.sub(r"\s+", " ", s or "").strip()
    return _CJK_GAP.sub("", s)


def strip_ws(s):
    return re.sub(r"\s+", "", s or "")


def sentence_spans(text):
    """把一段话切成句子，返回 [(start, end)]。句末标点后面的引号、括号归前一句。"""
    spans = []
    n = len(text)
    start = 0
    i = 0
    while i < n:
        ch = text[i]
        if ch in END_PUNCT:
            j = i + 1
            while j < n and (text[j] in END_PUNCT or text[j] in CLOSERS):
                j += 1
            # 对话后面紧跟"她说"之类的说明时（？” 或 ！” 后不是新引号），不在这里断开
            tail = text[i + 1:j]
            if ch in "？！?!" and tail and tail[-1] in "”’」』" and j < n and text[j] not in OPENERS:
                i = j
                continue
            spans.append((start, j))
            start = j
            i = j
            continue
        i += 1
    if start < n and text[start:n].strip():
        spans.append((start, n))
    return spans


# --------------------------------------------------------------------------
# 字体
# --------------------------------------------------------------------------
def _font_candidates():
    win = os.environ.get("WINDIR", "C:/Windows").replace("\\", "/") + "/Fonts/"
    return [
        (win + "msyhbd.ttc", 0), (win + "msyh.ttc", 0), (win + "Dengb.ttf", 0),
        (win + "simhei.ttf", 0), (win + "simsun.ttc", 0),
        ("/System/Library/Fonts/PingFang.ttc", 0),
        ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
        ("/Library/Fonts/Arial Unicode.ttf", 0),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 2),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 2),
        ("/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", 2),
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
    ]


def resolve_font(explicit=None):
    """返回 (路径, 字体序号)。用户指定的字体不存在时直接报错，不悄悄换。"""
    if explicit:
        if not os.path.exists(explicit):
            raise FileNotFoundError("指定的字体不存在：%s" % explicit)
        return explicit, 0
    env = os.environ.get("WEREAD_CARD_FONT", "").strip()
    if env:
        if not os.path.exists(env):
            raise FileNotFoundError("环境变量 WEREAD_CARD_FONT 指向的字体不存在：%s" % env)
        return env, 0
    for path, idx in _font_candidates():
        if os.path.exists(path):
            return path, idx
    raise FileNotFoundError(
        "没有找到可用的中文字体。请用 --font 指定一个中文字体文件（.ttf/.ttc/.otf），"
        "或设置环境变量 WEREAD_CARD_FONT。"
    )


@lru_cache(maxsize=128)
def load_font(path, index, size):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:  # noqa: BLE001
        return ImageFont.truetype(path, size, index=0)


# --------------------------------------------------------------------------
# 版面
# --------------------------------------------------------------------------
def parse_aspect(s):
    try:
        a, b = s.replace("x", ":").split(":")
        return float(a), float(b)
    except Exception:  # noqa: BLE001
        raise ValueError("比例格式应为 3:4 这样的写法，收到：%r" % s)


class Layout:
    """3:4 版式：主图约 70%，每条字幕条约 7.5%，条间距为 0（与参考 skill 一致）。"""

    BAND_FRAC = 0.075

    def __init__(self, width=1440, aspect="3:4", font=None):
        aw, ah = parse_aspect(aspect)
        self.W = int(width)
        self.H = round(self.W * ah / aw)
        self.band_h = round(self.H * self.BAND_FRAC)
        self.pad_x = round(self.W * 0.045)
        self.usable = self.W - 2 * self.pad_x
        self.size_max = round(self.band_h * 0.44)
        self.size_min = round(self.band_h * 0.36)
        self.font_path, self.font_index = resolve_font(font)

    def main_h(self, nbands):
        return self.H - self.band_h * nbands

    def font(self, size):
        return load_font(self.font_path, self.font_index, int(size))

    @staticmethod
    def stroke(size):
        return max(2, round(size * 0.06))

    def line_width(self, text, size):
        return self.font(size).getlength(text) + 2 * self.stroke(size)

    def fit_size(self, text):
        """这一行能放进单条字幕条的最大字号；放不下返回 None。"""
        sizes = list(range(self.size_max, self.size_min, -2)) + [self.size_min]
        for s in sizes:
            if self.line_width(text, s) <= self.usable:
                return s
        return None

    def plan_quote(self, text, max_lines=2):
        """把一句金句分成 1~max_lines 行，每行对应一条字幕条。放不下返回 None。"""
        text = text.strip()
        if self.fit_size(text) is not None:
            return [text]
        if max_lines < 2:
            return None
        best, best_score = None, None
        smin = self.size_min
        for i in range(2, len(text) - 1):
            a, b = text[:i].rstrip(), text[i:].lstrip()
            if not a or not b or a[-1] in OPENERS or b[0] in NO_LINE_START:
                continue
            sa, sb = self.fit_size(a), self.fit_size(b)
            if sa is None or sb is None:
                continue
            wa, wb = self.line_width(a, smin), self.line_width(b, smin)
            score = abs(wa - wb) / self.usable            # 两行尽量等长
            tail = a[-2] if (a[-1] in CLOSERS and len(a) > 1) else a[-1]
            if tail not in SOFT_BREAK:
                score += 0.80                              # 不在标点后断：强烈不推荐
                if b[0] in BINDS_LEFT:
                    score += 0.50                          # 把"的/了/着"留到下一行开头：更差
                if a[-1] in PARTICLES or b[0] in LEADERS:
                    score -= 0.25                          # 在"的/了"后或"在/把/但"前断：相对自然
            if min(len(a), len(b)) < 6:
                score += 0.30                              # 避免一行只剩几个字
            score -= 0.5 * (min(sa, sb) - smin) / max(1, self.size_max)
            if best_score is None or score < best_score:
                best, best_score = [a, b], score
        if best is not None:
            return best
        if max_lines >= 3:
            return None  # 三行以上不自动处理，交给 Agent 取更短的完整句子
        return None

    def missing_glyphs(self, text):
        try:
            f = self.font(self.size_max)
            nd = f.getmask("\U0010FFFF")
            nd_key = (nd.size, nd.tobytes())
            miss = []
            for ch in sorted(set(text)):
                if ch.isspace():
                    continue
                m = f.getmask(ch)
                if (m.size, m.tobytes()) == nd_key:
                    miss.append(ch)
            return miss
        except Exception:  # noqa: BLE001
            return []


def display_author(author):
    """卡面上的署名：去掉微信读书的国别标签（如 [哥]、（美）），把实心圆点换成间隔号。"""
    a = re.sub(r"^\s*(\[[^\]]{1,6}\]|［[^］]{1,6}］|（[^）]{1,6}）|\([^)]{1,6}\))\s*", "", author or "")
    return a.replace("\u2022", "\u00b7").strip()


def safe_name(s, limit=40):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s or "").strip(" ._")
    return (s or "book")[:limit]
