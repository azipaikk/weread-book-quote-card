# weread-book-quote-card

输入一个书名，从微信读书取封面和**大家划线最多的热门金句**，做成 3:4 的"电影字幕"风格金句卡片：
封面做主图，金句像字幕条一样一条条拼接在下方，可直接发朋友圈、小红书。

这是一个给 [Codex](https://developers.openai.com/codex) 等 Agent 使用的 skill：脚本负责取数、断行、渲染和质检，
Agent 负责确认是哪本书、挑哪几句、怎么分组。

## 它做什么

- 搜书并确认是哪一本，取封面和热门划线（微信读书接口固定返回前 20 条，带划线人数）
- 用真实字体量字宽，把长句在标点处拆成两条字幕条；放不下的划线给出"完整句子"选项
- 按版式渲染：主图约 70%，4 条字幕条各约 7.5%，条间距为 0
- **卡面上的每个字都来自微信读书原文**：Agent 只填编号，渲染后再逐字比对一次
- 逐张自动质检（文字一致、版面不溢出、封面清晰度、字幕条有字），并要求肉眼复查

## 前置条件

1. 能运行 Python 3.9+，并安装 Pillow（`python -m pip install -r skills/weread-book-quote-card/requirements.txt`）
2. 本机装有中文字体（Windows / macOS 自带的即可），或用 `--font` 指定
3. 一个微信读书 **API Key**：登录 <https://weread.qq.com/r/weread-skills> 获取，形如 `wrk-` 开头
4. 在**自己的电脑**上运行（需要能访问 `i.weread.qq.com`；网页版或受限沙箱不行）

## 安装（Codex）

1. 在本仓库页面点绿色 **Code** 按钮 → **Download ZIP**，解压
2. 把解压出来的 `skills/weread-book-quote-card` 整个文件夹复制到 Codex 的技能目录：
   - Windows：`C:\Users\你的用户名\.codex\skills\`
   - macOS / Linux：`~/.codex/skills/`
3. 设置 Key（只在你自己的电脑上设置，**不要提交到仓库，也不要发进对话**）：
   - Windows PowerShell：`setx WEREAD_API_KEY "wrk-你的Key"`
   - macOS / Linux：在 `~/.zshrc` 或 `~/.bashrc` 里加一行 `export WEREAD_API_KEY=wrk-你的Key`
4. **完全退出并重新打开 Codex**，环境变量才会生效

## 使用

在 Codex 里直接说：

> 用微信读书的热门划线，帮我把《百年孤独》做成金句图

第一次运行时它会先做环境检查，缺什么会说明用途并征求你同意。成品默认放在当前目录的 `weread_cards/<书名>/cards/` 下。

## 目录结构

```
skills/weread-book-quote-card/
├── SKILL.md                 # Agent 读取的主文件：流程、规则、停止条件
├── requirements.txt
├── references/
│   ├── selection-rubric.md  # 怎样像编辑一样选句、分组
│   ├── layout-spec.md       # 版式数字、可调参数、排障表
│   └── api-contract.md      # 接口字段，哪些已核实、哪些未核实
└── scripts/
    ├── check_environment.py # 环境检查（只读，不打印 Key）
    ├── weread_fetch.py      # 搜书、取封面和热门划线
    ├── prepare_quotes.py    # 量条数、拆完整句子、去重、打包建议
    ├── render_card.py       # 渲染卡片
    ├── qa_check.py          # 逐字比对与版面质检
    └── cardlib.py           # 共享工具
```

## 隐私、安全与合规

- API Key 只从环境变量 `WEREAD_API_KEY` 读取，不会被打印，也不会写入任何文件
- 接口返回的他人用户 ID（`userVid`）会被直接丢弃，不保存、不展示
- 热门划线、封面和书名的权利归微信读书、出版方和作者所有。公开发布成品前，请自行确认平台条款和版权；
  卡片上默认保留书名、作者和"微信读书热门划线"的来源标注
- `.gitignore` 已排除 `weread_cards/`，避免把封面图和书摘误提交到仓库

## 免责声明

本项目是个人开发的第三方工具，**与微信读书、腾讯无关联**，也未获其背书。接口行为可能随官方调整而变化，使用风险自负。

## 许可

见仓库中的 `LICENSE` 文件。
