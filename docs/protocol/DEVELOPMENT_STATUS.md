# 协议开发交付台账

最新增量：[共享 Grant 与跨 authority fanout 组合](SHARED_GRANT_FANOUT_PROOF.md)。按可信 owner、
Grant/Scope/实例/玩家分组，一份冻结请求、组 unknown/ACK，明确整个 Grant 的影响范围；
同名独立 owner 不合并，非 Grant 撤销仍按会话独立。独立 owner 重启后经可信锚点重绑，
支持跳代恢复，旧端口和仅同 UUID 的伪后继拒绝；活动 Grant 不接受同 revision 伪 ACK。
新增 15 个模型与 1 个严格门禁方法，候选互通 48 次请求/108 次夹具命令；预期全套 861。
正式 38 项/503 次 wire 和已有共享 Grant 64/137 分开计数，不宣称全局原子撤销。

此前增量：[同一 Grant 的多会话授权域](SHARED_GRANT_PROOF.md)。唯一 canonical Grant owner
复用会话/动作/事件模型，补真实邀请与 session.join、pending 槽位、Grant 单次原子撤销、
独立 session/CAS/读权、世界效果保留和可信恢复。新增 31 个模型与 1 个严格门禁测试；
候选 JS/Python 64 次请求/137 次夹具命令，覆盖三个撤销故障窗口、未知查证和兄弟端口回执。
补满 outbox 嵌套事务引用及旧 ActionHarness 绕过 owner 的实际反例；最外层统一提交，
受控内部动作端口也检查生命周期并拒绝绕过 owner；成功 wire 提交保留原 world/owner 锁，
补取消/结果提交三种故障条件与重启重放。正式操作仍为 38 项/503 次 wire；
预期全套 845 个测试方法，最终结果以本轮回执为准。互通采用有界嵌套预算并保留超时证据。
固定预批准单 Grant 不等于多玩家/多 offer 准入，跨 Grant 与跨 authority 全局屏障仍待验。

此前增量：[动态撤权目录与同 authority 多会话](FANOUT_CATALOGUE_PROOF.md)。明确目录版本与冻结
选集；未决引用阻止退休，墓碑禁止旧身份复活，已确认历史操作不依赖退休端口。新增 15 个
模型测试，含两种退休提交故障、恢复、容量满时控制可用性和同 authority 独立会话读权。
候选 JS/Python 新增 10 次请求/56 次夹具命令，累计 28/119；新增严格动态链门禁。
目录退出不是远端撤权；多玩家、共享 Grant 广播、长期清理和全局屏障仍待验。

此前增量：[撤权协调器命名空间与可信恢复](CROSS_AUTHORITY_REVOKE_PROOF.md)。已复现并修复独立
协调器 request_id 冲突，补齐完整账本 checkpoint、旧/混合快照拒绝、原字节恢复与不健康拒绝。
同时修复[代次恢复摘要类型碰撞](EPOCH_RECOVERY_PROOF.md)，损坏 list 不再可伪装成 map/tuple/set。
新增 10 个 fanout、3 个 epoch 和 1 个门禁测试；focused 29/44/11 项通过。候选互通现为
18 次请求、63 次夹具命令，包含 8 次旧快照拒绝；正式操作仍为 38 项/503 次 wire。
独立可信内存锚点不等于真实数据库防回滚；动态目标和全局屏障仍未完成。

此前增量：[跨 authority 四类撤权候选互通](CROSS_AUTHORITY_REVOKE_PROOF.md)。JS 独立构造
目标键/request_id/请求字节，16 次候选请求验证修改 CAS 拒绝、部分提交、丢响应和假重启。
与正式 503 次 wire 分开计数；新增严格门禁测试，累计预期 783 个，不宣称公网协调 API。

此前增量：[跨 authority 逐目标能力撤销](CROSS_AUTHORITY_REVOKE_PROOF.md)。明确冻结每目标
已批准 action ID，不按全局名称自动映射；撤执行不撤读权、不关会话，定义更新不复活。
新增 5 个测试，累计预期 782 个；涵盖不同 action ID 的两个目标及未选第三 authority。

此前增量：[跨 authority Grant/结果读权撤销](CROSS_AUTHORITY_REVOKE_PROOF.md)。冻结对象类型并
加入 grant_id 绑定；Grant 关闭和结果读权禁止读取不混同，丢 ACK 恢复保留原请求。
新增 5 个测试，累计预期 777 个；未知对象拒绝，不扩为全局永久禁令或快照迁移。

此前增量：[跨 authority 目标换代竞态修复](CROSS_AUTHORITY_REVOKE_PROOF.md)。先复现绑定检查
与接收方受理之间可插入换代，再以接收方锁原子覆盖两者；补并发反例和故障后锁释放。
新增 2 个测试，累计预期 772 个；远端仍需接收端完整绑定核验，不宣称网络共享锁。

