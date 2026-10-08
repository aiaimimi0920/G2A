# 原请求回执汇总与结果状态分离

本工作包承接 [设备生命周期](DEVICE_LIFECYCLE_PROOF.md)，不新增公开操作。固定组合入口仍为
38/38；补齐已有下层控制收据与动作状态的安全投影，不把账本内容直接序列化给调用方。
范围是协议契约、可信身份夹具、内存模型与 JS/Python 子进程字节链，不是生产服务。

## 1. 查询键、归属与可见字段

`operation.get` 仍只向已认证的原 `agent` / `player` 开放。控制写凭据、结果句柄、执行器、
游戏管理身份、隐私主体或 Relay 外层凭据不会因此取得新的控制查询权。可信身份登记包含
`expires_at` 时必须重新检查有效期；身份相同不等于拥有所有下层结果的读取授权。

| 原操作 | `original_request_id` 的来源 | 输出与边界 |
| --- | --- | --- |
| offer.create / offer.decide / invitation.redeem / session.join | 原外层 request_id | 复用原主体收据；不返回邀请秘密或控制凭据 |
| session.resume / session.handoff / session.claim_control | 原外层 request_id | 原控制流程状态；目标秘密仍只能经专门领取入口 |
| session.heartbeat / session.close | 原外层 request_id | 原收据中的 SessionView，不续租；不是重新采样的当前会话 |
| session.events | 原 poll_nonce，也就是外层 request_id | 仅报告原 poll 已提交，不重放事件正文、游标页或恢复快照 |
| permission.revoke | 原外层 request_id | 只返回原主体的 RevocationResult；邀请 consumed 不改写成 revoked |
| action.confirm | 原外层 request_id | 只供原玩家查询已记录的 confirmation_id；不再签发、消费或恢复确认权限 |
| action.request / action.cancel | 原 Envelope.id | 原 Receipt 和当前获准的 ActionResult；取消使用取消消息自身 ID，不是目标动作 ID |
| presentation.acquire / renew / release、asset.resolve、launch.request | 各原本地工作请求 ID | 沿用各 owner 的安全投影与先前工作包规则，不新增跨 authority 权限 |

message 族的外层 `request_id` 只是传输关联，不能新增为业务幂等键。这里没有建设第二份
索引或复制收据缓存，而是复用现有有界账本；同一个 Envelope 换传输 ID 重试仍只接受一次。
动作请求/取消查询的 `OperationView.request_id` 对应上述业务键；外层 Reply.request_id
仍对应本次 `operation.get` 请求，两者不能混淆。

聊天/情境/玩家转发消息的通用回执查询没有在本工作包开放；它们沿用业务 ID 重试和事件
读取路径。纯 read 操作没有凭空生成收据。游戏管理/执行器私有回执、隐私和 Relay 独立
账本也不因“汇总”而跨权限域开放。未知、不归属或无读权的键统一拒绝；拒绝不证明原请求
从未接受，客户端不能据此换业务 ID 重执行。

## 2. 原请求完成，不等于当前对象可用

- join 的首次 ready 提交记录在 admission 状态中；之后 handoff 暂时 ready=false，或关闭
  会话，都不将原 join 从 done 改成 pending/failed。尚未 ready 就关闭才为 failed。
- resume/handoff/claim 的 ready 是原控制流程的完成事实。后续关闭、升代或换 transport
  阻止秘密重放，但不会倒改已完成请求。附带的 join/resume SessionView 是当前会话；
  handoff TransferView 是对应原转移记录。不要把它们与 heartbeat 的原响应快照混用。
- action.request/cancel 的 done 只证明接受收据已提交，不能当成世界动作成功或已回滚。
  例如 `state=done, action.state=unknown, action.effect=undetermined` 是合法且必要的结果。
  取消后仍可返回 `cancelled/partial`；已提交动作仍保留 `succeeded/committed` 和获准结果。
