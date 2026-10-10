# 微信读书接口契约

本 skill 的数据全部来自微信读书的 Agent API 网关。这份文档记录"哪些是已核实的，哪些还没核实"，
改脚本或排查问题时先看这里。

## 目录
- 认证
- 用到的三个接口
- 一次真实测试的观察
- 尚未验证的点
- 隐私与合规

## 认证

- Key 获取：用户本人登录 https://weread.qq.com/r/weread-skills 获取，形如 `wrk-xxxxxxxx`，绑定该用户身份。
- 使用方式：环境变量 `WEREAD_API_KEY`。脚本通过请求头 `Authorization: Bearer <Key>` 发送。
- 入口：`POST https://i.weread.qq.com/api/agent/gateway`（测试时可用环境变量 `WEREAD_GATEWAY_URL` 指向本地假网关）。
- 请求体：`api_name` 指定接口，其余参数平铺在顶层，每次必须带 `skill_version`（当前 `"1.0.3"`）。
- 错误：`errcode` 不为 0 即失败；`-2012` 是登录超时（Key 失效，需用户重新获取）；`-2003` 是参数格式错误。
- **Key 只能由用户在自己的电脑上设置。** 不要让用户把 Key 发进对话，不要把 Key 写进任何文件、日志或成品。

## 用到的三个接口

### `/store/search`
入参：`keyword`。返回 `results[].books[].bookInfo`，含 `bookId`、`title`、`author`、`cover`、`newRatingCount`。
搜索结果里的 `cover` 是小图（`s_` 前缀，实测 70×100），**不要用它做主图**。

### `/book/info`
入参：`bookId`。返回 `title`、`author`、`category`、`cover` 等。`cover` 是 `t6_` 前缀（实测 250×357）。

### `/book/bestbookmarks`
入参：`bookId`，可选 `chapterUid`（0 = 全书，默认）。服务端固定返回前 20 条，不分页。
返回 `items[]` 和 `chapters[]`。`items[]` 实测字段：

| 字段 | 含义 | 本 skill 的用法 |
|---|---|---|
| `markText` | 划线原文 | 卡面文字的唯一来源 |
| `totalCount` | 划过这一段的人数 | 热度，写成 `heat`，用于排序和交付说明 |
| `chapterUid` | 章节 ID | 对应 `chapters[].title` 得到章节名 |
| `range` | 在章节里的字符区间 | 用于排书中顺序、检测重叠重复 |
| `bookmarkId` | 划线 ID | 仅作记录 |
| `userVid` | 划线者的用户 ID | **丢弃**，不保存、不展示 |
| `simplifiedRange`、`traditionalRange`、`bookId` | 其他 | 不使用 |

## 一次真实测试的观察（《百年孤独》，用户本机运行）

- 搜书、详情、热门划线三个接口都成功，`bestbookmarks` 返回 20 条，热度从约 7 万到 1.6 万人。
- 20 条里：22 字以内 1 条，23–44 字 8 条，超过 44 字 11 条。热门划线整体偏长，所以版式允许一句占 2 条字幕条。
- `/book/info` 的返回里没有看到封面色板字段，主色由脚本从封面图自己提取。
- 用户从 PowerShell 复制出来的文字里有多余空格，是终端折行造成的，不是数据问题。`normalize_text` 仍会去掉中文字符之间的空白，以防数据本身带空格或换行。

## 尚未验证的点

- `t7_`、`t8_`、`t9_` 前缀是否存在更大的封面：`weread_fetch.py` 会逐个试，失败无害，结果记录在 `book.json` 的 `cover_attempts` 里。看到结果后可以把有效前缀写进这里。
- 带 `chapterUid` 调用 `bestbookmarks` 是否会返回"该章节的前 20 条"：文档的参数说明暗示可以，未实测。如果 20 条候选不够用，可以逐章调用来扩大候选池。
- 调用频率限制。
- 冷门书是否返回热门划线、返回多少条。

## 隐私与合规

- 数据归微信读书所有，使用需遵守其服务条款；公开发布卡片前请使用者自行确认。
- 卡片上保留书名、作者和"微信读书热门划线"的来源标注。
- 只用聚合热度，不保存他人的用户 ID。
