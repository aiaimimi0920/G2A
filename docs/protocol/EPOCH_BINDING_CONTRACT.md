# 代次身份绑定候选合同与字节参考端口

## 状态

`g2a-epoch-binding-1` 是独立设计 profile，由 `epoch_binding.py` 的 EpochBoundPort
接入 EpochRotation。它不是对现有 g2a-design-1 wire 的兼容升级，也不增加正式操作数。
使用既有严格 JSON codec，但目前只覆盖可信配对登记、领取 claim 和 controller 关闭。
pull/reply、业务结果读取及正式 RelayHarness 接入仍须单独完成。后续已补
[候选执行回执归档](EPOCH_RECEIPT_PROOF.md)，不等于全操作控制回执或业务结果查询。

## 公开绑定对象

对象必须恰好包含下列字段，不允许省略、增加或自动补齐：

| 字段 | 约束 |
| --- | --- |
| version | 必须为 g2a-epoch-binding-1 |
| authority | 固定 Relay authority 标识，非任意 URL |
| instance_id | 与代次模型的持久实例 ID 一致 |
| epoch | 0..2^53-1 的整数，bool 不作整数，必须为当前 Relay 代次 |
| kind | pairing 或 mailbox |
| mailbox_id | pairing 必须为 null；mailbox 为 1..8 的整数，bool 拒绝 |
| principal | 可信端口验证的主体标识，非调用者自报身份 |
| role | pairing 为 controller；mailbox 执行凭据为 controller、agent 或 game；独立回执读权为 receipt_reader |

字符串标识长度 1..128；编码输入最大 4096 字节。重复 JSON key、NaN 等继续由已有
codec 拒绝。缺少 epoch 不得默认成当前代次，旧版本不得自动升级。对象不携带凭据。

## 可信证据与权限

可信登记端口单独交付 opaque token 和绑定对象。请求携带的公开绑定不是授权依据；
必须与 token 在可信登记表中对应的完整对象进行规范化字节比较。只有 token 命中、
authority/instance/epoch 全部匹配、且角色许可时，才能进入参考状态机。

| 行为 | 证据要求 |
| --- | --- |
| register | 当前代次 pairing/controller；一次同意不能重复消费 |
| claim | 当前 mailbox 的 controller 或 agent；game 角色不能代替调用者 |
| close | mailbox/controller，且 principal 是原批准该 mailbox 的主体 |
| query_receipt | 独立 receipt_reader，精确原主体、完整旧 mailbox 和原 request_id，不要求旧 epoch 等于当前执行代次 |

同一 request_id 按 mailbox 完整身份和 principal 隔离，跨主体不会共用游戏去重键。
claim 返回的是模型内部可信见证，不是可直接从任意 JSON 构造并送入游戏的公开凭据。

## 切换与回收

Relay 封存和游戏切换之间不发行未来代次 pairing，也不把旧 token 重标记为新 epoch。
只有 Relay 提交新 epoch 后，端口才清理旧登记表和 owner 映射；旧 token 即使把公开
epoch 字段改成新值也不能使用。局部 mailbox 编号复用不产生完整身份复用。

登记表每代次最多 64 条。新代次的同意必须由可信端口重新产生，不从客户端重放
旧证据推断。真实适配器必须认证可信发行端口；UUID fixture token 不构成生产认证方案。

## 恢复限制

直接创建新端口仍默认拒绝所有旧 token，不能因模型账本恢复就默默恢复凭据。
后续已补 [登记表与原 owner 的检查点恢复](EPOCH_BINDING_RECOVERY.md)：仅在独立凭据
checkpoint 与代次账本 checkpoint 均通过时恢复原 token/owner。该能力是内存快照
参考模型，不是持久数据库实现；可信锚点丢失时仍拒绝，不能用新发 controller 凭据绕过归属。

## 本地证明

新增 11 个测试覆盖字节绑定→登记→领取→游戏执行→关闭→代次切换→重新登记链，
旧证据改 epoch、跨 authority/instance/mailbox/principal/role、缺字段/未知版本、
bool 整数混淆、角色与 pairing 混用、主体去重隔离、切换间隙、登记表容量、严格 codec
和重启后的 fail-closed。后续已补 [JavaScript/Python 字节互通](EPOCH_INTEROP_PROOF.md)，
覆盖恢复与代次切换；仍不代表现有 Relay wire 接入或第三方实现认证。
