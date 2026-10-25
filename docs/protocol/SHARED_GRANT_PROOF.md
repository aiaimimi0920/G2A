# 同一 Grant 的多会话授权域与原子撤销

## 目标、owner 与配置

本候选装配补齐 [场景验收](SCENARIO_ACCEPTANCE.md) 中的共享 Grant 场景，不把两个独立
Grant 的 fanout 当作一次共享授权撤销。`SharedGrantAuthority` 持有唯一 canonical Grant、
邀请、全局准入/Grant 撤权回执和时钟；`SharedSession` 复用既有 SessionHarness、动作账本、
事件与结果读权。所有子会话、动作与 owner 共享一个 RLock 排序域。

固定预批准 Scope 绑定一个 player、agent、完整 GameInstance、Grant ID 和 Scope digest。
只接受 core.session/core.events/actions/multi-session、volatile 账本；不接受 team、resume、
handoff、资源、呈现、启动等未经本组合验证的功能。没有 multi-session 时最多一个活动
会话；有该功能时使用已批准 session_count，候选模型最大为 8。ready=false 的接入中会话
也占活动槽。关闭后允许新 ID 使用空闲槽，不允许重用任何历史目标 session ID。

这是单个预批准 Grant 的 owner，不提供跨 Grant/跨玩家的实例级 slot 分配，也未替换
AdmissionHarness 的单会话 profile。可信 `issue_invitation` 只是夹具端口，不是新公开操作，
不伪造 offer 协商或玩家同意 UI。wire 仍使用已有 session.join、permission.revoke、
operation.get 和各子会话的现有操作，版本仍为 fixture-only。

## 邀请、加入和独立会话

可信邀请登记冻结目标 session ID、Grant revision、完整 Scope digest、随机邀请 ID/凭据和
`min(issue_time + ttl, grant.expires_at)`。本 profile 无设备条款，JoinIntent 必须精确等于
登记内容；请求不能改 Scope、玩家或目标实例，邀请 ID 本身也不是认证凭据。

session.join 在同一 owner 事务内验证邀请身份/意图/期限、当前 Grant 和槽位，原子消费邀请
并创建全新子会话。首次返回 join_pending；可信 finish_admission 提交 ready 事件后，原
join 重放才允许返回控制凭据及结果句柄。准备失败、邀请期限已过或会话已关闭，不能发布
新的 ready。邀请消费后不会因重试重新分配槽位。

每个子会话有不同的控制凭据、结果句柄、事件序号、动作与会话撤销 revision。相同的
action ID/局部请求 ID 不合并不同会话。session.close 或 session 对象撤销只建立本会话
写权 fence；不撤 canonical Grant，不推进其 revision，也不关闭兄弟会话。
session 撤销 revision 初始为 1，仅该对象撤销推进，回执返回新值；不冒充 SessionView
已有公共字段或给旧 SDK 增加隐式字段。capability 与 result_read 继续使用各会话独立 CAS。

## 一次 Grant 撤销的提交点

Grant 请求可从 owner 或任一子会话端口进入，但必须路由到 owner，而非在子会话内单独
撤销一份 Grant copy。当前身份、角色、version、消息大小、对象 ID、扩展及 CAS 均检查；
只有该授权域的原玩家或 GameAuthority 有权撤销，伙伴/执行器不能借此升级权限。

```text
lock owner
commit trusted clock/expiry maintenance independently
authenticate current caller and validate request
if global receipt exists:
    require same frozen request bytes
    return original revocation receipt
transaction:
    require object_id == canonical Grant ID and expected_revision == current revision
    if Grant not already revoked:
        set Grant revoked; increment Grant revision once
        invalidate every issued invitation
        close every associated active or joining session
        stop each action's future effects; append each local closed/result event
    save global receipt and trusted full-ledger checkpoint
commit
```

