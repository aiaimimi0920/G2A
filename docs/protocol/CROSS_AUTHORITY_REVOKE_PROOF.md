# 两独立会话权威的撤销传播组合

## 范围与主体

revoke_fanout.py 是候选内部协调模型，调用既有 permission.revoke 的 session、grant、
result_read 或 capability 分支，不增加
公开操作或新 schema。调用方传入的 player 是可信适配器已认证主体，不是允许公网
自报 Principal；目标只能通过可信 register 登记，每个目标仍使用自己的玩家凭据。
协调器不产生 game 管理权，不代理任意 URL，不代替各接收方核验权限。

目标键绑定完整 GameInstance（game issuer/subject/kind、instance_id、epoch）、
session_id、grant_id、规范 Scope 摘要和所属玩家。两个 authority 可以都有 s1/g1，不得只按
这些本地 ID 合并。登记和派发时检查当前绑定；目标换代/Scope 改变拒绝派发，不能
悄悄路由到新会话。最多 16 个活动目标、64 个退休墓碑、64 个协调请求，容量耗尽明确拒绝。
动态目录版本、目标退出和历史重放合同见 [目录证明](FANOUT_CATALOGUE_PROOF.md)。

## 提交与知识

begin 要求精确 catalogue_revision，冻结该版本、本次 object_type、目标集合、每目标
expected_revision 和原始请求字节。其 request_id
由内部生成且重启保持的 coordinator_id、协调请求 ID 与完整目标键确定；重复 begin
不增加目标、不改 CAS，改内容冲突。不同新协调器有独立命名空间，不能自报复用旧身份。
这里只撤销该快照中的选定对象，不是阻止未来新准入的全局永久禁令。

每次 deliver 只访问一个独立 authority：先将本地项标为 unknown，再发送原字节。
接收方继续执行自己的 CAS、权限、去重、动作停止和事件事务。协调器只在获得
request_id、对象类型/ID、预期终态及原 revision+1 全部匹配的合法响应时确认。
session 的预期终态为 closed，grant/result_read/capability 为 revoked，不能只凭同名 ID 确认。
无响应、畸形回包、拒绝或 CAS 冲突均不能宣称原请求未提交，也不自动换 ID/改 CAS。

整体状态：零目标确认是 pending，部分确认是 partial，全部确认才是 done。
这里 partial 是传播完成度，不是 ActionResult.effect。接收方提交后丢响应，或者
协调器取得响应却未保存 ACK，都保持 unknown；假重启后重发原请求，接收方重放原
撤销回执，不重复增加 revision/事件。不回滚已经关闭的另一 authority。

## 可观察的非原子窗口

一侧已关闭、另一侧尚未确认期间，另一侧可能仍 active 并继续执行已批准动作。
这不是跨服务瞬时撤权屏障；需要全局同步禁止新效果的配置必须另有共同权威协议，
不能由这个 fanout 声称实现。done 也只证明所选旧会话的撤销提交，不控制后来新会话。

关闭保留既有世界效果和独立结果读权。组合测试在两侧各执行第一步，关闭一侧后
该侧第二步被拒，另一侧仍可执行第二步；两侧最终关闭后事实分别保留为 1 和 2 个。
一侧追加 result_read 撤销只影响该侧结果，不能因同名 s1/a1 泄露或撤掉另一侧读权。

## 当前证据与缺口

最初七个测试方法运行真实 SessionHarness 字节入口，覆盖同名对象隔离、单侧提交、两种
接收方提交故障、协调器 ACK 丢失、假重启、旧协调器拒绝、CAS 冲突不自动重基、
主体/目标代次/回包关联拒绝、部分世界效果保留、读权独立和严格目标选择。

假重启现在检查独立可信内存 checkpoint，独立接收方对象不复制；没有真实网络/数据库、
后台调度或公平性证明；跨语言固定链和恢复假设见下文。当前能力撤销仅覆盖逐目标
明确选择的已批准 ID，不覆盖自动跨游戏能力语义映射、多玩家与全局准入屏障；动态目标
新增/退休及两个同 authority 会话的固定组合已有 [独立证据](FANOUT_CATALOGUE_PROOF.md)。
因此不能把本固定组合等同于多会话与跨 authority 场景包全部完成。

## 绑定检查与接收方受理的换代竞态

