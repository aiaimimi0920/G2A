# 玩家消息转发、当前席位与统一事件事务

`player_chat.forward` 已接入 [SessionHarness](session_harness.py) 的请求字节入口，并由
[PrivacyHarness](privacy_harness.py) 的完整准入/控制/隐私组合继承，统一入口由 31/37
增加到 **32/37**。不是把请求改名为 `chat.send`，也不签发一个伪装成玩家的伙伴 token。

## 1. 游戏身份和玩家席位是两份证据

- 外层凭据必须是当前固定实例的 GameAuthority，走 `management` lane。玩家控制、
  伙伴写入、结果读取以及 Relay 的 agent/controller 提交通道均不能代替它。
- `seat_proof_ref` 只引用可信游戏输入端口的内部 `PlayerSeatAuthorization`。网络请求
  不能直接提交证明正文、成员代次或“已验证”标志；一个猜中的引用也不代替游戏身份。
- 内部记录绑定 proof ref、完整 instance/epoch、session、批准 Scope 的规范摘要、
  GameAuthority、玩家 Principal、当前 membership revision、成员 incarnation、
  issued_at/expires_at 与 active/revoked 状态。成员代次和时间必须为整数，不能用 bool。
- `envelope.sender` 必须等于该记录中的玩家，且 kind 为 player。即使游戏端登记了一条
  指向 agent 的假证明，也不能因此冒充伙伴发言。
- 每次调用先验证当前会话/Grant/ready/租约及席位，包括重复消息。证明缺失、畸形、
  已撤销、过期、换会话、换游戏、换 Scope 或换主体均保守拒绝，不查询别人的收据。

此 profile 保守要求证明中的 membership revision 与当前值完全相等；其他成员的变化
也要求刷新证明。退出再加入还会增加 incarnation，不能仅更新旧证明的 revision 复活
旧席位。更细粒度的席位证明缓存可另行设计，不能默默放宽本次绑定。

**证明的边界**：这里核验的是固定登记的身份/席位映射，不证明某段正文确由真人键入，
也不能阻止已受信任的游戏谎报输入。真实游戏登录、输入通道、签名和撤销事件仍须独立
适配器验证。它不是“任意游戏说自己有玩家就可信”的认证方案。

## 2. 私聊、队伍与批准范围

核心 private 仍只允许原玩家和伙伴，队伍玩家不能借转发进入这条私聊。team 必须协商，
且新消息携带当前 `expected_membership_revision`。发送者及所有接收者都必须在当前
成员表和原 Scope 中；接收者 incarnation 在事件接受时冻结，退出重入不能领取旧事件。

[AdmissionHarness](admission_harness.py) 的 team profile 使用固定、可信的
`verified_audiences` 登记表。所选 Scope 只取请求受众与该表的交集；未协商 team 时仍限
原玩家和伙伴。新受众展示在冻结 Offer/Scope 中再批准，不从 `Requested.audiences`
自报完成认证。`membership.replace` 可以更新成员，但不扩大原批准的披露范围。

这个登记表不是自动发现服务，也不是其他玩家的来源披露同意。带来源的内容仍须逐来源
验证所有读者，包括 Scope 声明的 game/其他明文观察者。

## 3. 一个消息事务，不为游戏转发续伙伴租约

```text
bytes -> codec/schema -> exact game role/instance -> writable session/Grant
      -> current trusted player seat -> (session, player, Envelope.id) dedup
      -> active/frozen extensions -> source authorization -> frozen audience
      -> stage event + Receipt -> validate/encode reply -> one snapshot commit
```

业务摘要只覆盖规范 Envelope，和其他消息操作保持一致。`request_id` 是传输关联，
席位引用属于当前授权证据；二者都不能建立第二份业务消息。换一个仍然有效的席位证明
或外层 request_id，原 Envelope 返回 duplicate；修改正文、频道、受众、来源或可选
扩展仍是 `id_conflict`。不同玩家的同 ID 各有独立收据，游戏主体本身不是去重 sender。