关闭会话不再反向推进 Grant revision。对已经 revoked 的 Grant，新的请求仍需当前 CAS，
匹配时返回当前终态而不再次推进对象 revision；旧 CAS 只有匹配原回执时才允许重放。
全局回执键使用原 Principal、operation、request_id；重放可换到另一子会话端口，仍返回
同一个原回执，不追加 closed 事件。候选恢复使用冻结的原始请求字节，不自动重编码或改 CAS。

三处故障均实际注入：before_commit 与 after_first_close 整体回滚，不能留下只关闭第一侧
的部分提交；after_commit 保留 Grant、所有会话、邀请、回执与 checkpoint，丢回复后可原样
重试。join 与 revoke 的两种先后顺序及真实双线程竞争都受同一个排序域约束：要么先加入
再被此次撤销关闭，要么邀请先失效而不能加入。

## 效果事实、读权与容量

协议事务的回滚只恢复协议知识；MultiStepModel 的独立 world 对象保持原引用，不复制、
删除或重建外部效果。已有 journal 步骤允许按原 ticket 重读；共同 fence 后的新步骤拒绝。
after_effect 未写 journal 的 unknown 不解释成无效果，仍可经可信 reconcile 查证并以
cancelled/partial 结算，不能重新执行未知步骤。效果后发布失败保留 pending_sync，重启后
先发布已有事实再提供查询。执行异常也更新可信协议 checkpoint。

成功 wire 提交同样不得替换独立 world：既有 ActionHarness 的 staged 提交会复制 model，
共享子类型在 submit 出口重新绑定原 world 和 owner 锁，不撤销已提交的协议状态。
回归从首次 request 之前保存对象，逐次检查 request/claim/cancel/commit_result 后的对象
身份；取消与结果提交各覆盖成功、提交前失败、提交后丢回复，再经重启和原请求/步骤重放，
确保已发生效果不丢失、不重复。只比较 world 内容相等不足以证明这个边界。

撤销 Grant/关闭 session 不自动撤销历史结果读权。既有 result_read_handle 仍受各自原成员
代次、读权撤销与保留期限制；撤第一侧结果读权不会影响第二侧。operation.get 对全局
Grant 回执及指定子会话原控制/动作回执分别查询，不创建执行、返回秘密或绕过当前读权。
已经关闭/撤权/过期的 join 原回执只返回 completed_without_secret，不能借重放复活会话。

候选 owner 最多保留 16 个邀请/历史 session ID、64 个普通全局回执，额外预留一个 Grant
撤权回执槽。子会话沿用既有事件裁剪/止损预留。普通回执满额、邀请满额或两个子会话事件
outbox 都满额时，必要 Grant 撤销仍可提交；已受理 join/撤权重放与未知结果查证不消费新
普通槽位。不删除 unknown、墓碑或身份绑定换取容量，也不宣称已完成长期账本 GC。

满 outbox 反例曾实际发现嵌套协议事务替换状态副本，导致关闭写到失效 session 引用。
现由最外层协议事务统一提交，内层裁剪/结果发布加入该事务，不创建伪独立提交；效果执行
不进入该协议事务，效果后的发布仍独立保存/回滚。回归同时检查满队列下第一侧关闭后
故障的整体回滚，以及随后成功关闭全部会话，不能只检查返回的撤权回执。

## 可信恢复边界

快照含 owner ID、完整 Grant/邀请/回执/时钟、各子会话状态/事件/成员及动作协议账本；
摘要区分 map/list/tuple/set/bytes/null/bool/int/str 的精确类型。独立可信 checkpoint 绑定
完整快照及原 fixture/身份/邀请凭据/子端口凭据，输入快照不能自报 credential map 或 world。
旧、外来、混合、容器类型伪装和注入凭据的候选快照拒绝，拒绝不退役当前可用 owner。

成功恢复为新 owner/新子端口接回原可信凭据及独立 world；旧 owner 和全部旧子端口立即
fail closed。不健康恢复和当前凭据完整性不匹配也拒绝继续使用。到期维护先独立提交，
后续错误身份或失败业务事务不能回滚已经到期的会话；受信时钟不能倒退。

