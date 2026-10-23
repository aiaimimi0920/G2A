# 独立游戏派发 journal 的关闭屏障与载荷清理

后续 [有界槽位回收](GAME_JOURNAL_GC_PROOF.md) 已允许在本屏障提交后删除逐 claim
摘要；下文 retire 操作本身仍只建立屏障和清除回复，不混入独立的批量回收事务。

## 两个 authority，两个提交点

此前 Relay 邮箱清理不触碰独立 `RelayGamePort.journal`。本增量增加可信维护协调器
`retire_closed_game_journal(mailbox_id, now)`：先在 Relay owner 锁下确认对象存在、
已关闭且账本健康，再释放 Relay 锁，向固定游戏端口发送可信关闭见证。
这是内部适配器通道，不是新增 wire 操作，外部请求不能自报 mailbox 已关闭。

游戏端口在自己的锁内原子提交两项事实：

1. mailbox 加入永久关闭屏障 `closed_mailboxes`；
2. 该 mailbox 的 journal 保留 claim 键及摘要，但清除 reply 和授权 guard。

屏障 MUST 先于旧 journal 重放和任何新的游戏调用检查。即使 claim 在 Relay 关闭前
已经取得可信 binding、尚未进入游戏端口，也不能在屏障提交后执行。response_guard
也拒绝关闭 mailbox，不能重新认证已清理的回复。新 mailbox 不受旧身份屏障影响。

提交前故障保留原 journal，Relay 已关闭状态不回滚；提交后丢响应可以重试并得到
固定 retired 状态，不重新执行。Relay 载荷清理与游戏 journal 清理可任意先后，
两者成功并非一个原子事务。完整假账本重启必须恢复屏障；不健康端口保持拒绝。

## 在途效果与并发

游戏端口锁串行化 dispatch 和关闭屏障。已经持锁的 dispatch 可以完成，之后清理
其缓存回复；屏障不是取消、不是世界回滚。协调器不得持有 Relay 锁等待游戏端口，
避免把独立 authority 锁串成伪事务。只有屏障返回成功后才声明该端口已阻断旧 claim。

关闭屏障自身只返回维护状态，不提供旧动作业务结果。Relay 已领取请求仍保持 unknown，
不能因为缓存清空就改为 not_accepted；应使用原业务 ID 和原结果权限另行查证。

## 证据和边界

新增八个 Python 场景：缓存清理不改变游戏状态、迟到未派发 claim 拒绝、关闭 owner
验证、两个提交点故障隔离、两种清理次序与假重启、unknown 保留、新配对隔离，以及
真实线程交错下已开始的聊天效果只发生一次、随后 journal 回复被清理。

本模型保留最多八个 mailbox 屏障及既有 journal 摘要，未释放身份或 claim 槽位。
它不处理活跃 journal 的回收、不擦除认证表、不取消已有调用，不等于隐私删除或真实
持久数据库证明。端口接口的可信见证需由生产适配器认证，不能直接暴露给调用者。
