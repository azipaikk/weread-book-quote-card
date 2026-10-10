# -*- coding: utf-8 -*-
"""只读的环境检查：告诉你缺什么、怎么补。不会修改系统，也不会打印 API Key。

用法：
  python -X utf8 check_environment.py            # 基本检查
  python -X utf8 check_environment.py --network  # 再测一下能否连上微信读书网关
"""
from __future__ import annotations

import argparse
import os
import platform
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cardlib as C  # noqa: E402

C.ensure_utf8()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", action="store_true", help="测试能否连上微信读书网关（不带 Key，不会触发任何账号操作）")
    ap.add_argument("--font")
    args = ap.parse_args()
    problems = []

    v = sys.version_info
    ok = v >= (3, 9)
    print("[%s] Python %d.%d.%d  （%s）" % ("OK" if ok else "缺", v.major, v.minor, v.micro, platform.system()))
    if not ok:
        problems.append("需要 Python 3.9 或更新版本")

    try:
        import PIL
        print("[OK] Pillow %s" % PIL.__version__)
    except ImportError:
        print("[缺] Pillow 未安装")
        problems.append("运行：%s -m pip install -r \"%s\"" % (
            "python" if platform.system() == "Windows" else "python3",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "requirements.txt")))

    try:
        path, idx = C.resolve_font(args.font)
        print("[OK] 中文字体：%s" % path)
    except FileNotFoundError as e:
        print("[缺] 中文字体")
        problems.append(str(e))

    if os.environ.get("WEREAD_API_KEY", "").strip():
        print("[OK] 已设置环境变量 WEREAD_API_KEY（出于安全不显示内容）")
    else:
        print("[缺] 没有设置环境变量 WEREAD_API_KEY")
        problems.append(
            "请用户自己设置 Key（不要发进对话）。Windows PowerShell：setx WEREAD_API_KEY \"wrk-你的Key\"，"
            "然后完全退出并重开 Codex。Key 在 https://weread.qq.com/r/weread-skills 登录后获取。")

    if args.network:
        try:
            req = urllib.request.Request(C.GATEWAY, data=b"{}", headers={"Content-Type": "application/json", **C.UA}, method="POST")
            urllib.request.urlopen(req, timeout=15)
            print("[OK] 能连上微信读书网关")
        except urllib.error.HTTPError as e:
            print("[OK] 能连上微信读书网关（返回 HTTP %s，说明网络是通的）" % e.code)
        except Exception as e:  # noqa: BLE001
            print("[缺] 连不上微信读书网关：%s" % e)
            problems.append("需要能访问 i.weread.qq.com 的本机环境；沙箱或受限网络里无法使用。")

    print("")
    print("建议的 Python 命令：%s -X utf8 ..." % ("python" if platform.system() == "Windows" else "python3"))
    if problems:
        print("")
        print("还需要处理：")
        for p in problems:
            print("  - " + p)
        return 1
    print("环境就绪。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
