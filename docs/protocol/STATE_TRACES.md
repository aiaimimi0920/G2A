# 全操作状态轨迹与验收责任

这是逐操作的**设计级符号推演**，不是 38 次真实 HTTP 调用日志。每行使用具体前态、输入、
提交点、后态和反例核对目录与伪代码。机器检查只能证明表中操作与目录一一对应，不能代替
这些语义推演。自动证据另列；缺少运行适配器时不标记生产验收。

本表保留最初推演的证据描述；后续逐项统一装配状态见
[SESSION_OPERATION_COVERAGE](SESSION_OPERATION_COVERAGE.md)，不要把旧的“未证”当成当前
唯一证据，也不要把本表 38 行都视为已执行的字节链。

记号：P=玩家 Alice，A=伙伴 Fox，G=游戏权威，S1=会话，g1/g2=控制代次，r1=请求，
a1=动作请求，D1=描述 revision 1。所有身份都包含 issuer/subject/kind，先由端口验证。
同 ID 重试的前提是主体/受众/内容相同、原收据仍可读取；改变任一内容不是同一次请求。

## 1. 控制与会话

| 操作 | 前态与输入 | 提交点及成功后态 | 失败或重试推演 | 语义来源／自动证据 |
| --- | --- | --- | --- | --- |
| describe | 已验证 A 请求实例 I1，D1 有完整动作目录 | 只读投影 D1，不生成 Grant/租约 | 未认证者仅可走公开最小发现；不能以 ID 取得团队或授权信息 | PROTOCOL §2/6；字段/角色测试，身份端口人工推演 |
| offer.create | A 从 companion 入口请求 D1 的 action=find-key；或 P 从 game 入口选择 A | 冻结 Scope Q1、摘要和期限，原子写 O1 pending 与控制回执 | D1→D2 在批准前使 O1 stale；同 r1 复用 O1，不重建申请 | CONTROL §3/4；8 MAIN、T02、关系测试 |
| offer.get | O1 属于 P/A，r2 查询 | 只读 O1 当前状态，不续租、不交秘密 | B 知道 offer_id 也拒绝；O1 后来 approved，查询可反映新状态 | CONTROL require_owned_offer；结构/角色测试与人工推演 |
| offer.decide | P 看到 O1.scope_digest，decision_ref 验证通过 | 一次事务 O1 pending→approved，创建 Grant G1 和回执；拒绝则 denied 且无 Grant | 变更摘要拒绝；相同 r1 回包丢失仍为一个 G1；remember 不等于 launch_permission | CONTROL decide；T01/T02/T23、审批条件测试 |
| invitation.redeem | A、O1 approved、G1 active、固定 JoinIntent J1 | 写 I1 及 J1 摘要，一次返回 A 专属邀请凭据 | 同 J1 重用 I1，改设备观察 redemption_conflict；过期/撤销不创建会话；不可回放秘密时返回 SecretStatus | CONTROL redeem；T04、T14、秘密状态 schema 测试 |
| session.join | A 持 I1，G1 有效；尚无 S1 | 同事务消费 I1、创建 S1 active/ready=false；资源与呈现成功后 ready=true 才交 g1 写权 | 并发重复指向同 S1；准备失败闭会并 release；等待时 join_pending，不提前交秘密 | CONTROL join、PRESENTATION admission；T04/T05/T15、M01 |
| session.heartbeat | S1 g1 当前写权，request_id=h1，租约未过期 | 写一次 h1 回执，租约=min(now+period,G1.expiry)，排出设备租约更新 | 重复 h1 返回原期限；旧 g0/transport 拒绝；到期先闭会并提交，不能异常回滚闭会 | CONTROL heartbeat；expiry/transport_epoch 补充检查，关系写权测试 |
| session.snapshot | A 当前写权读取 S1 | 同切点返回无秘密 RecoverySnapshot（会话/cursor/可见动作/情境/定义/成员），不续租 | ready=false 或已关闭写凭据不通过；结果查询另走只读授权，不复活 S1 | DATA authorized_control、PROTOCOL §8；EVENT_RECOVERY_PROOF 消费验证；服务端快照原子性未证 |
| session.events | S1 cursor=0，事件 1 不可见，2/3/4 可见，page_size=2 | 扫至 3 返回 2/3 与 cursor=3，记录 poll_nonce；下一页能读 4 | 旧 cursor 给过滤后的 history_gap，不续租；同 nonce 不重复续租；重加成员不能读旧代事件 | DATA read_events；T10/T11、分页补充检查、成员代次测试 |
| session.close | P/A/G 有相应关闭权，S1 active，有 pending a1 与 executing a2 | 事务 closed/ready=false；a1 cancelled/none，a2 unknown/undetermined；撤写权、保读权、排 release | 重复关闭无新效果；Renderer 失败不伪称恢复，按实际状态/租约收敛 | CONTROL close；MAIN、模型状态接缝、M03/M07 |
| session.resume | A fresh 身份，S1 durable、resume 已协商、g1、租约有效，同设备 | 回执与 g1→g2 同事务；旧动作 fence；设备 rebind 完成才交 g2 | 原 r1 重试复用 g2；新 r2 带旧 expected_generation 拒绝；后来 g3 时 r1 只返 completed_without_secret | CONTROL resume、BINDINGS protected_receipt；T16/T24、秘密状态与模型接缝测试 |
| session.handoff | P 明确批准目标设备 B，S1 ready/g1，目标 A 身份与设备证明有效 | g1→g2 且 ready=false，先释放旧设备，再获取 B；ready 后保存目标响应 | 旧 release 未 ACK 且租约未到不得 acquire；失败闭会不恢复 g1；P 只取 TransferView | PRESENTATION §5；T14、M02、目标视图拒绝秘密测试 |
| session.claim_control | A fresh+设备 B，对已 ready 的 transfer T1 赎领 | 原子核对 S1/G1/期限/当前 g2，读取原 g2 ControlDelivery；不再升代 | 未 ready 给 pending；g3/closed 不交秘密；原发起玩家身份不能赎领；同键内容冲突拒绝 | CONTROL claim_control、通用控制回执；角色/秘密状态 schema，端口人工推演 |
| operation.get | P 查询自己 audience 下 offer.decide 的原 r1 | 返回 OperationView 与有权读取的 outcome_ref，不续租或重新执行 | A 不能枚举 P 的审批回执；玩家查询 handoff 不获得 A 写权；tombstone 返回 request_expired | BINDINGS §3；公开视图拒绝凭据测试、M04 |