此前增量：[跨 authority 会话撤销组合](CROSS_AUTHORITY_REVOKE_PROOF.md)。两个真实 SessionHarness
按完整目标身份分派原 permission.revoke 字节；部分提交/丢 ACK/假重启不伪造全局成功，
已产生效果和两侧结果读权独立。新增 7 个测试，累计预期 770 个；仅固定 session 撤销组合。

此前增量：[Launcher 退役跨语言恢复](LAUNCHER_RETIREMENT_PROOF.md)。新增 22 次正式请求，
累计 503 次、38 项操作；独立封存/authority 确认故障、迟到启动拒绝及 GC 后旧回执贯通。
新增 1 个严格门禁测试，累计预期 763 个；没有新增公开维护操作或恢复旧端口权限。

此前增量：[独立 Launcher 退役与回收](LAUNCHER_RETIREMENT_PROOF.md)。新增 6 个测试方法，
累计预期 762 个；无未决、精确退出及闭会后建立独立不可逆屏障，再单独确认并有界清理。
旧 authority/running 快照不能复活端口，原历史回执保留；不提供新代或重新开放接口。

此前增量：[启动回执跨语言恢复](LAUNCH_RECEIPT_RETENTION.md)。新增 24 次正式 wire 请求，
总计 481 次、38 项操作；两种 GC 提交故障及 unknown 超期查证后回收均贯通。
严格子报告门禁新增 1 个测试，累计预期 756 个；不将维护夹具算作公开 API。

此前增量：[启动终态回执有界回收](LAUNCH_RECEIPT_RETENTION.md)。新增 7 个测试方法，累计预期
755 个；冻结最早回收时间，保留 pending、许可消费屏障及独立进程事实，回执缺失不重启动。
不是许可/效果/墓碑全账本回收，不解除现有容量上限。

此前增量：[最大长度启动许可的进程引用修复](LAUNCH_PROCESS_MONITOR_PROOF.md)。先复现合法
128 字符许可可启动/加入却无法记录退出，再改为完整引用摘要生成有界内部进程 ID。
新增 2 个边界测试，累计预期 748 个；不截断身份、不修改已有绑定，不新增 wire 字段。

此前增量：[精确进程监视互通](LAUNCH_PROCESS_MONITOR_PROOF.md)。新增 20 次正式 wire 请求，
累计 457 次、仍为 38 项操作；两种提交故障经假重启收敛，旧秘密不重放、历史效果不抹除、
不重复启动。新增严格互通门禁测试，累计预期 746 个方法；不证明真实 OS 观察或持久化。
主契约、控制面/资源伪代码与覆盖表已同步此前撤销、预装、回收和身份期限规则。

此前增量：[公共 enrolled 身份期限审计](ENROLLMENT_EXPIRY_AUDIT.md)。先复现过期玩家仍可启动，
再在准入/启动共同身份入口补期限检查。新增 5 个方法，累计预期 745 个；旧回执不能
绕过当前认证，独立邀请能力不被另一个身份到期隐式撤销。

此前增量：[精确进程退出监视模型](LAUNCH_PROCESS_MONITOR_PROOF.md)。新增 8 个测试方法，累计 740 个；
准入冻结精确进程，确定退出才关闭关联会话，unknown 不猜测；历史启动回执/效果不变，
新进程不能完成旧准入，退出墓碑阻止旧 running 快照复活。不启动真实进程或自动重启。

此前增量：[启动许可独立撤销](LAUNCH_PERMISSION_REVOCATION.md)。permission.revoke 新增
launch_permission 对象，不增加操作数量；新增 7 个场景和 1 个互通门禁测试，累计预期 732 个。
JS/Python 新增 16 次正式请求，总 wire 为 437；未知/既有效果和独立 Grant 不被撤销抹除。

此前增量：[资源回执固定期限与回收](ASSET_RECEIPT_RETENTION_PROOF.md)。新增 6 个测试方法，累计 724 个；
成功/已受理失败回执按冻结期限失效，关闭后有界回收；不续期、不重执行、不删除共享内容。
包含边界时间、故障重启与独立有效身份前提，公开回执结构不变。

此前增量：[关闭会话缓存回收](ASSET_CACHE_RETENTION_PROOF.md)。新增 6 个测试方法，累计 718 个；
会话关闭与独立呈现释放证据同时满足才允许有界清理，保留原回执及预装身份目录。
含 release/ACK 间隙、部分 GC、提交故障、假重启与不健康账本拒绝；不删除真实文件。

