# 独立 Launcher 的不可逆退役与有界回收

## 为什么不能直接删效果账本

启动回执、许可消费、独立效果和退出墓碑属于不同知识层。删除独立 entries 后若仍
允许 start，相同许可就可能重新产生效果；删除 exited 后若仍接受旧 running 快照，
又会复活已退出进程。因此本模型只能先建立不可逆 sealed 屏障，再回收该端口账本。

## 两个独立提交域

LaunchHarness.retire_launcher 是可信维护入口，不是公开协议操作。顺序为：

1. 提交可信时间维护，要求健康 authority、无会话或会话已关闭、所有启动记录均终态。
   after_accept/after_dispatch 留下的 pending 即使端口没有效果也阻断退役。
2. LauncherPort.seal 在独立锁内要求 running 为空、entries 全部 done/failed、每个
   已知 effects 都有精确 exited 见证，再不可逆设置 sealed。缺少 running 不证明退出。
3. authority 单独提交 launcher_retired 确认。after_seal 或确认提交前故障不能回滚
   独立屏障；恢复后重复 seal 幂等，再补确认。未确认不能经 authority 回收端口。

这里不通过退役自动停止进程、伪造退出或关闭会话。先用既有确定退出监视或其他授权
关闭流程使会话终止，再退役。unknown_after_effect 即使已有退出见证，未确定启动
终态仍不得退役；不知道是否成功握手与知道进程退出不是同一事实。

## 不可复活与回收

sealed 端口拒绝所有 start（包括旧许可重试）；available 恒假，不能因旧 running
快照变真，verify_existing_effect 不再握手。authority 新 offer/新 launch 也检查
独立 sealed 状态，不能只相信可能过时的 launcher_retired 本地确认。

compact_retired_launcher 要求健康 authority 及已确认退役，再调用独立
compact_sealed。严格预算 1..128，默认 64；每项同时清理该许可的 entry、effect
和对应退出墓碑。重复及部分回收有 removed/remaining，sealed 标记永久保留。
这只删除内存记录，不是 OS 进程、文件或生产数据删除授权。

authority 原启动回执仍保留原 started/failed 事实；清理后独立 query 缺失不等于
未执行。已关闭会话的后续监视可能为 unknown，但不得复活或改写历史事实。业务
回执另按自己的最短保留期回收，许可消费仍保留。

## 验证与未完成部分

六个测试方法覆盖存活/无退出见证拒绝、未决受理/派发/效果拒绝、活动会话拒绝、
四个提交故障点和假重启、完整与部分/重复 GC、严格预算、损坏 authority 拒绝、
原历史回执可读及旧 running/旧 authority 快照不恢复新启动。

本次是单一固定应用端口的最终退役，不提供重新开放 sealed、替换成空端口或自动
换代的接口。未来新代必须定义新的可信应用/authority 绑定、迟到请求隔离和新同意，
不能拿新建对象清空旧屏障。许可/offer 长期回收、多应用、新代轮换、真实持久化、
仍待验证；不会因此宣称可无限长期启动。

## 跨语言退役与迟到请求

JS/Python 新增 22 次正式 wire 请求，分别覆盖 after_seal 与 after_commit 两个
故障窗口。两条链均实际完成启动、邀请及 ready，再验证活进程不能退役、记录退出
后活动会话仍不能退役；经已有监视关闭会话后才进入封存。

假重启后两条链的独立 sealed 都为真，但只有 after_commit 链的 authority 确认已
提交。此时新 request_id 的迟到 launch 已被拒绝；after_seal 链未经确认也不能 GC。
重复退役补齐确认后，分别清掉一套 entry/effect/退出墓碑，再次重启和重复 GC 不
恢复任何启动权。原启动回执仍为 started、查询仍 done，旧 join 不再返回控制秘密。

互通门禁强制要求独立 launcher_retirement 子报告、两个指定故障窗口、迟到请求拒绝、
两个退役端口与恰好两次启动；拒绝缺失、畸形及 bool 冒充计数。正式操作仍 38 项，
总正式请求现为 503 次；独立候选 epoch profile 的 26 次另计。退役/观察/GC 命令是
可信夹具，不计入公开操作，也不证明真实持久化、任意并发或新代轮换。