## 2. 消息、动作与游戏管理

| 操作 | 前态与输入 | 提交点及成功后态 | 失败或重试推演 | 语义来源／自动证据 |
| --- | --- | --- | --- | --- |
| chat.send | S1 当前 A，message m1 给 P，来源允许披露 | 同事务保存收据与冻结成员代次的事件；新消息可续租 | 同 m1 改文本 id_conflict；team 无能力或 revision 过期拒绝；聊天文字不创建批准 | DATA submit/accept_chat；MAIN、T11、关系/团队字段测试 |
| action.request | S1 当前 A、a1、find-key revision 1、room=hall、参数/定义摘要匹配批准 | 同事务 pending ActionRecord、收据、通知；若需单次确认则原子消费 | 未授权参数/新动作拒绝；重复 a1 返回收据而非再执行；效果前还需核权 | DATA accept_action；MAIN、T06/T07/T18、动作 schema/Scope 摘要测试 |
| action.cancel | 取消消息 c1 指向自己的 a1 | pending→cancelled/none；executing 增 fence 并记录 stop_requested | 已开始的 effect 可能完成；重复 c1 不再 fence；终态只返回实际状态，不伪造取消成功 | DATA accept_cancel；T06/T07、M03 |
| action.query | 原 A/P 或解析出的结果读授权，S1/a1 | 只读实际 state/effect/result_revision，关闭后仍受独立读取期限保护 | 句柄丢失可 fresh 原主体核对旧读授权；读权撤销拒绝；过期/丢账本不称未执行 | DATA query_action；MAIN/T08/T09/T16、只读关系测试 |
| action.confirm | P 对 S1/a1/find-key/参数与定义摘要/期限作一次可信决定 | 保存未消费 confirmation_id 和同请求回执；不创建 ActionRecord | 改任何绑定字段后不能用于原动作；A 不可自签；第二次新动作 ID 不可复用已消费确认 | DATA confirm_action；角色/字段测试及本表符号推演；可信 UI 端口未实测 |
| context.publish | G 发布 S1 已开放 room 类别，event c1 给 P/A | 验证 G、类别、受众；事务写共享经历来源、事件与游戏收据，不续 A 租约 | 未开放类别或伪造其他游戏经历拒绝；同 c1 重复无第二事件 | DATA publish_context；MAIN、来源补充检查、Scope 子集测试 |
| player_chat.forward | G 持当前 P 席位证明，绑定 instance/session/Scope/成员 revision 与 incarnation，Envelope.sender=P | 私聊/队伍和来源校验；按玩家与消息 ID 拒重，事件/收据同事务，不续伙伴 lease | 旧席位/过期/跨主体拒绝；刷新证明不重收旧消息；重入不恢复旧事件，cutoff 重新过滤 | DATA game_forward_player_chat；PLAYER_FORWARD_PROOF、33 个专项方法及 JS/Python 字节链；真实席位认证另验 |
| capability.replace | G 在能力 revision=1 时提交替换定义 | CAS→2；影响旧动作则 pending 取消、executing fence；新增定义不加入旧 Scope | expected_revision=1 再新提交冲突；同控制 r1 返回原 revision；改名或改义需新批准 | DATA replace_capabilities；T07、动作 ID 唯一和批准摘要测试 |
| membership.replace | G 在成员 revision=1 移除 P，之后再次加入 P | CAS 每次升 revision，重加入成员代次从 1→2；旧冻结投递仍为 1 | 新成员不自动进入旧 Scope；旧队伍消息不给重加 P；同控制 r1 不重复升代 | DATA membership_replace；T11、成员代次关系测试 |
| permission.revoke | 有权 P/G 指向 G1 或其他明确对象类型 | G1 revoked 升 revision、撤邀请并闭相关活动会话；只撤 auto_rule 不闭已有 S1 | 撤错对象无权；已消费邀请返回 consumed 不谎称 S1 已关；result_read 撤销仅作用于读授权 | CONTROL revoke、PROTOCOL 撤销表；T05/T07、Grant/读权测试，细分对象人工推演 |
| action.claim | 已登记 executor 请求 S1 pending a1 | 同事务 executing、唯一 ticket/fence/worker；返回不可变参数 | 新 r2 不能再次领取 executing；原 r1 可读原 ticket，但 step 仍不可重复；过期取消不签发执行权 | DATA claim_action；MAIN/T06/T07；执行器端口排序契约 |
| action.commit_result | 原 executor/ticket 对 a1 提交可信 fact | 原事实汇总后持久结果、result_revision 和通知；旧代 ticket 仅报告事实 | terminal 同摘要幂等，不同摘要 execution_conflict；unknown 可由原事实解决；不能产生新效果 | DATA commit_result；T08/T09、M03、结果状态关系检查 |

