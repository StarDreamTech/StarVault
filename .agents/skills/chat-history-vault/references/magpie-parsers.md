# Magpie 本地会话解析器对照

核对日期：2026-11-13。对象为官网链接的官方仓库 `yetone/magpie`，固定读取提交 `80c22eecbadceac5b835baf4bf049ca396afb729`。以下外部结论来自源码静态核对；未运行 Magpie、安装其程序或用真实聊天做转换验证。StarVault 已独立实现下列三项改进，未接入新来源或原生续聊转换。

## 已落实到 StarVault

- `session_relations.py` 提取 Codex 明确的上级、子 Agent 与分叉身份，以及 Claude Code 子 Agent 路径和有界读取的可选 `.meta.json`。关系写入索引、manifest 和只读查询，保留原归档 ID；冲突、非法或自引用身份不猜测。`desktop/src/session_relations_view.rs` 提供同 branch、同 tool 的双向导航、缺失提示和长标题裁切；Claude App Projects 保持专用导航。
- `vault.py` 的未压缩 Claude App 本地会话 / DeepSeek Harness 仅文本路径直接读取原 JSONL，省去完整源文件临时副本；发布前复核状态，变化则保留旧档并重试。损坏完整行继续阻止覆盖，压缩源与 Projects 不绕过原有验证；导出正文与原临时副本路径逐字节相同。这不是大字符串跳过解析，也不是按偏移续读。
- 普通文件增量签名加入 ctime、设备与 inode，覆盖同尺寸、恢复 mtime 的文件替换；Claude sidecar 的关系变化也参与增量检测。元数据签名不构成内容不变的密码学证明。

归档解析版本从 5 升至 6，下次用户手动导入时为可用来源补充关系。沿用手动选来源、默认仅文本和原应用只读，不恢复自动导入，也不改写真实归档。本轮使用合成数据验证，未复制第三方 Go 实现或新增依赖。

## 源码入口与许可

