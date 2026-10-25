# 共享 Grant 与跨 authority 撤销的组合

## 主体、对象与影响范围

本候选复用 `SessionRevokeFanout`、`SharedGrantAuthority` 与已有 permission.revoke 字节入口，
不是新公开操作或跨 authority 原子事务。可信登记的 SharedSession 增加 grant_owner_id，
来自真实 owner，而不是网络请求、Grant 名称、玩家名称或 GameInstance 推断。独立 owner
即使拥有相同 g1、Scope 和 session ID，也必须是不同目标和授权域。

grant 操作的分组绑定是完整目标 binding 去掉 session_id：保留 owner ID、Grant ID、
Scope digest、GameInstance 与原玩家。组 ID 是该规范对象摘要的 grant- 前缀形式。
同组选择必须给出一致 CAS，否则在写入协调意图前拒绝；session/result_read/capability
仍逐会话处理，相同 action ID 不形成共享能力撤销。

**冻结的是授权对象，不是该 Grant 在某时刻的会话清单。** grant_groups 明确返回
impact=entire_grant；session 目标只是受信路由和展示入口。撤销到达时，该 Grant 的全部
当前会话和未消费邀请受影响，包括 begin 后、实际撤销前才加入或发出的对象。目录未登记
的关联会话也不能幸免；提交后原 Grant 的校验阻止继续发邀请/加入。若只希望关闭所选会话，
必须使用 session，不可将 Grant-wide 结果解释成精确会话集合或跨 Grant 永久禁令。

begin 的 catalogue_revision 和 alias 选集仍冻结；后来登记不向旧进度表增加 target。
新独立 Grant/owner 不会自动加入旧任务。这与同一已选 Grant 的依赖对象受影响是两个层次。

## 一份请求与一次组确认

每个共享组只使用一份 canonical 请求：request_id 为 fanout- 加
SHA256(canonical([coordinator_id, operation_id, group_id]))；所有选中 alias 的 raw、对象和 CAS
一致。既有独立目标保持原 target_key 请求命名方式，不将相同 Grant 字符串误合并。

```text
freeze group binding, alias members, CAS, original request bytes
under coordinator lock and selected receiver lock:
    validate complete current receiver binding
    mark every selected group member unknown; save checkpoint
    submit the same frozen request to the selected receiver
if a valid original-request receipt is available and ACK was not lost:
    acknowledge every selected member in one coordinator checkpoint
otherwise:
    retain the whole group as unknown
```

另一 authority 已确认时，当前组失败只能留下 partial，不回滚其他 owner。单组 unknown
的总进度仍是 pending，不能凭远端会话已关闭就报告 done。只有完整原请求回执匹配对象、
状态、关联 ID 和预期 revision 才 ACK；错误回复或丢 ACK 仍保留 unknown。

活动 Grant 撤销预期 revision+1。若 begin 已在可信端口锁内观察到相同 CAS 的 revoked
Grant，冻结 already_revoked，预期 no-op 回复保持原 revision；不能仅因是共享组就接受
活动 Grant 的同 revision 伪 ACK。此已观察状态也进入恢复 checkpoint。

任一组成员都可用于重放同一 raw；不能换 request ID 或将 CAS 自动重基到当前值。
全局 Grant 回执使兄弟端口重放不重复关闭事件、对象 revision 或世界效果。两侧历史读权
仍独立保留，撤销执行权不撤销结果读取权。

## 独立恢复与可信重绑

仅重启协调器时，快照恢复保留当前可信端口映射；快照不能提供端口或凭据。group binding、
members、raw、CAS、already_revoked 和全部进度都进入原有精确类型 checkpoint；删成员、
改 owner/字节/ACK 或使用过时快照均拒绝。

共享 owner 独立恢复会退役旧 owner 和全部旧子端口；旧指针投递不能继续产生效果，也不能
因此丢弃 unknown。可信 rebind_target 只接入以下全部成立的恢复后继：