## 3. 外部端口、隐私与 Relay

| 操作 | 前态与输入 | 提交点及成功后态 | 失败或重试推演 | 语义来源／自动证据 |
| --- | --- | --- | --- | --- |
| launch.request | O1 已批准且 P 单独允许启动固定注册应用 | authority 接受/许可消费→派发标记→独立 Launcher 效果→结果收据；返回 started/already_running 或失败/unknown | 未许可不启动；失败撤未使用 Grant；丢回复查原结果；未知保留 pending，不重启、不因历史进程记录进入 ready | [LAUNCH_PROOF](LAUNCH_PROOF.md)、test_design_launch.py；T03、M09；OS 端口未实测 |
| asset.resolve | S1 已选 manifest，来源/依赖策略已批准 | 图检查、逐跳受控下载、精确 size/hash、隔离解析，成功才发布 verified cache/receipt | 依赖引入陌生 origin、循环、超限或损坏则失败，admission 不 ready；缓存需绑定 parser/policy revision | PRESENTATION prepare_resources；T15、资源图关系测试、M05；真实下载/解析未实测 |
| presentation.acquire | S1 g1 已批准设备 D，未释放、期限有效、用户 revision r | 幂等占用与实际 Renderer 结果落盘；按最新 baseline 重算 | 先 release 后迟到 acquire 被 tombstone 拒绝；CAS 失败不覆盖用户新意图；失败撤本次占用 | PRESENTATION acquire；T12/T13/T25、M02；真实 Renderer 未实测 |
| presentation.renew | S1/g1 ready，设备 epoch e1 当前占用 revision 1 未到期，游戏存活提交签发 revision 2 | 精确 authority/Scope/条款/epoch 证明；设备更新期限先提交，authority ACK 后提交，不重复渲染或反向续游戏租约 | 未应用旧 revision 拒绝；旧 ACK 不降版本；过期/tombstone 不复活；重启须 fresh 验证；未知 ACK 不因关闭变成未执行 | [DEVICE_LIFECYCLE_PROOF](DEVICE_LIFECYCLE_PROOF.md)、test_design_presentation_lifecycle.py、JS 字节链；无真实设备 |
| presentation.release | 有权释放 S1/g1，其他 S2/g2 仍占用 | 先写 S1/g1 tombstone，只移除该占用，再应用当前集合结果 | 重复 release 不影响 S2；渲染失败记实际状态、不谎报恢复；墓碑保留覆盖旧证明期限 | PRESENTATION release；T12/T25、M02 |
| privacy.request | 独立 data_subject 对实际控制者有每条来源主体权，privacy-request 已协商 | 同事务 cutoff/去重→派发标记→独立假存储效果→可信 done/partial/denied 回执；部分或外部副本显式例外 | 非本人或跨控制者整批拒绝；结果回滚不复原副本；派发缺口/无可信回执保持 pending，新 ID 不绕过未决范围 | [PRIVACY_PROOF](PRIVACY_PROOF.md)、test_design_privacy.py；DATA/M06；无真实删除 |
| privacy.receipt | fresh 原数据主体查询自己的 privacy_request_id | 读取已保存状态或原 provider operation；精确绑定可信回执后提交处理进度，不派发新删除 | 外人知 ID 也拒绝；游戏关闭/Grant 撤销不撤独立查询权；畸形或自报完成无效，已知终态不被查询回退 | [PRIVACY_PROOF](PRIVACY_PROOF.md)、test_design_privacy.py；只读 byte 链与跨语言夹具 |
| relay.register | relay_controller 持 G/P/A 配对与固定 I1、origin/operator 证明 | nonce/回执/邮箱与三类外层 capability 同事务建立；只通过各自认证接收方交付 | 不受信任 target URL 不登记；重试不创建第二邮箱；配对不能被新 nonce 重用；注册响应无 secret | [RELAY_PROOF](RELAY_PROOF.md)、test_design_relay.py、JS 字节链；M08；无真实配对 |
| relay.call | 外层 agent/controller 与内层身份分别验证，I1 mailbox open，固定 route revision | 一次入 queued，冻结内层 OperationRequest/proof/有效 deadline；预留 claim 回包空间 | 完整内层条件校验；重复不延期限；原路径未派发终态才 not_accepted，claimed 超时 unknown；缓存授权变化不重执行 | [RELAY_PROOF](RELAY_PROOF.md)、test_design_relay.py、JS 字节链；T19/T20/T22 |
| relay.pull | relay_game 在 open mailbox 用 pull_nonce p1 | 同主体 FIFO/主体轮转，项数/字节双限，queued→claimed 与 p1 回执同事务 | ACK 丢失返回原批次；原空批次仍空；新 nonce 不重领 claimed；过期/关闭不重放旧 proof；假重启保留 claim | [RELAY_PROOF](RELAY_PROOF.md)、test_design_relay.py、JS 字节链；T21/M08 |
| relay.reply | 原 relay_game/claim owner 提交原 request_id 的合法回复 | 验证内层/外层包装大小、输出/错误 schema，claimed→replied 与控制回执同事务 | 相同响应幂等，矛盾 reply_conflict；过期/关闭 request_gone；游戏后坏回包 unknown，结果回滚不撤游戏效果 | [RELAY_PROOF](RELAY_PROOF.md)、test_design_relay.py、JS 字节链；M08 |
| relay.revoke | 原 controller 对 mailbox route_revision=1 撤销 | 专用止损收据格、closed/revision=2/三类 capability 撤销与 queued/claimed 分类同事务 | 已派发 unknown；不回滚世界或续游戏 lease；旧 token 拒绝，fresh 原主体只能查原无秘密终态；假重启保留关闭事实 | [RELAY_PROOF](RELAY_PROOF.md)、test_design_relay.py、JS 字节链；T22/M08 |