原组合只在协调器锁内检查目标绑定，然后另调用接收方 submit。并发反例证明另一
线程仍可取得接收方锁，在检查之后替换 epoch：原 permission.revoke payload 只有
本地 session ID，不能自行拒绝新代同名会话。先新增反例复现该窗口，再修复模型。

现在以接收方自身 RLock 同时覆盖当前绑定核验和原请求受理，随后释放锁再解析响应。
两个新增测试验证并发换代不能插入这个窗口，以及成功、提交前/后故障、绑定拒绝后
另一线程仍能取得接收方锁。固定锁序为协调器锁到一个接收方锁；不同时持有两个
接收方锁，接收方不得回调协调器并引入逆序锁依赖。

这是本地组合端口的原子绑定核验，不是网络共享锁。未来远端适配器必须在接收端
原子核验完整目标绑定，或使用不可重定向到新代的已认证实例端点；仅客户端缓存
检查或路由到复用 URL 不满足该合同。现有公开 revoke payload 没有因此新增字段，
不能据此声称任意 HTTP 适配器已实现跨代安全。

## Grant 与结果读权的不同效果

每个协调操作只选一种 object_type；重试时修改类型与修改目标/CAS 一样是 id_conflict。
未知或未实现类型拒绝，不降级为 session 撤销。grant 目标 ID 从可信登记的 grant_id
取值，session/result_read 从 session_id 取值；相同 Scope 换成新 Grant 也必须拒绝旧
目标派发。增加 grant_id 会改变候选内部目标键，旧协调快照不能无证据重算键/请求 ID；
没有提供历史快照迁移或公开 schema 变更。

grant 撤销沿接收方原规则关闭关联会话并推进 Grant revision，分别保存两侧提交事实。
result_read 只推进各自 result_access_revision，不关闭会话、不撤 Grant、不取消动作。
测试在第一侧读权已撤时验证第二侧仍可读；两侧读权都撤后，原动作仍可执行已批准
第二步，两个世界事实均保留，而双方 action.query 都被拒绝。不能把“禁止读取结果”
当作“撤销执行权限”，也不能用会话关闭替代用户选择的窄撤权。

五个新增测试覆盖 Grant 两种提交故障与恢复、读权 ACK 丢失和独立效果、对象类型冻结/
未知类型拒绝、同 Scope 换 Grant 拒绝及同 request_id 的错误类型/状态/对象回包拒绝。

## 逐目标能力撤销

capability 必须同时提供 capability_ids，键集合与本次目标集合完全一致，每个值是
该目标当前冻结 Scope 已批准的 action ID；不能省略、补通配符或把一个全局名称自动
映射到多个游戏。其他 object_type 不接受 capability_ids。注册目标的 Scope 摘要
同时绑定批准的定义摘要，因此同名 action 不代表相同语义，也不允许换 Scope 后沿用。

选择映射复制进入协调账本，并写入每目标原始 request 字节；调用者后续修改字典不
改变已受理意图。各目标以自己的 capabilities_revision 执行 CAS；受理前不扩大任何
Scope。每个目标撤销后的回包仍须匹配原类型/对象/revision 和 revoked 状态。

五个新增测试验证一侧能力撤销阻止该侧后续步骤，另一侧仍可执行；最终保留 1/2 个
独立世界效果，双方会话/Grant/结果读权保持不变。接收方 after_commit 丢响应后重试
不重复推进 revision；后续 capability.replace 不能恢复该侧已撤定义。另验缺失/额外/
未批准选择拒绝、选择副本不受调用者修改影响，以及两个目标分别撤 find-key/open-door
而不影响未选的第三个 authority。此组合不声称跨服务瞬时停止或任意动作模型已穷尽。

## 独立 JS/Python 候选组合互通

revoke_fanout_peer.mjs 独立计算完整目标绑定的 SHA-256 键、每目标 request_id 和
permission.revoke 规范字节，不导入 Python schema 或冻结请求。可信管道夹具核对
客户端字节与已批准协调意图完全一致后，调用原模型及真实 SessionHarness 受理路径。
这不是公开协调 API；返回协调进度，不伪装成新的 OperationReply 类型。