在当前席位重新获得验证后，重复请求可以读回原来不含正文的 Receipt；不会重做旧
team revision 下的接受，不会重建已被裁剪的事件，也不会把旧消息重新授权给新成员。
当前会话已关闭或 Grant 已撤销时则禁止该写入口；这不是闭会后的通用历史查询 API。

复用 [活动扩展校验](contract_checks.py) 和 [来源披露检查](source_authorization.py)。
测试扩展 `example.max-chat-bytes` 同样限制玩家转发，按 UTF-8 字节数计算；未知 required
扩展不能绕过。来源必须授权真正的玩家 publisher，不把转发游戏的权限借给玩家。
接收端验证仍不能收回其已经收到的明文，也不能识别未声明的自然语言泄露。

接受与重试均不修改伙伴 lease；游戏代玩家说话不能证明伙伴仍存活。64 个 outbox 槽和
256 个消息收据的现有限额继续生效；容量拒绝不会留下半份事件/收据。

## 4. 回滚、丢回复、隐私与恢复

| 情况 | 已有证据与处理 |
| --- | --- |
| 席位/身份/受众/来源/扩展失败 | 未接受，事件、收据和 lease 不变 |
| before_commit 或回复编码失败 | 事件和收据同事务回滚；证明不被消费 |
| after_commit 丢回复 | 原消息已经接受；同 ID/内容重试只返回原收据 |
| 成员退出重入 | 旧席位失效；旧事件冻结的接收者 incarnation 不恢复 |
| 来源 cutoff/revision 撤销 | 新消息拒绝，重复 poll 重新过滤旧事件；已收到的正文无法撤回 |
| PrivacyHarness 接受带来源转发 | 同事务记下游戏 outbox 的已知外部副本，不把伙伴删除说成全局擦除 |
| 假账本重启 | 保留当前席位表、消息收据、outbox、成员代次和隐私记录；不再次接受原消息 |

生产网络发送与席位/来源撤销之间的跨进程屏障、真实持久恢复、证明签发/轮换/回收均
没有在本包完成。所有席位登记和故障驱动只属于测试端口，不是新公开操作。

## 5. 本地验证

[test_design_player_forward.py](../../tests/test_design_player_forward.py) 有 **33 个方法**：
既包括单会话负例，也包括完整准入组合、队伍受众协商、隐私 cutoff、假账本重启和
真实双线程重复请求。验证结果应以同轮最终回执为准，不把子例数量混为测试方法数。

[独立 JS 客户端](../../scripts/design_interop_client.mjs) 从空 authority 开始，走真实
操作字节完成批准、邀请、加入、席位引用转发、成员变更、来源过滤及重启后的重复查询。
夹具的 seat/membership 登记命令是可信输入，不算公开 wire 操作。当前合计 **23 组
编码正反例、190 次 wire 调用、30 个操作**；本包实际接受 4 条玩家消息并保留 4 份收据，
重入成员代次为 2，cutoff 过滤 1 条带来源消息。

完整设计验证入口为 `scripts/verify_design.py --interop`：本轮累计 **383 个设计方法**，
原 **42 条纯内存模型轨迹**另计。完整验证、跨语言及最终 hash/编码/AST/链接回执位于
`C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007`：

- `player-forward-final-verification.json`
- `player-forward-cross-language-final-verification.json`
- `player-forward-final-hygiene.json`

首轮 JS 的末尾断言预期 close 后 `session_closed`，实际现有 close 会同时撤销 Grant，
写检查按既有顺序返回 `grant_revoked/not_accepted`。已修正测试预期，没有为了让测试
通过而改变关闭或授权语义；首轮失败回执保留，不冒充全部通过。

## 6. 剩余范围

五个 Relay 入口仍未装配，见 [操作范围表](SESSION_OPERATION_COVERAGE.md)。真实玩家
认证/输入真实性、任意多会话、多厂商互通、持久存储与网络发送原子性仍是独立验证项。
本包只改协议草案/模型/测试；不修改旧 SDK，不启动真实应用，不提交推送、部署或运行
GitHub Actions，不将字段齐全或局部装配计作全协议认证。