此前增量：[预装形象跨语言互通](PREINSTALLED_AVATAR_PROOF.md)。JS/Python 新增 11 次正式请求，
总 wire 为 421 次；覆盖库存拒绝、独立呈现提交丢响应和重启后的无秘密回执。
新增门禁测试，累计预期 712 个方法；真实安装/格式/设备并发和目录回收仍待验。

此前增量：[预装形象精确绑定与准入](PREINSTALLED_AVATAR_PROOF.md)。新增 8 个测试方法，累计 711 个；
已接入不依赖 assets 的准入、独立设备库存、精确内容绑定、呈现及 resume/handoff 门禁。
无真实安装/加载；目录回收与新配置跨语言互通仍待验。

此前增量：[内层 proof 与底层身份期限修复](RELAY_IDENTITY_EXPIRY_FIX.md)。先复现到期 reader
被查证接受的缺口，再在公共 verify 层修复。新增 4 个测试方法，累计预期 703 个；
保留期场景改用可信新 reader，不以过期凭据作为成功前提。

此前增量：[查证恢复跨语言组合](RELAY_SETTLEMENT_INTEROP.md)。四类恢复实际新增 26 次正式字节请求，
总 wire 为 410 次；新增严格互通门禁测试，累计预期 699 个测试方法。含丢回复、GC、
查证前后故障、假重启和两侧代次切换，不新增公开维护操作。

此前增量：[会话控制提交查证](RELAY_SESSION_CONTROL_SETTLEMENT.md)。新增 4 个测试方法，累计 698 个；
heartbeat/close 与会话侧 session/result_read/capability 撤权已接入原主体/摘要查证，
覆盖丢回复、GC、重启及轮换，不续租、不重复关闭或增加撤权 revision。

此前增量：[action 查证授权与通道边界](RELAY_ACTION_SETTLEMENT.md)。新增 4 个测试方法，累计 694 个；
read_until 精确边界、成员退出/新代次重入拒绝、pending_sync 不发布，以及 worker 管理操作
被 Relay 路由拒绝已验证。worker 通道不是待开放的 Relay 扩展；合法控制操作查证仍待补。

此前增量：[action 受理事实查证](RELAY_ACTION_SETTLEMENT.md)。新增 4 个测试方法，累计 690 个；
Envelope.id 与传输 ID 分离、独立同主体 reader、当前读权/保留期复用、request/cancel
无重执行及故障恢复已装配；worker 效果未知及其他控制账本仍待验。

此前增量：[准入查证组合与 pending join 边界](RELAY_ADMISSION_SETTLEMENT.md)。新增 3 个测试方法，累计 686 个；
已补 offer.decide、invitation.redeem、session.join 的丢回复/GC/重启/查证/轮换链，
并验证查证不提前发布 ready、不泄露凭据，时钟倒退和 proof 到期保留未知阻断。

此前增量：[准入提交事实查证](RELAY_ADMISSION_SETTLEMENT.md)。新增 3 个测试方法，累计 683 个；
已用 offer.create 覆盖真实模型提交后丢回复、独立账本精确匹配、授权撤销拒绝及轮换恢复。
此检查点其他准入操作组合尚待验，已在后续补齐上述固定场景；其他业务账本及跨进程查询仍待验，不把 committed 当作异步业务完成。

此前增量：[未调用派发的可信收敛](RELAY_UNSTARTED_SETTLEMENT.md)。新增 3 个测试方法，累计 680 个；
端口未调用见证、关闭屏障、GC/重启及提交故障重试已组合；可能已进入游戏的未知仍阻断轮换。

此前增量：[现有 Relay 动态轮换与有界旧回执](RELAY_ROTATION_PROOF.md)。新增 7 个方法，累计 677 个；
三独立提交点、未知派发阻断、新同意登记、旧回执期限/容量与 GC 已组合。JS/Python 新增 13 次正式请求，
总 wire 为 384 次；真实持久化、防旧快照回滚、未知查证收敛与多人公平性仍待验。

此前增量：[现有 Relay 固定代次 profile 接入](RELAY_EPOCH_PROFILE_PROOF.md)。新增 9 个方法，累计 670 个；
既有五操作与通用撤销使用冻结 required 扩展、代次 mailbox ID、配对索引及游戏端口拒绝规则。
该检查点 JS/Python 正式操作 wire 为 371 次；后续动态轮换装配见最新增量，不等于独立归档模型全部能力已迁移。

此前增量：[跨代次执行回执归档](EPOCH_RECEIPT_PROOF.md)。新增 8 个方法，累计预期 661 个；
执行栅栏与回执分离、独立原主体读权、固定保留期、到期清理及恢复已装配到候选模型。
候选互通增至 26 次字节请求/51 次夹具命令；不等于全操作归档或正式 Relay 接入。