四条链分别执行 session/grant/result_read/capability：先拒绝修改 CAS 的请求，再
提交第一侧形成 partial；第二侧 after_commit 丢响应保持 unknown；协调器假重启
后重发原字节收敛 done，接收方 revision 和事件序号不得再次增加。最终逐类核对
会话/Grant 状态、Grant revision、读权 revision、能力 revision 和定义数量，证明
四类撤权不会被统一成“关闭所有会话”。

四类链各拒绝派发前旧快照和 ACK 保存前旧快照，合计 8 次恢复拒绝；有效 unknown 快照
恢复保持 coordinator_id 和原请求字节。另在同一接收方上，以相同 operation_id 先通过
一个协调器撤结果读权，再由新的独立协调器撤会话，验证请求命名空间不会碰撞。

上述固定组合共 18 次客户端编码请求（其中 4 次修改 CAS 拒绝），63 次夹具命令。加入
[动态目录链](FANOUT_CATALOGUE_PROOF.md) 后现为 28 次请求、119 次夹具命令。此计数
独立于正式 38 操作/503 次请求，也独立于候选 epoch 的 26 次请求，不重复相加为公开
操作覆盖。互通门禁要求四类全部完成、8 次快照拒绝、独立命名空间、固定候选范围标记
和严格整数计数；缺失或旧客户端总 passed 不能替代本子报告。

此链没有新增真实网络认证、持久存储防回滚或跨服务原子屏障证据。

## 协调器身份与可信恢复

原 request_id 仅摘要 operation_id 和目标键。回归反例已复现：两个独立协调器登记同一
接收方并复用 operation_id，先撤结果读权再撤会话，第二个请求因同 ID 不同字节被接收方
拒绝，协调器只能保持 unknown。现在 request_id 为 `fanout-` 加以下规范数组的 SHA-256：

```text
[coordinator_id, operation_id, target_key]
```

coordinator_id 在可信构造时生成，不作为调用者可选参数。恢复必须保留经锚点认证的旧
ID；新协调器的独立命名空间用于独立新意图，不能用于替代未知请求恢复或绕过原 CAS。
没有旧协调器身份/锚点的历史候选快照不提供自动迁移，不能静默重算请求 ID。

`snapshot()` 仅导出 coordinator_id、player、目录 revision、完整冻结目标绑定、退休墓碑
和协调 records 的深拷贝；
每条记录的选择、对象类型、能力 ID、request_id、原始 bytes、CAS revision 和进度全部
纳入 checkpoint。端口对象、玩家凭据映射及可信 checkpoint 保留在快照之外，不接受
快照自报替换。恢复只复用可信登记的独立接收方，不把接收方恢复为协调器快照时点。

账本和其独立锚点视为同一模型提交边界：登记/退休目标、begin 保存意图、派发前保存 unknown、
合法响应保存 acknowledged 均更新 checkpoint。派发前必须完成本地 unknown 提交，再调用
接收方；接收方 before_commit、after_commit 或 ACK 丢失不改变这条先后约束。恢复要求
候选快照完整匹配最新锚点，故旧快照不能删除操作、回退 ACK 或混入另一协调器的目标/记录。

摘要为 map/list/bytes/null/str/int/bool 分别打类型标签；例如 True、1、原始 bytes 和
描述 bytes 的普通列表不能互换。不支持类型明确拒绝。这是模型内部恢复编码，不是新
wire 编码或数字签名。校验失败不修改当前账本、不退役当前实例；校验成功后才退役旧
实例。intact 必须为严格布尔值；intact=False 恢复出的不健康对象及旧实例对登记、读取、
派发、导出快照和再次恢复均 fail closed。

可信恢复这一轮新增 10 个 fanout 回归方法，该文件共 29 个，覆盖身份碰撞、四类撤权两种远端提交
故障的显式快照恢复、派发前锚点顺序、登记/begin/ACK 旧快照、混合/外来账本、篡改 owner/
目标/选择/字节/进度、锚点缺失、深拷贝、严格类型及全部不健康入口。

可信假设仅包括当前进程的 live state、端口/凭据映射和独立 checkpoint；不抵抗任意
live-memory 篡改，也不检测账本和锚点被同时回滚。实际适配器仍须实现原子持久提交、独立
最新位置证明、恢复认证和真实崩溃验证。本模型不能把未知接收方提交自动判为未发生，
不能让恢复成功等同于跨 authority 原子撤权。