旧 ActionHarness 端口曾被独立反例证明可在 owner 重启并撤权后增加一个 world 效果。
现用受控子类型覆盖其 submit/execute/revoke/operation_view：内部写/执行只能从 owner
受控调用栈进入，所有入口都检查 owner 存活；保留旧内部端口不能绕过新 owner 的撤权。
这不是任意 Python 字段访问的内存沙箱，直接篡改模型字段不属于认证 API。

这些是 live memory 与独立 non-rollback anchor 的明确模型前提，不是 hash 签名、真实
数据库崩溃一致性或任意内存篡改防护。同时回滚全部可信账本与锚点仍不在证明范围。

## 可执行证据

- `tests/test_design_shared_grant.py`：31 个方法，覆盖上述邀请、加入、独立缩权、两侧效果、
  三撤销故障、效果后发布失败、join/revoke 排序、CAS/身份、容量与恢复反例。
- `shared_grant_interop.py` / `shared_grant_peer.mjs`：独立手写 JS 编码请求，经真实 Python
  字节入口执行。三条故障链各建立两会话及第三未消费邀请，两侧均已有一个效果，其中
  一侧为 after_effect unknown；恢复、共同撤权、兄弟端口原回执、无秘密 join 重放、迟到
  join 拒绝、原 ticket 查证结算及结果读取贯通。另有 session/result_read 独立撤销链。
- 候选共享 Grant 子报告为 64 次请求、137 次夹具命令，三条链合计关闭 6 个会话、保留
  6 个既有效果、6 次 join 安全脱敏和 1 次旧快照拒绝。正式互通仍为 38 操作/503 次 wire；
  既有候选 fanout 为 28/119、epoch 为 26/51，互不混算，也不算新增公开操作。
- `test_design_interop_gate.py` 对缺失/部分/布尔冒充数值的子报告拒绝放行；总 passed 标记
  不能替代上述共享授权域证据。

本轮曾在第 1124 次夹具命令、503 次正式 wire 后触发旧 60s 整套墙钟预算；诊断为
timed_out=true/elapsed_ms=60043/SIGTERM，并非协议断言不一致。失败回执保留；扩展后的
串行场景采用 JS 120s、Python 150s、统一验证子命令 180s 的嵌套绝对上限，输出实际耗时，
仍以超时失败、非零退出和完整场景断言共同把关，不自动重试、不减少请求或放宽语义门禁。
此预算不是协议性能 SLA，也不证明外层强杀时已回收全部后代进程。

## 外部规范参考与差异

2026-10-25 联网核对官方原文：

- [RFC 7009 §2.1](https://www.rfc-editor.org/rfc/rfc7009.html#section-2.1) 将撤销与同一授权
  Grant 的关联 token 失效区分，并讨论传播延迟。G2A 在此明确采用 owner 内单次原子提交，
  不是将顺序远端 fanout 误称原子撤销；跨 authority 仍必须如实报告 partial/unknown。
  不照搬 OAuth 的无效 token HTTP 200 规则，G2A 继续使用自己的身份、CAS 和回执合同。
- [RFC 9396 §6.1](https://www.rfc-editor.org/rfc/rfc9396.html#section-6.1) 提醒授权细项的
  比较依赖 API 语义，不能用任意 JSON 子集推断缩权。本候选不推断“更小 Scope”，只接受
  已冻结 Scope 的精确绑定；子会话撤权也不改写玩家原批准条款。

## 仍须继续完成

本包完成固定单 owner 的共享 Grant 场景，不代表多玩家、跨 Grant/跨 authority 全局准入
或执行屏障、其他共享对象、完整多 offer 同意流程、独立跨端口查证、动态资源/呈现组合、
长期控制账本清理已完成。生产身份根、持久事务、真实网络/引擎和第三方互通仍为独立门禁。
与既有 fanout 的 [分组传播与恢复组合](SHARED_GRANT_FANOUT_PROOF.md) 已补：同一 Grant
不再各发一次旧 CAS，授权域范围与别名选集分开，独立 owner 重启经受信恢复链重绑。