此前增量：[候选代次 profile 字节互通](EPOCH_INTEROP_PROOF.md)。新增 3 个门禁测试，累计预期 653 个；
独立 JS 端完成 21 次候选字节请求与 43 次夹具命令，验证绑定拒绝、凭据恢复和切换故障。
与原 38 操作分开统计；真实网络、旧回执归档和现有 RelayHarness 接入仍待完成。

此前增量：[代次凭据与 owner 恢复](EPOCH_BINDING_RECOVERY.md)。新增 7 个方法，累计预期 650 个；
独立凭据 checkpoint、关联模型时点、原 token/owner 保留及旧快照拒绝已在参考模型验证。
不是持久数据库或现有 Relay wire 接入；最终结果以本轮回执为准。

此前增量：[代次身份绑定候选合同](EPOCH_BINDING_CONTRACT.md)。新增 11 个方法，累计预期 643 个；
严格字节绑定与可信证据比对接入代次参考模型，覆盖主体/角色/邮箱隔离与新旧代次拒绝。
尚未接入现有 Relay wire，登记表持久恢复及新 profile 的跨语言互通待验。

此前增量：[代次恢复校验](EPOCH_RECOVERY_PROOF.md)。新增 7 个方法，累计预期 632 个；
独立可信 checkpoint 对照旧/混合/篡改快照，同 epoch 派发标记回滚亦拒绝。
仍是内存参考模型，真实持久锚点与 Relay wire 接入待验，最终结果以本轮回执为准。

此前增量：[长期身份代次参考模型](EPOCH_ROTATION_PROOF.md)。新增 8 个方法，累计预期 625 个；
封存、游戏切换、Relay 切换的独立提交与故障恢复，及有界身份回收已在独立模型中验证。
尚未接入 RelayHarness/wire；不放宽现有 8 邮箱限制，结果以本轮回执为准。

此前增量：[端口生命周期复核](PORT_LIFECYCLE_AUDIT.md)。新增 4 个方法，累计预期 617 个；
修复退役/不健康端口仍提供身份验证和结果披露依据的路径，统一拒绝规则并严格验证恢复参数。
不新增 wire 操作，不宣称真实持久数据库或认证实现完成；最终结果以本轮回执为准。

此前增量：[关闭游戏 journal 槽位回收](GAME_JOURNAL_GC_PROOF.md)。新增 7 个方法，累计预期 613 个；
独立屏障保护下的有界回收、活动记录保留、容量释放、故障与假重启已装配。
不删除 mailbox 身份屏障、不支持无限重配对；最终结果以验证回执为准。

此前增量：[独立游戏 journal 清理](GAME_JOURNAL_RETENTION_PROOF.md)。新增 8 个方法，累计预期 606 个；
关闭 owner 见证、独立提交屏障、迟到 claim 拒绝、载荷清理、并发效果保留和假重启已装配。
仍保留身份与摘要槽位，不代表无限账本回收；最终验证以本轮回执为准。

此前增量：[Relay 关闭载荷清理](RELAY_RETENTION_PROOF.md)。新增 8 个方法，累计预期 598 个；
保留墓碑与撤销记录、原子清除请求及 pull 副本、有界批次、重启与新旧配对隔离已装配。
不回收 mailbox 身份槽位，不清理独立游戏 journal，不宣称无限长期运行；最终结果以回执为准。

此前增量：[通用 Relay 撤销](RELAY_REVOCATION_PROOF.md)。新增 8 个方法，累计预期 590 个；
独立 owner 分派、双入口单次关闭、权限隔离、原回执恢复及止损容量已装配。
新增 [场景验收清单](SCENARIO_ACCEPTANCE.md)，明确模型证据、设计缺口和独立生产门禁。
最终通过情况以本轮验证回执为准，尚不能宣布整个协议完成或冻结。

此前增量：[原请求客户端恢复](REQUEST_RECOVERY_PROOF.md)。新增 21 个方法，累计预期 582 个；
参考 HTTP、Problem Details、JSON-RPC 和 MCP，补动作/取消/关闭的保守接受知识、
原字节重试、有界查证和关联校验。不是 SDK 自动重试器，最终通过情况以回执为准。

此前增量：[自动批准规则](AUTO_RULE_PROOF.md)。新增 24 个方法，累计预期 561 个；
显式规则期限/时长、严格匹配、新 Grant、玩家撤销、已有授权保留、启动隔离和故障恢复
已装配；JS/Python 增加 22 次 wire，含 capability 撤销补证。最终通过情况以回执为准。

此前增量：[固定会话能力撤销](CAPABILITY_REVOKE_PROOF.md)。新增 10 个方法，累计预期 537 个；
capability 撤销的 CAS、单向权限屏障、停止执行、保留效果/读权及原玩家回执已装配。
最终通过情况以回执为准，不覆盖多会话传播、auto_rule 或通用 Relay 撤销路由。

