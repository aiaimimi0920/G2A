# G2A 协议场景验收与完成边界

本表用于人工复核，而不是以操作数或测试数宣布协议完成。当前交付目标为协议草案、
明确合同和可执行模型；生产 SDK、真实网络、引擎、账户系统与部署不在本阶段自动授权范围内。

## 已具备固定配置模型证据

| 用户场景 | 验收核心 | 证据入口 |
| --- | --- | --- |
| 玩家首次准入或邀请加入 | 身份、冻结 Scope、批准、过期与提交故障 | SESSION_OPERATION_COVERAGE.md |
| 最小 companion 会话 | 不虚构 action，聊天/事件/关闭与不支持功能拒绝 | MINIMAL_CORE_PROOF.md |
| 记住决定并自动准入 | 严格匹配、规则期限、全新 Grant、无隐式启动授权 | AUTO_RULE_PROOF.md |
| 运行中撤销动作能力 | CAS、执行 fence、保留既有效果与读权、不可隐式恢复 | CAPABILITY_REVOKE_PROOF.md |
| 响应丢失后的客户端恢复 | 原字节、关联校验、有界重试与查证、unknown 不降级 | REQUEST_RECOVERY_PROOF.md |
| 玩家离队或结果读权撤销 | 原结果不越权泄露；未知不等于不存在 | RESULT_READ_BOUNDARY_PROOF.md |
| 关闭后重复旧请求 | 过期消息清理、终态屏障与结果保留 | RECEIPT_RETENTION_PROOF.md |
| Relay 撤销与丢包恢复 | 独立 owner、双入口单次关闭、queued/claimed 知识分离 | RELAY_REVOCATION_PROOF.md |
| Relay 关闭载荷清理和有界重配对 | 清除 pull 副本、保留墓碑、新旧 token 隔离、容量拒绝 | RELAY_RETENTION_PROOF.md |
| 独立游戏 journal 清理 | owner 关闭见证、独立屏障、迟到 claim 拒绝、在途效果保留 | GAME_JOURNAL_RETENTION_PROOF.md |
| 关闭 journal 槽位回收 | 保留永久身份屏障、活动记录不变、容量释放与重启安全 | GAME_JOURNAL_GC_PROOF.md |
| 旧端口实例与不健康账本 | 身份/披露/派发/维护一致拒绝，恢复参数不隐式转换 | PORT_LIFECYCLE_AUDIT.md |
| 代次快照恢复独立模型 | 可信 checkpoint、类型伪装/同代次回滚/混合账本拒绝 | EPOCH_RECOVERY_PROOF.md |
| 代次公开绑定与可信证据 | 独立候选 profile，完整身份比对与注册/领取/关闭角色边界 | EPOCH_BINDING_CONTRACT.md |
| 代次凭据恢复 | 独立凭据锚点与模型时点一致、保留原 owner、不复活旧 token | EPOCH_BINDING_RECOVERY.md |
| 候选代次跨语言链 | JS/Python 实际绑定字节、错误拒绝、恢复和代次切换 | EPOCH_INTEROP_PROOF.md |
| 候选执行回执跨代次归档 | 独立读权、固定保留期、到期 gone 与防重执行分离 | EPOCH_RECEIPT_PROOF.md |
| 现有 Relay 固定代次 profile | 五操作字节链、显式 required 扩展、配对绑定与游戏端口跨代次拒绝 | RELAY_EPOCH_PROFILE_PROOF.md |
| Relay 动态轮换与未知查证 | 三提交点、有界旧回执、四类可信查证与跨语言恢复链 | RELAY_ROTATION_PROOF.md / RELAY_SETTLEMENT_INTEROP.md |
| 内层身份期限交集 | proof 不能延长底层凭据期限，派发/查证重验 | RELAY_IDENTITY_EXPIRY_FIX.md |
| 预装形象准入与迁移 | 精确版本/内容绑定、目标设备库存、无下载及控制迁移门禁 | PREINSTALLED_AVATAR_PROOF.md |
| 关闭会话下载缓存回收 | 独立呈现释放先于内容清理、有界事务、保留回执/预装目录 | ASSET_CACHE_RETENTION_PROOF.md |
| 资源回执关闭后回收 | 冻结期限、不重试续期、不因缺失推断未受理、内容独立保留 | ASSET_RECEIPT_RETENTION_PROOF.md |
| 启动许可独立撤销 | 原玩家/CAS、派发前阻止、派发后未知和效果保留、不级联 Grant | LAUNCH_PERMISSION_REVOCATION.md |
| 精确进程退出与会话关闭 | 历史 started 不等于存活、退出墓碑、unknown 保守处理、新进程隔离 | LAUNCH_PROCESS_MONITOR_PROOF.md |
| 启动回执与独立端口退役 | 回收不重启动、独立封存/确认、迟到请求拒绝 | LAUNCH_RECEIPT_RETENTION.md / LAUNCHER_RETIREMENT_PROOF.md |
| 两独立会话 authority 撤销传播 | 独立协调器身份、partial 不伪造 done、可信快照/原请求恢复、独立效果/读权 | CROSS_AUTHORITY_REVOKE_PROOF.md |
| 动态撤权目录与同 authority 多会话 | 冻结目录版本、未决不遗忘、退休墓碑、旧回放和独立会话读权 | FANOUT_CATALOGUE_PROOF.md |