- [官方仓库](https://github.com/yetone/magpie)：官网主要介绍模型网关，会话管理实现在 `internal/sessions/`。
- [LICENSE](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/LICENSE)：MIT，版权为 `Copyright (c) 2026 yetone`。若复制、翻译移植代码或实质代码片段，保留其版权与许可声明；研究笔记不等于已经引入第三方实现。
- [sessions.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/sessions.go)：来源发现、会话摘要、读取缓存、JSONL 扫描。
- [content.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/content.go)、[transcript.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/transcript.go)：消息块、按需正文与分支读取。
- [markdown.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/markdown.go)：从正文读取器单独流式导出 Markdown。

## 已核实的可借鉴实现

| 方向 | Magpie 的具体做法 | StarVault 当前实现及借鉴边界 |
| --- | --- | --- |
| 来源适配与消息表示 | 各来源独立解析；`Part` 区分 user / assistant / tool，以及 text / thinking / tool_use / tool_result / context / image；模型可来自消息或轮次 | `vault.export_session` 集中处理多来源，`dialogue.jsonl` 保留可读的原消息，工具日志另由 `resources.py` 管理。可逐步抽离来源适配，沿用现有归档契约；`Part` 本身缺少消息 ID、时间和父子关系，不能直接作为完整档案格式 |
| 文件内续读 | `tail.go` 保存最后完整行后的偏移、头部及采样前缀指纹；满足续读条件时读取新增部分，失效时重读。`scanAt` 暂留没有换行的尾部 | 现有 `.export-cache.json` 跳过未变会话；变化后的会话由 `export_session` 整体解析。真正按偏移续读有价值，但必须保证与完整导出相同，并保留损坏完整行阻止覆盖的现有规则 |
| 元数据与正文分开 | 列表读取摘要；`ContentOf` / `TranscriptOf` 按需读源文件指定区间。请求缓存使用带校验和的追加帧和恢复状态 | 阅读器已从归档分页读取正文；值得优化的是源导入阶段。新的缓存只能是可重建的索引，不能成为文本归档的唯一正文 |
| 分支与子 Agent | `Session` 有 role / parent_session / root_session；`subagents.go` 读取 Claude 的子 Agent 元数据、OpenCode 子会话等。Pi 按最后节点沿 parentId 回溯当前分支，Claude 分支按共享 UUID 衔接原会话 | 已补齐 Codex / Claude Code 明确身份的父子导航与 Codex 分叉来源，Claude App Projects 保持专门层级。尚未实现 UUID 共享前缀的分支投影或根节点推导；档案保留其他分支，不照搬丢弃旁支的投影 |
| 大记录的内存控制 | `thin.go` 在元数据扫描时分块跳过或裁短大字符串，减少截图 base64 对列表解析的开销 | 仅文本导入已停止持久化资源二进制，未压缩 Claude App / DeepSeek Harness 省去 `prepare_jsonl` 完整源临时副本；压缩等来源仍需准备，`export_session` 仍按完整行处理。流式跳过大字符串尚待实现，归档正文不得套用展示截断策略 |
| 新来源与格式演进 | OpenCode 适配器区分旧 JSON、SQLite 旧表与 v2 表；迁移中处理新旧存储并存。Cursor 区分 CLI 和编辑器聊天，编辑器有 `state.vscdb` 与项目 transcript 读取 | StarVault 当前七种来源未包含 OpenCode、Cursor、Pi。优先研究 OpenCode 与 Cursor 的适配器；接入须独立验证上游格式、错误处理和只读行为，不能以官网 Agent 名单代替正文支持范围 |

补充来源：

- [tail.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/tail.go)、[call_cache.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/call_cache.go)、[discovery.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/discovery.go)：续读、缓存与目录发现。目录暂时读取失败时沿用上次成功结果，区分“不可读”和“已消失”。采样指纹是性能折中，不能宣称证明全部旧内容未变。
- [subagents.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/subagents.go)：子 Agent 标题、类型、父节点与正文入口；Codex 子 Agent 通过独立会话的 ParentSession 表示。
- [thin.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/thin.go)：低内存元数据扫描。
- [opencode.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/opencode.go)、[transcript_opencode.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/transcript_opencode.go)：OpenCode 存储与正文适配。
- [cursor_editor.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/cursor_editor.go)：共享只读数据库访问、按索引前缀查 composer、编辑器聊天正文；编辑器记录的可读性与 CLI 能否继续该会话分开。

## “迁移”的两种结果

StarVault 当前把档案和所选资源迁到另一台电脑继续检索阅读；`vault.export` 生成的归档说明明确限定这一用途。原客户端能否恢复会话，需要各客户端自己的格式和导入机制。

Magpie 的 [carry_convert.go](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/internal/sessions/carry_convert.go) 已实现 Claude Code ↔ Codex：读取源会话，在目标客户端目录新建原生会话，并返回 resume 命令。转换在显式请求时发生，源文件只读。可借鉴它在 `carryItem` 中先统一消息、配对工具调用与结果，再分别生成目标格式的做法。

其转换具有明确损失：Bash / exec_command 可映射为目标工具，其他工具降为说明文字；跨供应商 thinking / 加密 reasoning 不迁入；单项工具输出有 64 KiB 上限。该实现不能证明任意客户端之间无损续聊。StarVault 的仅文本档案未必保有转换所需的完整工具内容和图像，转换入口必须先报告可用材料与损失，不能自动补复制资源或改写源会话。

另一个 [relocate-claude](https://github.com/yetone/magpie/blob/80c22eecbadceac5b835baf4bf049ca396afb729/docs/session-relocation.md) 功能会迁移 Claude Code 的原项目存储，属于写源操作。当前 StarVault 的只读归档约定不包含这种操作。

## 不能直接照搬的阅读策略

- `TranscriptOf` 的总量上限为 400,000，单个 `Part` 最多保留 8,000 个 Unicode 字符并标记裁切；其 Markdown 导出另走无此展示裁切的读取路径。StarVault 继续完整保留文字，分页和折叠仅影响展示。
- `content.go::textPart` 以 `<` 或 `# AGENTS.md` 开头判断 context；这可能包含用户真正输入的内容。StarVault 继续用已确认包装与原消息元数据判断，混合或不完整包装保持展开。
- 多个解析分支在 JSON 解码失败时继续读取，超大行扫描也可能跳过；这些是查看器的容错取舍。StarVault 继续拒绝用损坏完整记录覆盖旧归档。
- Magpie 的 `Session.App = claude-desktop` 标记可表示在 Claude Desktop Code 标签中运行的 Claude Code 会话。核对的 `HasTranscript` 与会话发现路径不能证明其支持 StarVault 的 Claude App 普通本地聊天、Projects 主对话与讨论串缓存；这部分继续保留现有专用解析。
- 官网的模型网关、Token 统计与会话正文属于不同能力。`HasTranscript` 明确列举可读正文的来源，不能据网关支持名单宣传已经可以完整迁移所有来源。

## 后续方向（待实施）

1. 为现有来源记录“发现 / 正文 / 工具 / 分支 / 附件 / 覆盖范围”能力，统一 parser 输出中的身份和来源字段；增量导入继续由用户选择来源并显式执行，默认仅文本。
2. 在已实现的 Codex / Claude Code 阅读器父子导航基础上，按需设计时间线关系视图；当前项目时间线仍沿用既有节点规则。Projects 继续按产品、origin、channel 与 thread 隔离。身份和关系不得靠标题或路径相似度猜测。
3. 在测量长会话导入开销后，选择一个 JSONL 来源实现持久化续读与低内存资源跳过。验证新增、半行补齐、重写、同尺寸替换、压缩轮换和缓存损坏，确保与完整解析相同后再推广；不得以此恢复自动导入。
4. 按实际需要接入 OpenCode / Cursor；原生续聊转换作为独立功能设计，先输出目标格式与损失预览，不与已有档案迁移混称已完成。

不为读取 Go 适配器引入 Go 运行时或更换 Python / Rust 架构。优先借鉴格式事实、边界与测试案例；需要实际移植代码时单独维护来源和许可证。

## 可参考的回归案例

已阅读上游 `transcript_test.go`、`content_test.go`、`call_append_test.go`、`carry_convert_test.go` 的测试定义：包括分支选择、追加后定位、同前缀增长重写、缓存帧恢复、跨客户端工具转换与源文件保留。这些是后续测试设计依据，本轮未运行或移植上游测试，也不构成 StarVault 已通过相关测试的声明。

StarVault 自身已通过 150 项 Python 检查（2 项可选 zstd 路径跳过）及 43 项 Rust release 测试。`test_session_relations.py`、`test_archive_storage.py`、`test_claude_desktop.py` 和 Rust 关系模块测试覆盖身份隔离、sidecar 更新、重复零改写、源消失保留、同尺寸替换、导入中变化保护、正文一致性及真实指针事件跳转。macOS release 应用已构建并校验临时签名；原生截图与合成归档证据只保存在忽略的 `.local/magpie-adoption/`。