此前增量：[关闭会话回执清理](RECEIPT_RETENTION_PROOF.md)。新增 10 个方法，累计预期 527 个；
过期消息回执有界清理、双索引事务、结果保留期和终态屏障已装配，JS/Python 补清理后
旧/新 ID 拒绝与假账本重启。最终通过情况以回执为准，未完成全账本或活跃会话回收。

此前增量：[最小 core 配置](MINIMAL_CORE_PROOF.md)。新增 7 个方法，累计预期 517 个；
无虚构 action 的两种准入入口、聊天/事件/关闭、功能拒绝和准入回滚已装配，JS/Python
补最小 core 实际链。最终通过情况以本包回执为准，未扩展全部功能组合。

此前增量：[动作结果读权边界](RESULT_READ_BOUNDARY_PROOF.md)。新增 5 个方法，累计预期 510 个；
修复成员离开/重入后 action.query 仍返回旧结果、但 operation.get 拒绝的入口不一致。
正常关闭后读取与成员变更事务回滚保持；最终通过情况以本包回执为准。

此前增量：[原请求回执汇总](OPERATION_STATUS_PROOF.md)。新增 29 个方法，累计 505 个设计方法、
42 条原模型轨迹；JS/Python 实际调用 38 个操作、312 次 wire。组合入口仍为 38/38。
原完成事实与当前会话/动作状态分开；控制/业务 ID、独立结果读权、跨层 revoke 唯一性与
假重启贯通。全部操作被有限夹具调用不代表全部配置通过，不扩管理/隐私/Relay 查询权限。

此前增量：[呈现设备生命周期](DEVICE_LIFECYCLE_PROOF.md)。新增 41 个方法，累计 476 个设计方法、
42 条原模型轨迹；JS/Python 实际调用 36 个操作、287 次 wire。组合入口 38/38。
显式 renew、revision/epoch、独立设备重启、有界补偿和满停止回执后的本地恢复已贯通；
原 ACK 与 fresh 证据分开，关闭或替代意图不把未知效果伪报为失败。无真实设备或后台服务。

此前增量：[Relay 配对、队列与未知结果](RELAY_PROOF.md)。新增 52 个方法，累计 435 个设计方法、
42 条原模型轨迹；JS/Python 实际调用 35 个操作、268 次 wire。组合入口 37/37，Relay 与
游戏保持独立 authority/事务；原 ID、双角色、claim/reply、撤销分类和假账本恢复已贯通。
批次字节限额与撤销预留都有修复前反例；未扩展真实服务或把所有操作开放给 Relay。

此前增量：[玩家消息转发](PLAYER_FORWARD_PROOF.md)。新增 33 个方法，累计 383 个设计方法、
42 条原模型轨迹；JS/Python 实际调用 30 个操作、190 次 wire。组合入口 32/37；
当前可信席位、私聊/队伍受众、按玩家去重、事件事务、隐私 cutoff 与假账本恢复已装配。
游戏转发不续伙伴租约；固定输入映射不代表真实玩家认证或正文作者证明。

此前增量：[隐私请求与可信回执](PRIVACY_PROOF.md)。新增 38 个方法，累计 350 个设计方法、
42 条原模型轨迹；JS/Python 实际调用 29 个操作、158 次 wire。组合入口 31/37；
独立主体权、cutoff/去重、固定副本处理、例外、派发未知和原结果查询贯通。
同时修复首次启动 join 的 device_id=None 未被绑定，未触及真实存储或 OS。

此前增量：[本地启动与未知结果](LAUNCH_PROOF.md)。新增 29 个方法，累计 312 个设计方法、
42 条原模型轨迹；JS/Python 夹具实际调用 27 个操作、125 次 wire。组合入口 29/37；
单独启动许可、不可回滚假进程、未知查询、准备期进程核验和 prejoin 重启已装配。
不执行真实程序；启动事实不等于已加入或 ready。

此前增量：[资源准备与缓存](ASSET_PROOF.md)。新增 30 个方法，累计 283 个设计方法、
42 条原模型轨迹；JS/Python 夹具实际调用 26 个操作。组合入口为 28/37；资源闭包字节、
可信传输见证、声明式解析、原子缓存及资源到 ready 已装配；恢复收尾修复资源元数据
布尔/整数相等性绕过，使用规范字节绑定。无真实下载/第三方格式。

此前增量：[呈现设备与补偿](PRESENTATION_PROOF.md)。新增 25 个方法，累计 253 个设计方法、
42 条原模型轨迹；JS/Python 夹具实际调用 25 个操作。组合入口为 27/37；设备独立效果、
准入 ACK、rebind/handoff 的释放与获取、失败补偿已装配；资源和设备租约更新仍未完成。