- 原 owner 已退役，新 owner 存活，同一稳定 owner ID 和**同一个独立 checkpoint 对象**；
- 精确相同子端口类型、完整 session/Grant/Scope/实例/玩家 binding；
- 凭据在当前受信映射中仍属原 player，且使用原可信登记凭据。

UUID 相同而锚点独立的 owner 拒绝。允许连续多次恢复后直接接到最新后继，不要求先接入
已经退役的中间代。新旧端口锁按稳定进程内顺序获取并去重，不合法反向调用也不能制造
两个协调器的反向锁环。重绑不改变逻辑目录 revision、原请求或账本快照；再恢复协调器
仍接回最新可信映射，不能用旧逻辑快照倒换到已退役端口。
重绑本身不发送撤权、不续身份期限；实际 wire 仍由接收方检查当前身份/期限，过期身份
不能因接回新端口而恢复权限，协调组保持 unknown。

上述对象同一性是可信内存恢复链，不是网络认证、UUID 签名或持久化防回滚。未提供远程
凭据轮换、跨进程恢复证明或任意可执行 Python 内存篡改防护。

## 目录退出与容量

组 pending/unknown 时，每个被选中的 alias 仍受所有历史操作的 not_drained 检查。
共同 ACK 后可单独移出一个 alias；兄弟目标、原组回执和历史进度保留。退休后的原 begin、
deliver 和 view 不访问被移除端口，也不撤销另一 owner。原有 16 活动目标、64 墓碑、
64 协调意图上限未放宽，不清除 unknown 换容量。

## 可执行证据

- `tests/test_design_shared_fanout.py`：15 个方法；包含最初重复请求导致只得到 partial 的
  实际反例、同名不同 owner、冲突 CAS、两提交故障和丢 ACK、Grant-wide 迟到会话/邀请、
  非 Grant 隔离、双重恢复/跳代重绑、伪锚点/凭据拒绝、锁序、伪 ACK、快照和退休重放。
- `shared_fanout_peer.mjs` 独立构造目标键、组 ID、命名空间 request_id 与 canonical wire；
  通过 `shared_fanout_interop.py` 运行三个故障链：一个两会话 owner + 同名独立 owner，
  独立侧先 ACK → 共享组 unknown → owner 恢复/旧端口拒绝 → 可信重绑 → 协调器恢复 →
  兄弟端口原字节确认 → 退休与旧回执 → 修改 CAS、旧快照拒绝。
- 新候选子报告为 48 次客户端编码请求、108 次夹具命令，6 个 alias 共同 ACK、3 次可信
  重绑、3 个既有效果保留、3 次旧快照拒绝。调用数包括重试和退休后不再访问接收方的
  原请求回放，不冒充网络往返次数；正式互通仍为 38 操作/503 次 wire，其他候选独立计数。
- `test_design_interop_gate.py` 拒绝缺失/部分/布尔伪装数字的组合报告；总 passed 不能替代
  分组、恢复、效果与完整故障链证据。统一验证预期 861 个方法，实际结果以最终回执为准。

## 外部规范对照

2026-10-25 重新联网读取 RFC Editor 官方原文：

- [RFC 7009](https://www.rfc-editor.org/rfc/rfc7009.txt) §1、§2.1 区分单 token 与同授权
  Grant 的关联失效，并明确传播延迟可能存在。本模型选择明确 Grant-wide 影响范围，
  不把顺序远端提交伪装成全局原子提交，不照搬其 HTTP 响应规则。
- [RFC 9396 §6.1](https://www.rfc-editor.org/rfc/rfc9396.txt) 指出授权细项比较依赖具体 API
  语义，任意对象比较不足以推断权限包含关系。本组合不按 Scope 子集或相同名称合并，
  只按受信 owner 与精确冻结绑定识别同一授权。

仍待继续：多玩家目录、跨 Grant 全局准入/执行屏障、其他共享对象、长期账本回收、真实
持久恢复链和网络身份根。当前补齐共享 Grant 的传播组合，不代表整个场景包或协议完成。
