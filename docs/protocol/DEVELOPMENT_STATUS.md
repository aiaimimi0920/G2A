# 协议开发交付台账

最新增量：[关闭会话回执清理](RECEIPT_RETENTION_PROOF.md)。新增 10 个方法，累计预期 527 个；
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