此前增量：[控制权恢复与转移](CONTROL_PROOF.md)。新增 20 个方法，累计 228 个设计方法、
42 条原模型轨迹；JS/Python 夹具实际调用 23 个操作。组合入口为 25/37；新增 control_changed
生产链、假账本重启、跨 transport 效果隔离及恢复清单读权过滤，真实持久化/呈现仍未验证。

此前增量：[准入到就绪字节链](ADMISSION_PROOF.md)。新增 20 个方法，累计 208 个设计方法、
42 条原模型轨迹；JS/Python 夹具涉及 20 个操作。两入口的批准/邀请/加入/ready 与既有数据
面接通，组合入口为 22/37，余下 15 项及未支持配置见 [操作范围表](SESSION_OPERATION_COVERAGE.md)。

此前增量：[统一会话事务与跨语言夹具](UNIFIED_SESSION_PROOF.md)。新增 19 个方法，累计
188 个设计方法；42 条原模型重放与跨语言 23 组编码/13 操作夹具分别验证。动作与事件
已共享协议事务，外部效果不回滚。统一入口为 15/37；余下 22 项及受限配置逐项列在
[操作范围表](SESSION_OPERATION_COVERAGE.md)，不宣称全部协议开发完成。

此前增量：[事件服务与一致快照](EVENT_SERVER_PROOF.md)。新增 18 个方法，累计 169 个
设计方法、42 条原重放通过。chat/context、事件分页、快照及可信结果导入已在单一内存
锁域装配；动作执行提交到 outbox 的跨模型事务、其他生产操作和独立互通仍待完成。

此前增量：[事件与业务快照恢复](EVENT_RECOVERY_PROOF.md)。新增 13 个方法，累计 151 个
设计方法、42 条原重放通过。八类核心事件和完整 RecoverySnapshot 的消费已装配；
服务端快照/过滤/outbox 同事务、其余操作链和独立互通仍待证，不整体结单。

此前增量：[动作字节装配](ACTION_WIRE_PROOF.md)。新增 16 个测试方法，累计 138 个设计
方法、42 条原重放通过。confirm/claim/commit_result 和业务结果校验已接入固定动作夹具；
全事件/快照、其余操作链、独立互通仍未完成，不将局部闭环当作整体结单。

此前增量：[请求装配与消费恢复](PIPELINE_AND_CONSUMER.md)。新增 17 个测试方法，累计
122 个设计方法、42 条原重放通过；并修复 executing/committed 与 schema 不一致。
当时动作 confirm/claim/commit_result 字节入口尚未装配，现由上述增量覆盖；全事件/独立互通仍待证。

此前增量：[多步执行与恢复](MULTISTEP_AND_RECOVERY.md) 已补接受/撤权排序、双执行器
线程竞争、多步 partial 结果及三个非事务故障窗口的模型测试。新增 9 个方法，累计
105 个设计方法及 42 条原重放通过；全操作 wire 装配、事件 reducer、真实端口仍待证。

此前增量：[动作时序验证](ACTION_ORDER_PROOF.md) 新增 5 个方法，其中枚举 720 个有界
调度；修复已知效果仍报 none 及空事实 TypeError。累计 96 个设计方法及原 42 条重放
通过，回执为 linshi/g2a-protocol-design-20261007/action-orders-verification.json。

此前增量：[来源与聊天装配](SOURCE_AND_CHAT_PROOF.md) 新增 17 个测试方法，包含
accept/revoke/deliver 的 6 个有界顺序；累计 91 个设计测试方法及 42 条原模型重放通过。
回执为 linshi/g2a-protocol-design-20261007/source-chat-verification.json。
仅 chat.send 的成功响应链已实际装配；不是全操作/真实认证/网络投递验证。

此前研究增量：见 [外部协议研究](PROTOCOL_RESEARCH.md)。活动扩展新增 7 个测试方法，
统一检查累计 74 个通过，42 条模型重放通过；双层扩展摘要歧义已修复，新增的运行扩展检查
仍不代替完整授权/提交链。回执为 linshi/g2a-protocol-design-20261007/protocol-research-verification.json。

本表承接设计阶段，不把“工作草案流程完成”等同于“全部协议开发完成”。
默认保持用户此前允许伪代码/假实现、不推进具体游戏或生产部署的范围；
若之后明确进入真实 SDK 阶段，再增加对应实施和验收，不反向改写旧证据。

当前结论：已有可验证交付基线，但后续反向审查仍发现参考检查器缺口，不能据此宣称全部
协议开发完成。修订见 [交付审计与反例复核](FINAL_AUDIT.md)。下表保留各层证据边界；
生产端口和发布不因设计检查通过而自动通过。

## 验收与当前状态