表内证据仅覆盖各证明声明的配置。设备、资源、启动、隐私及 Relay 完整既有证明索引
见 [操作覆盖](SESSION_OPERATION_COVERAGE.md)，不能据本表推断任意配置互通。

## 协议设计阶段仍须收口的场景

| 场景包 | 必须明确并验证的边界 | 当前状态 |
| --- | --- | --- |
| 多会话与跨 authority 撤权 | 对象命名、撤权传播提交点、部分故障、独立读权 | 四类组合、可信恢复、动态目录增减及两个同 authority 独立会话已补；共享 Grant、其他对象、多玩家及全局准入/执行屏障待验 |
| 全账本生命周期 | 活跃回执、控制回执、幂等 tombstone、容量拒绝与长期清理 | 关闭会话消息回执、Relay 载荷和关闭游戏 journal 已有模型；活跃及其余控制账本待验 |
| Relay 长期运行和重新配对 | 旧配对/旧凭据隔离、保留期、多人公平性 | 已补关闭清理与代次隔离；[现有 Relay 动态轮换](RELAY_ROTATION_PROOF.md) 已覆盖 wire 接入、有界旧回执、新同意与故障恢复；未知查证收敛、真实防回滚和多人公平性待验 |
| 资源配置扩展 | preinstalled、格式/沙箱、缓存长期回收 | manifest、精确预装目录及关闭会话缓存 GC 已有；活跃/跨会话共享缓存、目录/回执回收及更多格式配置待验 |
| 启动许可生命周期 | 独立撤销、进程运行状态、长期清理 | 单应用撤销/监视、回执 GC、最终退役及其字节恢复已有；真实身份根、多应用、新代轮换与许可/offer 清理待验 |
| 隐私跨服务处理 | 动态复制/备份、混合数据拆分、屏障、长期调度 | 密封内存清单之外待验 |
| 配置组合矩阵 | feature 依赖、角色拒绝、各提交点前后故障与查询 | 最小 core 与固定组合已有，未穷尽 |

每个场景包的关闭条件：写清主体/owner/对象、先决条件、提交点、成功与失败可观察结果，
包含重复、乱序、过期、权限变化、提交前后故障和重启反例，并通过本地模型与契约门禁。
若决定不支持某配置，须在规范中明确拒绝合同并测试，不能仅以“以后 adapter 做”关闭。

## 独立生产验收

真实认证与配对、持久数据库崩溃一致性、网络重试、设备/引擎/OS 效果、第三方互通、
部署与安全评审另设门禁。模型通过不等于这些项目通过；协议最终冻结仍需人工复核。
