# 全流程符合性审计台账

范围：`g2a-design-1` 的协议设计、伪代码装配及逻辑推演。不是旧 SDK 的运行验证，不是独立厂商认证，不是公网部署或密码学实现审计。

本轮已完成本阶段审计：设计定义、伪代码装配、42 条本地模型检查和 10 组补充符号推演共同构成证据，详见 [验证记录](WALKTHROUGH_RESULTS.md)。完成级别为**协议工作草案与假实现流程**，不是生产运行或稳定发布；不以编号齐全代替语义验证。

本文保留初次设计审计追溯；随后字段/操作契约、统一验证、全操作与端口失败审查的
最终结论见 [FINAL_AUDIT](FINAL_AUDIT.md)，不能仅用本文的初始 42 条结果代替后续审计。

## 1. 原目标的验收解释

用户要求完成整个协议设计并具体实现，允许假代码，当前以跑通全流程为主。因此必须交付：

1. 不依赖 Mot 的明确协议核心与可选能力，不把现有演示限制写成通用要求。
2. 本地/云端两端组合，以及游戏发起/伙伴发起两条入口的完整授权到退出流程。
3. 身份、消息、权限、受众、形象呈现、动作生命周期、来源记忆、多会话与异常恢复的明确规则。
4. 有输入/状态/输出/错误的伪代码模块和它们的装配，不留只有函数名却没有责任契约的核心黑箱。
5. 成功和关键失败路径的推演记录，验证规则互相一致；必要时修正方案。
6. 与已有实验规范的区别、兼容/治理/发布边界，以及下一阶段真实实现需要履行的端口契约。

不把“代码可编译”“真实云厂商接入”“窗口截图”“GitHub CI 绿色”“发布网站/包”加作本阶段门槛；也不能因此删掉这些场景的协议设计。已有实现/测试仍保留，但不拿来证明新草案已实际运行。

## 2. 设计领域追溯

以下给出覆盖位置；对应结论见 §7，具体模型断言和人工推演见验证记录，不能仅按文件存在判断通过。

| 设计项 | 规则位置 | 伪代码或流程入口 | 本轮核对要点 |
| --- | --- | --- | --- |
| D01 核心与能力 | PROTOCOL §1、§3 | negotiate；无桌面/无动作组合 | 最小能力拒绝/接受与 required_features 矩阵 |
| D02 身份信任 | PROTOCOL §2、§4、§14 | authenticate、discover、Provider.complete；绑定入口 | 同名不同 issuer、错误受众、旧 epoch 不互换 |
| D03 发现授权 | PROTOCOL §7 | create_offer、decide、attempt_automatic、redeem、join | 两个入口与自动规则、单次启动、stale 路径 |
| D04 消息版本 | PROTOCOL §3–4、§15 | receive_http、control_mutation、submit | 业务/传输 ID 区分、未知扩展、编码/限额 |
| D05 会话恢复 | PROTOCOL §8 | heartbeat、close、resume、maintenance_tick | 闭会不复活、代次变更、结果保留、账本丢失 |
| D06 动作 | PROTOCOL §9 | accept_action、claim_action、world_step、commit_result | 请求/效果时点、部分效果、迟到事实、重试去重 |
| D07 情境受众 | PROTOCOL §10 | publish_context、accept_chat、membership_replace、read_events | 成员代次、空页/满页、私聊路由者可见性 |
| D08 偏好记忆 | PROTOCOL §10 | resolve_user_policy 契约、memory_ingest、prepare_disclosure、privacy_request | 偏好不能越权、跨游戏来源、部分删除回执 |
| D09 形象资源 | PROTOCOL §11 | select_avatar、prepare_resources、acquire/release | 强制形象不降级、资源闭包、无桌面、释放 tombstone |
| D10 并发设备 | PROTOCOL §12 | AgentController slot、begin_handoff、advance_transfer、resume rebind | 多授权域边界、单代写权、失败不恢复旧凭据 |
| D11 传输拓扑 | PROTOCOL §15 | 全部 BINDINGS_AND_RELAY；END_TO_END 位置组合 | 内外层凭据、只出站游戏的控制 lane、重启不重投 |
| D12 安全隐私 | PROTOCOL §2、§14 | 身份/输入/资源端口及逐操作权限 | 验证责任、不能保障的恶意端点行为明确 |
| D13 错误时序 | PROTOCOL §13 | reply_error、maintenance_tick、query_action、Relay timeout | not_accepted/unknown 区分，控制容量，回收不扩权 |
| D14 一致性验证 | 本文；END_TO_END；WALKTHROUGH_RESULTS | 主路径、T01–T25、补充检查和 M01–M10 | 已分别记录模型实际断言与未执行端口的推演结论 |
| D15 演进发布 | PROTOCOL §16 | 精确版本、旧绑定隔离、角色/能力声明 | 草案选择不伪装为旧 SDK 支持或稳定承诺 |
| D16 权利命名 | PROTOCOL §16 | 原许可保留、独立权利清单和发布门禁 | 权利人决定/名称调查是发布事项，本轮不冒充已完成 |