| 交付 | 状态 | 证据或剩余工作 |
| --- | --- | --- |
| 核心语义、角色、状态与失败路径 | 已形成工作草案 | PROTOCOL、四份伪代码、CONFORMANCE_AUDIT；不是稳定标准 |
| 主流程与故障假实现 | 已有本地证据 | flow_model.py；42 条重放，另 10 组人工推演 |
| 可移植重放入口 | 已补齐 | scripts/replay_design.py，路径相对仓库定位，标准输出默认无产物 |
| 严格 JSON、整数、Unicode、限额与摘要投影 | 已补齐编码层 | WIRE_CONTRACT、codec.py、15 个本地测试方法 |
| 每个操作的请求/响应字段与闭合错误目录 | 工作草案交付完成 | 38 个操作、58 个边界错误；STATE_TRACES 全操作推演、PORT_FAILURES 端口/提交知识矩阵；真实适配器故障注入另验 |
| 新设计机器可读 schema 与正反例 | 交付完成，本地检查通过 | 生成一致性、全部操作结构正反例、独立 fixture、FlowModel 状态/效果接缝；不是完整生产 wire server |
| 能力组合与操作目录的自动一致性检查 | 依赖图和角色路由已验证 | 穷举 2^11 能力集合；角色/入口/能力检查、Relay lane 越权负例；不代表穷举全部业务交错 |
| 外部实现者独立使用的符合性包 | 交付完成 | verify_design.py 单命令验证；CONFORMANCE 文档、声明 schema/模板与反例；状态轨迹逐项区分证据级别 |
| 新增契约的交叉审计 | 反例驱动复核继续中 | FINAL_AUDIT §5；本轮修复时间下界、聊天字段/发送资格、资源共享子树深度；完整分层装配仍缺独立可执行证据 |
| 动作与事件统一会话事务 | 固定夹具闭环 | 19 个新增方法；真实请求凭据/止损额度/不可回滚效果；15 个入口，剩余范围见 SESSION_OPERATION_COVERAGE |
| 跨语言独立代码对照 | 有限夹具已装配 | JS/Python 的 23 组编码与 38 操作实际调用；不是第三方厂商、全 schema 或全配置互通 |
| 基础准入到 ready | 固定配置已闭环 | 20 个新增方法；7 个新入口、邀请/Grant 撤销、秘密安全重放；无设备/资源/自动规则，累计 22/37 |
| 恢复与控制转移 | 无呈现配置已闭环 | 20 个新增方法；3 个新入口、control_changed、假账本恢复；累计 25/37，不证明磁盘或设备 ACK |
| 呈现与设备准备 | 固定设备假端口已闭环 | 历史 25 个新增方法；2 个新入口、独立效果/ACK/rebind/handoff/补偿；当时累计 27/37；设备生命周期后继见下行 |
| 设备租约、独立重启与补偿 | 固定配置已闭环 | 41 个新增方法；renew、revision/epoch、fresh 证据与原 ACK 分离、满收据本地收敛；累计 38/38，无真实 Renderer/磁盘/后台服务 |
| 原请求回执与结果汇总 | 原 agent/player 固定配置已闭环 | 29 个新增方法；原终态、动作 ID/读权、控制下层收据、跨层 revoke ID 冲突与假重启；不开放游戏/执行器私有回执或跨 authority 查询 |
| 自动批准与规则撤销 | 固定 authority 已闭环 | 24 个新增方法；严格 Scope/时长匹配、玩家独立撤销、Grant/邀请/Session 不级联、启动隔离、故障/重放与假重启；不含规则管理 UI/长期回收/真实身份根轮换 |
| 资源闭包与缓存发布 | 固定声明式格式已闭环 | 30 个新增方法；asset.resolve 与准入/Renderer/控制恢复装配；累计 28/37，无真实网络、ZIP/第三方格式或 preinstalled |
| 本地启动与准入衔接 | 固定单应用假端口已闭环 | 29 个新增方法；launch.request、独立许可/效果、未知收敛及资源/呈现组合；累计 29/37，无真实 OS、长期回收或运行中进程监视 |
| 隐私请求与处理回执 | 固定控制者/密封内存清单已闭环 | 38 个新增方法；2 个新入口、cutoff/源过滤、独立副本效果、保留例外/未知查询；累计 31/37，无真实删除、动态备份发现或法律认证 |
| 玩家消息转发 | 固定可信席位已闭环 | 33 个新增方法；player_chat.forward、team 受众协商、当前成员代次与 Envelope 去重、隐私/重启衔接；累计 32/37，无真实玩家登录或输入签名 |
| Relay 配对、队列与恢复 | 固定双主体/游戏端口已闭环 | 52 个新增方法；5 项字节入口、三类凭据、两级提交、未知结果、撤销与重启；累计 37/37，无真实身份/网络/磁盘或长期回收 |
| 生产适配器、独立厂商互通、正式发布 | 非本阶段默认范围 | 不用假实现结论代替真实认证/网络/存储/引擎/法律决定 |

