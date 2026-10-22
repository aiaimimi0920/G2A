# Relay 关闭邮箱载荷清理与重新配对隔离

## 合同与范围

关闭 mailbox 后，可信维护端口 `compact_closed_mailboxes(now, maximum)` 可以释放该
Relay authority 的请求正文、内层 proof 引用、claim、pull 回执和缓存回复。它不是
公开 wire 操作，不新增客户端管理权限。每批最多处理 8 个邮箱，默认 1 个；单邮箱
既有请求上限 128，因此扫描与重写有明确边界。仍开放的邮箱 MUST NOT 被清理。

清理 MUST 保留原请求摘要、内层角色、原 route_revision、终态、known_dispatch，
以及对象身份、注册回执、已消费 pairing 标记、外层凭据撤销记录、撤销控制回执。
这些最小墓碑确保旧请求改参仍冲突、never_sent 仍只能证明本路径未投递、claimed
仍是 unknown。已回复的旧路由关闭后也不再披露旧回复，更不重新执行。

pull 控制回执包含完整 claim 和内层 proof，必须与 pulls/claims 索引一起清理。
只清 requests 而遗留 pull 回执不构成载荷清理完成。游戏端口独立 journal、认证表
和游戏世界不在本事务内，不宣称全系统删除秘密或满足隐私删除请求。

维护先提交到期关闭，再在单个独立事务中清理选中邮箱。清理提交前失败不影响已发生
的到期关闭；提交后丢响应再调用是无副作用的空操作。完整假账本重启保留 compacted
标记和墓碑；损坏账本仍采用既有 fail-closed 规则，不允许用清理绕过不健康状态。

## 有界重新配对 profile

固定模型允许同一已验证主体使用**新的可信玩家同意证明**登记新 mailbox。原 pairing
proof 不可二次消费；原注册 ID 重试仅恢复旧注册事实，不重新打开旧邮箱、不发新凭据。
新 mailbox 与旧 mailbox 身份不同，新 token 不可访问旧 mailbox，旧 token 不可恢复。

重新配对不是业务重试协议：旧 claimed 请求的 unknown 不因新路由产生而消失。
客户端不得自动把未知动作换新语义 ID 重发；游戏业务层仍负责原业务 ID 的查询/去重。
新路由不延长旧 Grant、session lease 或结果读权。

本 profile 保留最多 8 个 mailbox 的身份墓碑，清理不释放身份槽位；达到上限明确
`resource_limit`，不使用 `len(mailboxes)+1` 重用已删除身份。不宣称无限次重新配对
或完整长期存储方案。无界运行需要另行设计持久唯一身份分配、墓碑保留期限和 epoch
隔离，不能直接删除旧 mailbox 来“解决”容量。

## 可执行证据

`tests/test_design_relay.py` 新增 8 个测试，覆盖载荷副本清除、独立游戏/journal 不变、
派发知识与改参冲突、清理前后故障、活动邮箱与输入边界、假重启、到期独立提交、
新旧配对身份隔离、批次上限和身份槽位耗尽。

JS/Python 增加可信清理命令（不是 wire 操作），清理提交前/后故障和假重启后，重新
通过 wire 验证原撤销回执、claimed unknown 与 queued not_accepted。

未覆盖：真实持久数据库、进程崩溃、内存安全擦除、独立游戏 journal 清理、活跃邮箱
回收、多参与者公平性及无限重配对。测试计数与最终源码哈希以本轮回执为准。