## 4. 本次交叉核对的修订

在把每行的输出与 schema 对照时发现：原 `protected_receipt_view` 可以返回 pending 或
completed_without_secret，但邀请/恢复/目标领权的输出类型并不都接受它。这会让正确的
安全降级被序列化层错误拒绝，甚至诱使实现重新返回秘密。

现已增加统一 SecretStatus：`{status:pending|completed_without_secret,outcome_ref,reauth_required}`。
它不携带凭据；invitation.redeem、session.join、session.resume、session.claim_control 均可
返回它。直接 join 的 join_pending/already_joined 仍保留，不能解释为已交付当前写权。
不可见 outcome 的主体仍拒绝，不通过 SecretStatus 枚举对象。

本表还揭示隐私外部处理可能挂起：PrivacyReceipt 需显式 pending 视图，不能为了满足
done/partial/denied 的 schema 而虚构完成。实际存储适配器必须能重试同一请求并查询进度。

## 5. 尚未被本表证明的事项

人工符号推演证明在已声明端口保证下各步骤的设计意图与提交点，不证明真实并发、密码学、
磁盘崩溃、OS 启动、资源解析或网络投递已实现。每行的结构见证也不是独立业务运行。
交付者声明符合性时必须分别填写设计证据、假实现证据和真实适配器证据，不能选一个总勾选。
