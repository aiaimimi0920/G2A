# 统一装配范围与剩余操作

本表不是新的符合性声明，也不覆盖旧 SDK。所有 38 项已有字段契约、结构正反例和
[逐操作符号轨迹](STATE_TRACES.md)；现在 **38 项**接入 [RelayHarness](relay_harness.py) 的组合字节入口。
其中 5 项由独立 Relay authority 处理，另外 33 项仍由 [PrivacyHarness](privacy_harness.py)
组合 [LaunchHarness](launch_harness.py)、[AssetHarness](asset_harness.py)、[PresentationHarness](presentation_harness.py)、
[ControlHarness](control_harness.py)、[AdmissionHarness](admission_harness.py) 与 [SessionHarness](session_harness.py) 处理。
这不是一个共享事务，也不把管理/本地/隐私操作开放给 Relay。`unified` 仅表示固定身份/单会话
夹具下的局部装配，不代表该操作所有配置、角色和异常路径已完整实现。

[test_design_conformance.py](../../tests/test_design_conformance.py) 检查本表与目录恰好一一
对应，并核对 unified 集合等于代码声明；这个静态检查不能证明表中的语义描述正确。
跨语言客户端实际调用 38 项，见 [回执汇总验证](OPERATION_STATUS_PROOF.md)；此前 36 项见 [设备生命周期验证](DEVICE_LIFECYCLE_PROOF.md)。此前 35 项证据在 [Relay 验证](RELAY_PROOF.md)。此前 30 项证据在 [玩家转发验证](PLAYER_FORWARD_PROOF.md)，29 项证据在 [隐私通道验证](PRIVACY_PROOF.md)，27 项证据在 [本地启动验证](LAUNCH_PROOF.md)；26 项/25 项/23 项/20 项/13 项证据分别保留在 [资源准备验证](ASSET_PROOF.md)、[呈现设备验证](PRESENTATION_PROOF.md)、[恢复与转移验证](CONTROL_PROOF.md)、[准入验证](ADMISSION_PROOF.md) 与 [统一会话验证](UNIFIED_SESSION_PROOF.md)。

## 1. 全操作证据与缺口

| 操作 | 统一入口 | 当前证据或具体缺口 |
| --- | --- | --- |
| describe | unified | 固定登记玩家/伙伴与实例校验；不是公开发现或真实 endpoint 身份验证 |
| offer.create | unified | 两个入口、Scope 协商冻结；仅 test-enrolled，volatile 或假 durable 端口，core/actions/team/resume/handoff/presentation/avatar/assets；team 受众须固定可信登记，资源仅 fixture manifest，不支持 preinstalled/自动规则 |
| offer.get | unified | 绑定主体读取当前状态，不续期、不含秘密；无长期清理/tombstone |
| offer.decide | unified | 预置交互假证据到 Grant/收据/独立启动许可原子提交；许可精确绑定本地注册应用/设备/范围，不由 remember 推断；自动规则仍不支持 |
| invitation.redeem | unified | JoinIntent 摘要与主体绑定、一次领取、设备观察与当前 revision 验证；本地启动 profile 还需当前进程及 fresh 同设备主体；失效不重放秘密 |
| session.join | unified | 邀请原子消费、设备绑定、资源闭包/独立 Renderer 准备、呈现 ACK 后 ready/outbox；仅声明式 fixture 资源 |
| session.heartbeat | unified | 当前写凭据、幂等租约；有效存活提交同事务签发呈现 revision 意图，设备仅经独立 renew 后更新，未确认期限到期仍保守闭会 |
| session.snapshot | unified | 同切点业务快照与当前权限；要求当前写凭据，关闭后结果另走 query |
| session.events | unified | 页窗口/nonce/当前过滤/历史缺口；没有网络发送与撤销的跨进程原子保证 |
| session.close | unified | 停写、保事实、closed 事件与补偿义务同事务；独立 release 及本地到期收敛，不声称跨设备原子恢复 |
| session.resume | unified | fresh 原主体/同设备、假账本和窗口、一次升代；呈现 rebind 或无呈现资源再校验，不沿用已失效 parser 收据；无真实磁盘 |
| session.handoff | unified | 玩家精确批准+目标证明、先撤旧代；资源缓存与目标 Renderer 独立验证，旧呈现释放或本地到期后才获取目标，失败闭会 |
| session.claim_control | unified | 原 agent+已验证目标设备、pending/ready、当前代次与传输代次秘密回放；不重复升代 |
| operation.get | unified | 原 agent/player 的准入/控制/lease/撤权/确认及动作业务收据，保留原终态、分别报告动作结果并重验读权；呈现/资源/启动沿用原 owner；不扩管理/隐私/Relay 私有查询，无长期清理 |
| chat.send | unified | 来源/受众/拒重/续租；不证明自然语言正文未泄密，真实发送前披露控制未实现 |
| action.request | unified | 固定 find-key、参数/定义/确认、实际凭据、收据+outbox；仍仅一个动作槽 |
| action.cancel | unified | 原 actor、停止后续步骤、部分效果、保留收据槽；不撤销已发生世界效果 |
| action.query | unified | 原 agent 及准入签发的只读句柄，关闭后可查询；与 operation.get 共用原成员代次及撤权检查，离开/重入不恢复旧结果读权；未覆盖 player 的独立读权配置 |
| action.confirm | unified | 固定可信玩家决定与一次消费、原玩家安全收据查询；跨语言已实际调用并验证消费一次；不是实际批准 UI 端口 |
| context.publish | unified | 已开放类别、可信来源、业务状态+outbox；不为伙伴续租 |
| player_chat.forward | unified | 当前 GameAuthority 与玩家席位/Scope/成员代次分别核验，private/team、按玩家去重、来源/扩展/事件事务/隐私 cutoff；不续伙伴租约；无真实输入签名或远端席位认证 |
| capability.replace | unified | CAS、冻结定义摘要、移除/改义停止动作；新增定义不扩大旧 Scope |
| membership.replace | unified | 预置可信证明、CAS、离开重入升代；不认证远端游戏席位证明 |
| permission.revoke | unified | grant/session/result_read/invitation；已消费邀请如实报 consumed，不假装闭会；auto_rule/capability/relay 对象未装配 |
| action.claim | unified | 登记 executor、唯一 ticket、事务领取；不是真实作业调度器 |
| action.commit_result | unified | 原 ticket 的可信事实、业务值 schema、结果+outbox；停止后仍允许已知事实收敛 |
| launch.request | unified | 单一固定本地应用/设备、独立许可与派发标记、不可回滚假进程、幂等收据/未知查询、已知失败撤未用 Grant；启动不等于 ready，无真实 OS/进程认证 |
| asset.resolve | unified | 固定资源角色、规范字节精确绑定 Manifest/策略/解析兼容性、逐跳连接见证、实际字节摘要/大小、声明式解析、整闭包缓存与收据原子提交；无真实 HTTPS/ZIP/第三方格式 |
| presentation.acquire | unified | 精确 authority/设备/Scope/代次/期限证明、设备独立效果账本、ACK 丢失重试、tombstone；只支持固定内存设备 |
| presentation.renew | unified | 明确 local authority 入口、递增 revision/设备 epoch、旧证明隔离、不重渲染、不续游戏租约；独立设备重启 fresh 验证，有界补偿和停止收据耗尽后本地收敛；无真实设备 |
| presentation.release | unified | 先落本代 tombstone、只撤本代占用、按最新 baseline 重算；失败如实报告 applied/actual_visible，闭会不假装已恢复 |
| privacy.request | unified | 独立 data_subject/privacy 通道、控制者/来源逐条核权、cutoff/去重同事务、密封副本清单与独立假删除效果；共享/外部/保留副本返回例外，派发未知不重删；无真实存储 |
| privacy.receipt | unified | fresh 原主体读取同 provider operation，回执表与精确绑定验证；pending 不重派发、不续游戏租约，关闭/撤 Grant 后可查；无第三方删除认证 |
| relay.register | unified | 固定 instance/origin/operator/配对，nonce 与三类外层凭据同事务，各认证接收方独立取自己的凭据；无真实配对服务 |
| relay.call | unified | 外层/内层独立主体角色和 game audience，冻结内层 ID/请求/proof/deadline，有界队列、原回执和授权变化后的缓存阻断；仅固定可信游戏端口 |
| relay.pull | unified | nonce/claim 同事务，同主体 FIFO/主体间轮转，项数与编码字节双限，claimed 不重入队；无真实 worker 或长期公平性证明 |
| relay.reply | unified | 精确游戏/claim owner、原内层关联与 schema/大小，原响应幂等及 reply_conflict；独立派发/结果日志与坏回包 unknown；无实际网络 |
| relay.revoke | unified | 原 controller/CAS、止损预留、closed/revision/三类凭据撤销及 queued 未派发/claimed unknown 同事务；假重启保留事实，不回滚游戏或续 lease |