## 本轮新增选择

- `g2a-cjson-1` 固定 Unicode 标量排序、控制字符转义、整数范围、域隔离和摘要投影。
  与原规范“固定版本的规范编码”衔接，但不声称与其他 JSON 签名标准兼容。
- 明确 OperationRequest 的 version/extensions 必需，不能沿用描述性简写。
- 不在旧 SDK 注册新 codec，不偷偷改变旧 wire 版本和历史去重结果。
- FlowModel 保留其原有 fixture 摘要以复用原场景证据；它没有被自动认证为编码层实现。
  编码层测试与状态机测试分开，后续装配必须验证二者的接缝。
- 跨对象检查补齐 Scope 中的动作定义摘要、已选扩展和 created_at；自动规则排除两个
  本次绝对时间，但不排除最大授权时长。具体见 RELATION_CONTRACT。
- FlowModel 新接缝检查修复 executing 在 close/resume/handoff 后出现 unknown/none 的矛盾，
  改为 unknown/undetermined。原始模型 hash 保留作历史，当前模型及重放回执单独记录。
- 补齐 action.confirm 与 session.claim_control 两个命名操作；它们分别解决单次动作确认和
  目标设备领取凭据的入口缺口，不通过玩家 operation.get 泄露伙伴秘密。
- 动作值 schema 采用 g2a-value-schema-1 有限配置；禁止远程引用、正则和可执行验证器。

## 可复现本地命令

在仓库根目录使用 Python 3.11+ 标准库，无网络、无模型调用、无第三方依赖：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
rtk python scripts/replay_design.py
rtk python -m unittest discover -s tests -p test_design_codec.py -v
```

机器 schema/契约测试使用项目已有的 jsonschema 依赖范围（本次在 linshi 隔离 venv 中
使用 jsonschema 4.23.0 验证，不改全局 Python）：

```powershell
rtk python scripts/build_design_contracts.py
rtk python -m unittest discover -s tests -p 'test_design_*.py' -v
```

生成检查默认只读；只有显式 `--write` 才更新 contracts.schema.json、operations.json 和
OPERATION_DIRECTORY.md、conformance.template.json。不要手工修改生成文件而遗漏声明源。

完整门禁推荐使用 `rtk python scripts/verify_design.py`；命令及声明规则见
[符合性说明](CONFORMANCE.md)。它汇总实际执行日志和源 hash，但不会自动认证真实部署。

需要保存逐项模型回执时，显式指定已有临时目录下的输出文件：

```powershell
rtk python scripts/replay_design.py --output C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/portable-replay-results.json
```

测试源码属于仓库交付；本地日志、回执及临时驱动放 linshi。默认命令不向仓库写日志，
从其他工作目录以脚本绝对路径启动也可重放。旧 SDK 的依赖和测试入口不变。

## 证据限制

编码测试包含 15 个 unittest 方法，多个方法内含参数化子例；不能把它们与 42 条
语义轨迹相加后称为 57 个端到端场景。通过编码测试不证明请求有权限或动作已执行。
42 条模型重放迁入仓库后重新运行；迁入当时模型 hash 未改变，此后状态/效果修订已生成新
模型 hash，随最新 portable-replay-results.json 保存，不能把初始 hash 当当前文件 hash。
本轮没有运行旧 SDK 全套测试或任何 GitHub Actions，也没有提交、推送或发布。

操作契约这一轮新增 17 个测试方法，与编码层 15 个共 32 个通过。结构见证由声明生成，
用于验证 schema 可满足和字段约束，不冒充独立厂商互通；独立字节 fixture 与状态机重放
分别报告。此处是当时的中间证据；当前完成判定还包含后续状态/端口推演和最终审计。

跨对象/资源关系与模型接缝新增 15 个测试方法，错误映射新增 6 个，合计 53 个设计测试
方法通过；原 42 条主流程/故障重放在模型修订后仍通过。它们不是 95 个完整网络场景。

此前统一验证：62 个设计测试方法通过，0 失败/错误/跳过；42 条模型轨迹通过。新增覆盖
安全回执、隐私 pending、声明约束与逐操作追溯；不把方法数、参数子例和网络场景混计。

后续反向审查：4 个新增负例方法在修复前实际失败；修复后新增正例检查游戏情境不被聊天
成员规则误拒。最新统一验证为 67 个设计测试方法通过，0 失败/错误/跳过，42 条模型轨迹
通过；独立回执为 linshi/g2a-protocol-design-20261007/adversarial-verification.json，
不覆盖此前 unified-verification.json 的历史证据。详见 FINAL_AUDIT §5。
