# 全流程推演与本地模型验证记录

日期：2026-10-07。验证对象为本目录 `g2a-design-1` 设计与伪代码，不是既有 `0.1.0-dev` SDK。结论限于**设计与假实现级贯通**；不声称真实提供者、TLS、OS IPC、游戏引擎、窗口或资源沙箱已经验证。

后续开发补充：原临时重放驱动现已有 [仓库内可移植入口](../../scripts/replay_design.py)，并重新通过同样 42 条轨迹；下文保留原始运行记录及原驱动/模型 hash，不冒充当前 hash。之后模型状态/效果修订和新证据见 §6；新命令及尚未完成的开发项见 [开发台账](DEVELOPMENT_STATUS.md)。

## 1. 实际执行的本地重放

模型源文件：[flow_model.py](flow_model.py)。固定身份、逻辑时钟、内存账本、假世界/设备/资源，允许失败注入；没有网络调用或真实账号。

本次执行命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
rtk python C:\Users\Public\nas_home\AI\GameEditor\linshi\g2a-protocol-design-20261007\replay_model.py
```

实际结果：**42 passed，0 failed**。

- 模型 SHA256：`1161e8a8114c42fbca54656c16ce80860add874d6cd7e36ac10aff3e3f4ad50d`。
- 重放驱动 SHA256：`490759c442dd5bed711457a267befa2fef52fa4b9192f1d7c4bceef089002b41`。
- 完整逐项结果：`C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/replay-results.json`。
- 测试驱动及产物按本地约定放在 linshi；规范与假实现模型保留在仓库。上面的命令是当前工作区路径，不是发布后安装命令。

模型是伪代码的可执行子集，不是机械翻译器：publish/page 等辅助方法由已验证路由调用；handoff 在模型中假定设备 ACK 即时成功；资源只验证 fixture 的来源/大小/摘要；数据持久化用内存状态保留/清除模拟。下面用单独推演补充这些边界，不把 42 项通过扩大为全部生产安全保证。

## 2. 主流程结果

执行了 `local/local`、`local/cloud`、`cloud/local`、`cloud/cloud` × `game`、`companion` 两个入口，共 8 条。每条都经过申请/批准/邀请/加入，再发送情境与主动聊天、接受动作、领取、执行、提交结果、重复请求、关闭和只读结果查询。

每条实际断言：session 数量=1，effect_count=1，重复原动作返回 duplicate，终态 closed，呈现占用=0、slot=0；本地呈现恢复 baseline，云端无桌面不创建占用；关闭后仍能在保留期内读取 succeeded。位置组合使用不同端口选择和提供者 fixture，不是 8 次真实公网连接。

## 3. T01–T25 的实际模型断言与覆盖边界

| 轨迹 | 本次观察/断言 | 不扩大为的保证 |
| --- | --- | --- |
| T01 | 拒绝后邀请/会话/启动均为 0 | 未检查真实审批 UI |
| T02 | revision 改变导致 approval_stale，未创建会话 | 未验证真实端点签名 |
| T03 | 启动失败后 Grant 撤销且无会话 | 不实际启动 OS 应用 |
| T04 | 重复 join 返回同 session/g1，占用与会话均为 1 | 不模拟线程竞争，串行化责任见 §4 M01 |
| T05 | ready 前不能动作；准备期间撤权后闭会并释放占用 | ACK 延迟分支另见 M01/M02 |
| T06 | pending 取消后 claim 拒绝，cancelled 且效果 0 | 未运行真实执行器取消 |
| T07 | 领取后撤能力，旧 fence effect 拒绝，效果 0 | 模型不产生执行器取消结果；终态规则见 M03 |
| T08 | 结果未知后以原 ticket 取得原事实并更新 succeeded，效果仍 1 | 假世界是可查账本，不推及不可查外部效果 |
| T09 | 消耗 step 权后事实未知，再次 effect 拒绝，undetermined | 不宣称现实中效果一定为 0 或 1 |
| T10 | 旧 cursor 返回 history_gap，新 cursor 可读取保留事件 | 快照字段按规范单独受权限过滤 |
| T11 | 退队及同 Principal 重加均不能领取旧消息，新代可收新消息 | 不自动证明模型生成文本不泄密 |
| T12 | 两个 hide 会话先退一个仍隐藏，全部退出恢复 | 多设备故障见 M02 |
| T13 | 最新手动显示意图生效，冲突会话停止，旧请求被拒绝 | 不承诺网络远端瞬时收到闭会 |
| T14 | g1→g2 后旧邀请只返回 already_joined，g1 写拒绝 | 异步目标准备另见 M02 |
| T15 | fixture 摘要错误拒绝，admission 闭会且无占用 | 不证明任意真实解析器安全 |
| T16 | durable 恢复升代且旧 pending 取消；丢账本查询 unavailable | 不是真实磁盘断电测试 |
| T17 | 未知版本/required 扩展在 offer 前拒绝 | 新版本兼容集合需发布时冻结 |
| T18 | 容量满不接受动作，释放限制后原 ID 可接受，query/close 正常 | 不证明吞吐量或抗 DDoS 能力 |
| T19 | Agent lane 调 decide/claim 均拒绝，队列为空 | Relay operator 自身是已声明可信方 |
| T20 | claimed 超时 unknown，原 action 重发去重，效果=1 | 不推断外层超时意味着内层没接收 |
| T21 | 同 pull_nonce 返回同 claim，新 nonce 不重新领取已 claimed 项 | 多 worker 需兑现 Store 原子约束 |
| T22 | queued 撤销返回 not_dispatched、claimed 返回 unknown，旧 pull 被拒绝 | 撤邮箱不等于回滚游戏 |
| T23 | 重复批准只有一个 Grant | 完整参数冲突由控制回执算法拒绝，见 M04 |
| T24 | 原 resume 重试得到原 g2，新 ID 旧代次冲突，后续 g3 不返新 secret | 真实凭据存储/加密由端口实现 |
| T25 | release tombstone 拒绝迟到 acquire，保持无占用 | 墓碑到期安全见 M02 |

补充 9 条检查：错误身份和伙伴自批拒绝；最小无桌面云端伙伴可聊天但不执行动作；两页拼接无漏消息；来源类型保留/越受众拒绝/partial 删除后停止披露；会话到期及结果保留期；自动规则复用且 revision 改变不命中；资源来源与提供者身份不匹配拒绝；单会话 slot 冲突；进程 transport_epoch 变化后旧写权拒绝，重新认证 resume 后可写。

## 4. 模型未直接覆盖的逐步推演

以下是对文件中控制流的人工符号推演，不是自动测试日志。每项写出分支、最终状态和端口假设；真实端口保证另验。

### M01 接入 saga、并发重复与无资源分支

1. 两个 join 在 `atomic(invitation,grant,agent_scope)` 排序。先到者消费 I1 并记录 S1；后到者只能读取 consumed_session_id，不创建 S2。
2. 若尚未 ready，后到者返回 join_pending，不读取保存在 secret store 的写凭据；后台按同 admission operation_id 准备。
3. 无 avatar/presentation 时两个准备分支为空，仍检查 active/grant/deadline 后提交 ready，不遗漏最小伙伴路径。
4. 有资源时失败进入 fail_admission→close→release。设备已 acquire 而 ready 前撤权时，末次事务校验失败，同样关闭；已到达设备的 release 写 tombstone，未到达则设备租约最终收敛。
5. ready 提交后回包丢失，原邀请/原 intent/原身份只返回同代秘密。后续升代时返回无新秘密的 already_joined。

结论：在 Store 原子序列化及设备幂等/租约端口兑现时，不重复建会话，也不在准备前授权交互。真实跨进程原子性不是本次重放证明。

### M02 Handoff、同设备 rebind 与乱序 ACK

begin_handoff 将 ready 设 false、升代、撤旧写凭据后才排出释放任务，因此即使旧设备还显示形象，也不能继续写入。advance_transfer 在旧 release ACK 或可信占用租约到期前不开始目标 acquire；超过会话/转移 deadline 就失败闭会。目标资源或 acquire 失败也闭会，不恢复旧 generation。目标 ACK 后还须在事务中复查 Grant/session/代次，才能交付目标秘密。

同设备 resume 复用释放→获取阶段而不再次升代，控制回执绑定原操作 ID；重复唤醒只能推进同一个 rebind。release tombstone 保留到旧证明全部过期，回收后仍拒绝过期证明；乱序 lease 更新按 authority revision 拒绝旧值。release 只删除 `(session,generation)`，不能删除别的会话或更高代占用。该推演覆盖延迟/超时，不声称真实桌面已恢复。

### M03 动作拒绝、取消、部分效果与迟到事实

pending 取消在同事务终结为 cancelled/none，claim 再来只能看到非 pending。executing 撤权提高 action fence，之后的 world_step 因旧 ticket.fence 不匹配拒绝；已先进入效果临界区的一步可能完成，其事实不能被撤权抹除。GameAuthority 汇总既有 step：无效果为 cancelled/none，有部分事实为 cancelled/partial，账本不全为 unknown/undetermined。世界条件不允许的 step 返回可信“本 step 未执行”证明，不能误写整个动作 none。

旧 ticket 在 commit_result 只能报告对应原动作事实，不能调用新效果。terminal 同摘要幂等，不同摘要报 execution_conflict；unknown 可由原事实解决。journaled 模式查询原事实，nonatomic 模式已消耗 step 又缺事实时拒绝重做。I05 不依赖自动补偿或假设 exactly-once。

### M04 控制请求回执与关闭后秘密

控制入口先验证角色和对象受众，再按 `(principal,audience,operation,request_id)` 查回执。同键不同 payload 先拒绝，不能以改变 remember/launch/target_device 的重试修改旧同意。同键相同输入读原 outcome；若涉及秘密，还须本人、目标设备、现有 generation、ready 和未撤销全部满足。发起 handoff 的玩家只能查 transfer，不取得 Agent 写凭据。会话已闭会时只读结果句柄按独立授权保留，旧 write secret 不回放成有效权限。

### M05 资源图与不兼容形象

选择强制候选后先校验兼容，失败即停止，不进入较低优先级。依赖图有环/超深/超总大小在网络前拒绝；每个依赖的 origin 都要在已批准资源策略内，不能利用可信主资源加入陌生来源。下载逐跳校验实际目标，大小/hash 符合后再隔离解析；预装资源也按精确 ID/revision 核对。失败不开放 session.ready，不更改 action 授权。Archive/Parser 的安全性是端口要求，不能由 mock hash 通过推断。

### M06 事件分页、队伍代次与来源

假设序号 1 对 A 不可见，2、3、4 可见，page_size=2：扫描到 3 时停止，返回 [2,3]、cursor=3，下一页可读 4；不会因为提前扫描到 4 后截断而丢失。全不可见页受 scan_budget 限制，返回已扫描 cursor，不能死循环。成员离开再加入使用新代次，旧冻结受众不命中；新授权不修改旧事件受众。来源记忆的公开披露还需用户规则与原受众双重满足，文字生成本身不属于宿主可完全验证的属性。

### M07 到期维护、结果保留和新进程

入口在接收新请求前发现到期，执行 close 后使用 commit_and_return，不由后续 require 把闭会回滚。pending 动作到期终结为 cancelled；executing 到期停止后续效果并标 unknown。结果句柄不续租，关闭时计算读取截止，查询入口按服务端绑定记录而非客户端自报截止验证。结果到期返回 expired；volatile 丢账本返回 unavailable，不把 absence 解释成未执行。durable 恢复保留逻辑实例和 ID，但更新 transport_epoch/控制代次，旧 pending/执行权不会被复活。

### M08 Relay 重启、迟到回复与审批丢包

queued 被原子关闭且未领取时可报告本 Relay 没有派发，不能否定另一连接已接收相同业务 ID。claimed 超时只能 unknown；不重新入队。游戏保存过语义结果则重发同 claim reply；无可恢复事实则 unknown，不重做效果。过期 claim 的迟到 reply 返回 request_gone，而内层结果仍可经新 transport 请求原 action ID 查询。审批已提交而 reply 丢失，控制 request_id 命中同 Grant；外层 claim 本身不证明已批准。无持久 Relay 重启须作废旧 route，不能以空队列证明所有旧请求未执行。

### M09 角色、偏好与最小能力

游戏/伙伴/玩家 Principal 包含 issuer，显示名不作为凭据。伙伴发起必须 actor=agent，游戏发起由玩家或可验证委托者提交，GameAuthority 管理 token 不能自行代表用户同意。偏好覆盖用显式键而非 truthiness，因此 false 不会被默认值覆盖；resolve_user_policy 不写 actions/audiences。无 action/avatar/presentation 的核心伙伴仍可情境+文本交互；游戏 required_features 缺失则在 offer 前拒绝，而不是谎称该伙伴不符合所有 G2A 核心。

### M10 版本、治理与权利边界

精确共同版本、依赖与 required 扩展在批准前检查，结果进入不可变 Scope。标准未知字段拒绝，可选未知扩展不启用，关键权限语义不可藏在扩展中。旧 `0.1.0-dev` 仅通过隔离旧绑定提供，不用新 token 调旧 endpoint，不把旧 schema 当新设计的实现。规范/SDK 版本、草案/稳定、弃用窗口和发布许可分开；保持既有许可，不代替权利人批准公开发布或名称占用。至此覆盖的是发布/演进**规则设计**，不是发布动作已经完成。

## 5. 复核结论与不在证据内的事项

本轮已把主路径、T01–T25、补充检查以及 M01–M10 逐项对应到实际模型或伪代码控制流。发现的分页、成员代次、维护回滚、控制重试、跨域 slot、隐私路由、transport_epoch 漏检和世界拒绝汇总问题均已修订。当前没有据这些轨迹发现仍未处理的设计级阻塞；本阶段可交付完整工作草案和假实现流程。

这不是穷尽全部网络交错的形式化证明。真实适配器需验证的事项包括认证/加密、数据库并发与持久性、WorldGate 效果边界、资源解析沙箱、窗口/设备 ACK、公网延迟/负载、外部厂商独立互通，以及真实许可/发布决定。它们在设计中有契约或门禁，不靠假实现报告成功。

## 6. 后续状态契约接缝修订

模型的 executing 动作在 close/resume/handoff 后曾得到 state=unknown、effect=none，
接缝检查发现它与原语义和 ActionResult schema 矛盾，现已修复为 unknown/undetermined。
pending→cancelled 仍是 none；修复点和反例见 [关系契约](RELATION_CONTRACT.md)。

修订后 flow_model.py SHA256：`96253c22c0a6ca684d5f85bb96de3a37ccad9b3fa375f4dc29ab2a8cc44f6843`。
仓库内 replay_design.py 已对修订版重新执行，仍为 42 passed / 0 failed；当前模型和驱动
hash 记录于 linshi 下 portable-replay-results.json，初始 replay-results.json 仍保留原始证据。