## 3. 原 R01–R17 的设计层对应

原台账含真实产品验收项目；本目标采用假实现，故这里明确区分其“协议设计责任”和“后续实物交付”。不能将后者标为通过。

| 原项 | 本阶段必须覆盖 | 后续真实实现/发布另验 |
| --- | --- | --- |
| R01 | 无 Mot/中心依赖、端口可替换与独立角色 | 独立检出安装和厂商互通 |
| R02 | PROTOCOL 类型/操作、错误、字段语义与模块一致 | 新版权威机器 schema、实际序列化兼容 |
| R03 | 批准/拒绝/加入/关闭/超时/恢复完整状态 | 网络故障和进程故障实测 |
| R04 | 主动情境/聊天/行动无先行问题依赖 | 实际两端主动消息互通 |
| R05 | 权限交集、动态撤权、效果临界区 | 游戏执行器确实提供排序/隔离 |
| R06 | 偏好优先级与权限不混同 | 真实 Agent 内容策略遵从评估 |
| R07 | Principal 连续性、来源与披露、跨游戏装配 | 持久身份和记忆存储/迁移验证 |
| R08 | 明确受众、成员代次、私聊非 E2EE | 多人网络投递隔离验证 |
| R09 | 优先级、资源兼容/完整性/拒绝 | 多引擎格式解析及安全沙箱 |
| R10 | baseline/占用、用户意图、退出/崩溃恢复 | 实际桌面/设备效果验证 |
| R11 | 两个入口、发现/同意/启动分离 | OS 注册唤起和身份验证适配器 |
| R12 | 四种位置组合、直连/出站 Relay | 公网、NAT、TLS 和提供者部署 |
| R13 | 威胁/权限/重放/未知结果/有界资源设计 | 真实攻击面测试与生产运维 |
| R14 | 不依赖指定语言的模型、模块及角色契约 | 第三方独立实现与引擎 SDK |
| R15 | 精确版本与一致性向量/旧绑定边界 | 发布 SDK、安装和兼容测试工具 |
| R16 | 提案状态/治理/弃用/公开版本规则 | 网站、下载、公开安全渠道 |
| R17 | 保留权利来源、不擅自换证、发布门禁 | 权利人最终许可决定、名称/商标调查 |

## 4. S01–S14 场景与 I01–I10 不变量

| 场景 | 追溯的具体轨迹/算法 |
| --- | --- |
| S01 本地伙伴发起 | 主路径的伙伴入口替换；T01/T02 |
| S02 游戏唤起伙伴 | 主路径 t0–t5；T03/T04/T05 |
| S03 云端伙伴 | 位置组合矩阵、Provider 事务、无 presentation 协商 |
| S04 仅出站游戏 | Relay 注册/控制 lane/伙伴 lane；下列 T19–T23 |
| S05 最小伙伴 | PROTOCOL 核心能力；无 action 分支和 absent 呈现 |
| S06 动态撤权 | T06/T07；WorldGate 串行化和 fence |
| S07 回包丢失 | T08/T09；原 ticket 事实查询和迟到结果 |
| S08 重启旧请求 | T16；逻辑 epoch/transport_epoch/generation 区分 |
| S09 cursor 过期 | T10；有限扫描与高水位快照 |
| S10 私聊队聊与退队 | T11；当前身份+冻结成员代次，来源披露检查 |
| S11 多会话/设备 | T12/T13/T14；slot 和 handoff/rebind |
| S12 形象/资源失败 | T15；优先级与资源闭包 |
| S13 版本/扩展 | T17；协商前拒绝与严格标准字段 |
| S14 限额/慢消费者 | T18；维护回收、控制容量、未知结果 |

| 不变量 | 检查点和必须拒绝的反例 |
| --- | --- |
| I01 身份前置 | receive_http/decide/join/claim；Agent 自批或错误 audience 拒绝 |
| I02 权限交集 | negotiate/accept_action/world_step；新增能力不会扩大旧 Grant |
| I03 范围绑定 | decide/redeem/join；同意后改条款 stale |
| I04 去重冲突 | control_mutation/submit/Relay receipts；同 ID 改内容拒绝 |
| I05 收据不是结果 | claim/effect/commit/query；超时不发新 action ID |
| I06 冻结受众 | freeze_audience/read_events；退出再加入的同名主体不能领取旧消息 |
| I07 旧代无权 | authorized_control/resume/handoff；旧邀请不取新 secret；结果句柄不写 |
| I08 呈现不覆盖 | occupations/manual_revision/release tombstone；迟到 acquire 和乱序 release 不覆盖新意图 |
| I09 数据非指令 | 显式审批端口/资源解析；聊天“允许”不变 consent，资源不运行脚本 |
| I10 接收原子性 | receipt+record+event 同事务；世界效果另用 WorldGate 或 unknown |

## 5. 组合复核已经发现并修正的问题

这些修订来自对实际伪代码顺序的检查，不是性能/安全测试结论。