- `action.confirm` 的 done 是确认记录完成，不证明许可现在仍未消费、未过期或可执行。
- 设备无原 ACK 的 pending、fresh 重启证据及本地停止补偿继续遵守前一工作包，不将本轮
  对已知控制终态的修正推广成“关闭所有未知请求都算 done”。

## 3. 读权与事务边界

[ActionHarness.operation_view](action_harness.py) 在暴露动作 ID、Receipt 或结果之前重验：
原 agent、独立结果读权未撤销、保留期、原成员代次与当前成员可见关系。离开后重新加入
不会恢复旧事件/动作读权；`result_read` 撤销也不能从 `operation.get` 绕过。

查询不领取 ticket、不执行/对账世界步骤、不重新确认、不消费新的收据槽，也不续租。
动作效果已发生但事件结果提交未完成时，`pending_sync` 拒绝读取旧投影，不在查询中偷偷
补跑效果。既有 `_maintain` 可信时钟维护仍可独立提交到期关闭；launch 查询也仍可导入
已有可信启动结果。这里的只读保证不是取消既有安全维护，而是查询不产生新的业务效果。

准入与 SessionHarness 共用同一锁域。跨两层的 `permission.revoke` 仍使用同一主体、操作、
request_id 命名空间：相同 ID 改为另一个对象族必须 id_conflict，不能各层各接受一次，
再让查询随查找顺序随机返回其中一份。原结果读取不依赖日志还有新写槽。

## 4. 反例与实际验证

[test_design_operation_status.py](../../tests/test_design_operation_status.py) 新增 29 个方法，
覆盖完成后关闭/新代、pending 失败、原 nonce、两个 ID 域、受理与效果分离、partial/unknown、
读权撤销/过期/成员重入、确认消费、权限域、满日志、提交前后故障与假账本重启。
旧准入测试中将成功 join 在关闭后期待为 failed 的断言同步修正，秘密隔离断言仍保留。

第一轮新测试在修复前实际暴露终态和缺失查询失败；测试构造中不合法的 cancel.reason
随后修正，不将该夹具错误算成产品反例。额外反例实际复现跨层 revoke 相同 ID 各自成功，
修复后双顺序均拒绝第二个不同请求。原始日志保留，不覆盖历史生命周期回执。

JS/Python 独立客户端实际新增 action.confirm / action.cancel，现 **38 个操作、312 次 wire、
23 组 codec 正反例**。新增链保留 **1 次世界效果、1 份已消费确认、2 份动作收据**；
取消后 partial，关闭和假账本重启后查询仍保持原事实，查询前后这些计数及 lease 不变。
随后撤销结果读权，两个动作查询均被拒绝。此前其他场景的 2 步完整动作等证据单独保留。

完整验证预期累计 505 个设计方法与原 42 条轨迹，最终是否通过以本次回执为准。文件位于
`C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/`：

- `operation-status-start-manifest.json`：开始时前一工作包 99 个源哈希全部匹配。
- `operation-status-red.log`、`operation-status-seams-red.log`：修复前失败证据。
- `operation-status-final-verification.json`：完整设计测试、生成检查、重放与互通。
- `operation-status-cross-language-final-verification.json`：独立互通最终复跑。
- `operation-status-final-hygiene.json`：源哈希、改动清单、编码、AST 和本地链接。

## 5. 停止条件与剩余范围

本包以原 agent/player 控制收据、动作受理/结果查询、跨层唯一 ID 和终态语义的字节链及
匹配回归通过为停止条件。固定单会话/单动作限制、长期保留与清理、其余撤权对象、自动
规则、preinstalled、多配置组合等继续见 [范围台账](SESSION_OPERATION_COVERAGE.md)。
没有真实身份、网络、磁盘、引擎、运行中服务或第三方实现证明；全部入口被夹具调用不等于
全部配置/交错/业务情况通过。未改旧 SDK、未提交/推送/部署，未运行 GitHub Actions。