## 2. 后续收口顺序与停止条件

这些仍是设计/假实现工作，不能全部移交给“未来生产适配器”来宣称本阶段完成：

1. **外部效果与完整设备流程**：准入、呈现释放/获取/rebind、延迟 ACK 与补偿已有受限字节
   证据，八类核心事件都有生产路径。设备租约 revision、独立设备重启和有界补偿批次已补，
   见设备生命周期证明；原 agent/player 控制与动作回执已补，见回执汇总证明；长期账本
   回收已补 [关闭会话消息回执清理](RECEIPT_RETENTION_PROOF.md)，保留终态、结果及控制账本。
   活跃回收、全账本清理、多会话及跨 authority 配置仍需独立工作包，不把管理私有回执直接对外开放。
   补偿由显式可信 tick 驱动，不是运行中的后台服务；假设备不代替实际窗口/网络验证。
2. **外部效果边界**：其余 revoke 对象，沿用受信
   假端口而非接真实 OS/账户。停止条件是每个已声明提交点的前后故障与结果查询贯通，
   unknown/partial/pending 不被转换为虚假成功。
   assets 已补固定 manifest profile；preinstalled 选择、更多格式/沙箱和缓存长期回收仍须单独装配。
   launch 已补单应用假端口与 prejoin 重启/未知收敛；真实 Launcher、许可独立撤销接口、长期清理及运行中进程监视仍须另验。
   privacy 已补密封内存清单、原主体查询和 outbox cutoff；动态复制/备份、混合数据拆分、跨服务屏障及长期处理调度仍须另验。
3. **Relay 配置与生命周期**：五项在固定配对下的 queued/claimed/replied/expired/closed、
   双角色、原 ID、秘密交付、撤销和假重启已有字节证据，本工作包已收口。长期保留/回收、
   多参与者公平性、真实缓存撤销屏障与重新配对策略另行验证；不以原入口数代替这些配置。
4. **全配置对照**：最小 core 的两种准入入口、功能拒绝和准入回滚已补 Python 字节证明，
   JS/Python 另补 companion 最小链，见 [最小 core 配置](MINIMAL_CORE_PROOF.md)。其余组合
   与角色拒绝仍须分别验证；单动作/固定时钟与有限交错不代表穷尽所有实现。

真实认证、持久数据库、网络、引擎、第三方厂商互通和发布继续使用独立 adapter/deployment
门禁；不是为完成本表而自动获准建设或部署的内容。