| 编号 | 反例 | 本轮修订与复核依据 |
| --- | --- | --- |
| A01 | 先扫描超过一页的可见事件，再截取 page_size，却返回扫描末尾 cursor，导致漏消息 | read_events 在本页可见条数到限时立即停止，cursor 只推进到最后已检查事件 |
| A02 | Principal 退队再加入后，单纯冻结 Principal 会恢复旧投递资格 | freeze_audience 额外冻结成员代次，重加代次递增 |
| A03 | 到期检查先闭会，再 require 抛错，普通事务回滚把闭会撤销 | 引入提交并退出的 commit_and_return，维护在接受新请求前执行 |
| A04 | resume 回包丢失后再次调用，expected_generation 旧值导致无法领取已成功的新凭据 | 控制操作回执先匹配同请求；仍需 fresh 身份、本人范围及当前代次检查 |
| A05 | 单宿主锁被误当作跨所有游戏的单会话保证 | 增加伙伴所属域 AgentController slot，明确无全局中心保证 |
| A06 | 隐私删除请求被默认发到游戏，就像游戏能删除所有提供者数据 | 路由到实际数据控制者，凭据受众独立；Relay 不任意转发跨 origin |

## 6. Relay 与控制重试补充轨迹

已与 T01–T18 一起完成本地模型检查，语义覆盖边界见 WALKTHROUGH_RESULTS §3–4。

| 轨迹 | 前置状态/输入 | 预期状态与不变量 |
| --- | --- | --- |
| T19 跨 lane 越权 | Agent 外层凭据发送 offer.decide 或 action.claim | 在 Relay 目录检查拒绝，游戏仍二次验证；不产生 Grant/ticket |
| T20 claimed 超时 | mailbox 已把 action.request 交游戏，回包丢失 | outer outcome=unknown；原 a1 查询，世界效果不因新 RelayCall 自动重做 |
| T21 重复 pull | 游戏第一次 pull ACK 丢失，使用同 pull_nonce 重试 | 同一 claim_id；语义重复依赖原 request_id 去重，不分配第二执行权 |
| T22 mailbox 撤销 | 一项 queued、一项 claimed | 前者 not_dispatched、后者 unknown；外层 token 作废，旧会话按关闭/租约收敛 |
| T23 审批回包丢失 | decide 已提交 Grant，Relay reply 丢失 | 相同控制 request_id 返回同 Grant 状态，不再批准第二 Grant |
| T24 resume 响应丢失 | g1→g2 提交且回包丢失 | 原请求领取原 g2；新 request_id 带旧 expected_generation 拒绝；之后 g3 时不泄露新密钥 |
| T25 迟到呈现获取 | admission acquire 尚在传输，先收到 release(S1,g1) | tombstone 拒绝迟到 acquire，其他会话占用不受影响 |

## 7. 完成审计结论

| 要求组 | 本轮证据 | 结论 |
| --- | --- | --- |
| D01–D04 / R01–R04：核心、身份、加入与主动交互 | 8 条 MAIN、T01–T05/T17、授权/最小云端补充检查；M01/M04/M09/M10 | 在明确端口契约下完成设计与假实现级贯通；标准格式/新旧版本未混用 |
| D05–D06 / R03/R05/R13：会话、动作、恢复 | T06–T09/T14/T16/T24、到期和 transport_epoch 补充检查；M02/M03/M07 | 状态、撤权、未知结果及保留边界自洽；不宣称跨崩溃恰好一次 |
| D07–D08 / R06–R08：受众、偏好、来源 | T10/T11、分页/来源隐私补充检查；M06/M09 | 可见性和来源不扩权，偏好不修改动作权限；生成文本内部遵从另验 |
| D09–D10 / R09–R11：资源、呈现、并发 | T12–T15/T25、单会话/资源补充检查；M01/M02/M05 | 资源准备、占用、用户意图、转移和失败收敛已贯通 |
| D11–D13 / R12–R13：传输、安全、限制 | T18–T23、Provider mismatch 检查；M04/M07/M08 | 外层 Relay 与内层权限不混同，控制幂等/期限/错误路径明确 |
| D14 / R14–R15：独立实现与验证设计 | 语言无关伪代码、可替换端口、FlowModel、42 条实际检查及 M01–M10 | 完成本阶段符合性证据，不冒充第三方独立 SDK 验收 |
| D15–D16 / R16–R17：演进与发布边界 | PROTOCOL §16、M10、原许可不变及发布门禁 | 规则设计完成；实际法律决定、公开网站/包发布明确未执行 |

用户目标所需的整体设计与假代码流程现已交付；这不把后续生产适配器、真实部署或稳定发布标记为已完成。全部 S01–S14 和 I01–I10 有上表及 §4 对应证据。修订记录包括 A01–A06，以及验证时发现并修正的 transport_epoch 漏检、世界拒绝后部分效果汇总、结果句柄回包丢失后的原主体只读恢复。

本轮未运行旧 SDK/Godot/Tk 全套测试，因为未修改它们且其通过不能证明新设计；未使用 GitHub Actions、未部署、未修改许可或账户、未提交推送。后续若进入真实实现，应逐端口兑现契约并生成新证据，不沿用本次假实现结果冒充实测。
