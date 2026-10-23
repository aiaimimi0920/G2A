# 跨代次回执归档、独立读权与有界回收

## 分离执行栅栏与查询回执

代次模型现在将 game.journal（防重执行）与 game.receipts（查询回执）分开保存。
begin 接受时保存完整 claim 身份和固定 retain_until，finish 仅改变 phase，不延长期限。
代次切换只清理旧 journal；receipts 继续存在，直到期限结束并由可信维护入口清理。

回执只返回 `{phase: accepted|completed, retain_until}`。accepted 表示已开始，不保证
效果完成；completed 表示模型收到可信完成事件，不携带业务成功断言或实际结果内容。
它不是 action.query 的替代品，不能把回执完成状态解释为任意外部效果成功。

## 独立读权

EpochBoundPort 的可信读权批准端口签发 receipt_reader fixture token，绑定原主体、
完整旧 mailbox 身份和一个原 request_id。读权不能只凭当前 mailbox/controller 身份
推断；原 controller 也不能代读另一 agent 的回执。可信批准验证目标回执已存在且
主体与原 claim 一致。公开绑定使用原 epoch，必须与可信 reader 记录逐字节匹配。

receipt_reader 不授予 claim/close/register 权限。执行凭据也不能用作回执读凭据。
query_receipt 可以跨代次读取，但仅允许批准的那个原 request_id，不能改 epoch、
邮箱或主体扩大范围。reader 在代次切换时不随执行凭据清理，进入独立 checkpoint，
与原 owner/模型检查点一致恢复；不因重启复活已撤销读权。

reader 有独立到期时间，最长 300000 时间单位，可以晚于回执保留期，但不延长回执：
读权有效而回执已过期或已清理，返回 request_gone；读权过期或被撤销则 permission_denied；
读权已回收则 unauthenticated。这些结果都不等价于原请求 not_accepted，调用方不得
据此生成新业务 ID 重发。公开查询不返回旧 token、owner 表或跨主体记录。

## 时间、容量与提交边界

now 是可信适配器提供的非负安全整数，不是客户端可任意指定的时钟。时间不能倒退，
bool/浮点被拒绝。游戏 checkpoint 保存 last_now；查询也推进这一可信时间。
begin 的保留窗口为 1..300000，默认 60000，溢出被拒绝。重复 begin 不刷新期限。

回执最多 1024 条，满额拒绝新 begin，不偷偷驱逐仍可查询的旧回执。compact_receipts
每批最多 128 条，只清理到期且不在 inflight 的记录。未知/未决调用即使已超过对外
查询期限，也不能藉清理绕过后续代次切换的收敛要求。finish 仍保留原到期点。

清理事务提交前失败保留记录，提交后丢响应可继续批量清理；可信时间先独立提交，
不能因清理失败倒退。当前代次旧请求仍被 journal 拒绝，过时代次旧请求被 epoch 拒绝，
所以删除查询回执不删除防重执行规则。reader 表最多 64 条，可按默认 16/最大 64 的
有界批次清理已撤销或到期读权；不顺带清理回执或改变游戏效果。

## 证据与范围

新增八个 Python 场景覆盖跨代次/恢复查询、精确主体与读权隔离、过期 gone 与防重放、
读权撤销和恢复、未决回执保留、清理前后故障、严格时钟、容量满额后有界释放。
容量场景使用合成记录，不宣称执行了 1024 次真实游戏业务。

JS/Python 候选 profile 增至 26 次字节请求、51 次夹具命令，实际验证 accepted→
completed、跨代次读、期限结束 gone、清理与撤销后拒绝。正式操作数仍为 38。

这是候选模型的执行回执，不覆盖所有正式 operation 控制回执、业务结果保留、真实
认证/持久化或隐私删除。现有 RelayHarness 的集成与旧协议版本协商仍未完成。
