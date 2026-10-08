# 准入到就绪的统一字节链

后继：[恢复与控制转移](CONTROL_PROOF.md) 新增 3 个入口和 control_changed 生产链，组合
入口现为 25/37；本文保留当时 208 方法/20 操作跨语言证据及基础准入 profile 边界。

本增量从没有会话的 authority 开始，经两个入口完成 offer、玩家决定、邀请、加入和
ready，再使用实际交付的控制凭据进入既有聊天/动作链。不是直接注入一个 active 会话
后宣称准入完成。实现为 [admission_harness.py](admission_harness.py)，组合既有
[SessionHarness](session_harness.py)，不替换旧 SDK、不建立真实账号或网络服务。

## 1. 接入范围

新增 7 个入口：describe、offer.create、offer.get、offer.decide、invitation.redeem、
session.join、operation.get。加上既有 15 项，组合入口共 **22/37**；每项受限配置与
剩余 15 项见 [操作范围表](SESSION_OPERATION_COVERAGE.md)。permission.revoke 还扩展了
邀请撤销和加入前 Grant 撤销，不能把扩展子类型再算成一个新操作。

已执行的主链：

```text
已登记玩家/伙伴身份 → describe → offer.create → offer.get
→ 预置可信玩家交互证据 → offer.decide → invitation.redeem
→ 邀请专用凭据 + session.join → join_pending（不带控制秘密）
→ 可信准备端口 finish_admission → ready 与 session.ready 同事务
→ 原 join 重试 → 原控制凭据 + 独立结果句柄 + 当前会话/高水位
→ chat.send 或 action.request/claim/step/commit_result → 事件与结果读取
```

game 入口由玩家本人发起，不由 GameAuthority 冒充玩家；companion 入口由绑定伙伴发起。
describe/offer.get 也先检查身份和归属。邀请 ID 不是认证证明，fresh agent 身份知道 ID
仍不能调用 join；必须提供预登记在邀请专用通道上的凭据，且该凭据不能调用其他入口。

## 2. 冻结、原子性与秘密安全

Scope 从请求与描述协商得到，调用现有跨对象校验，冻结动作定义摘要、受众、策略、限额
和绝对期限。控制去重键含主体/operation/request_id；内容冲突拒绝，同请求不重新建
offer、Grant 或邀请，也不延长原期限。玩家决定的假证据必须精确匹配完整批准字段；
Agent 文本、游戏管理身份或自报 decision_ref 不能生成批准。

AdmissionHarness 与子会话使用同一个 RLock。创建会话之前，事务保存准入记录；创建后，
还同时保存子会话/成员/凭据/动作 checkpoint。普通协议请求提交前失败回滚全部相关状态，
提交后丢回复保留原记录。WorldGate 的 execute 仍在独立路径，已发生效果不被协议回滚。

首次 join 原子消费邀请、建立 ready=false 会话及内部凭据。无可选资源的配置也经过
finish_admission，而不是绕过 ready 提交；ready 事件与可写状态同时出现。重复 ready
不产生第二事件；准备失败或 descriptor 过时则闭会，不能重新 ready。

原 join 只回放原代次凭据，不提代、不续租。闭会、撤权、超出秘密保留期或代次变化后
返回 completed_without_secret；未 ready 返回 join_pending。operation.get 按主体读取
当前 pending/done/failed 状态，但只返回无秘密视图；玩家不能借查询领取伙伴 token。

本模型把邀请秘密和原 join 秘密的可重放期限都限定为 15 秒邀请窗口（且不超过批准期限）。
此窗口不是会话租约；有效会话的已交付控制凭据不因此自动到期。窗口后本模型不通过旧
邀请再次交付秘密，后续 fresh 恢复路径仍待 resume 装配。这个保守限制不是所有真实实现
必须采用的保留参数，不能隐含延长或重新签发。

## 3. 撤销、到期与只读句柄

- 未消费邀请可撤销；已消费邀请如实返回 consumed，不谎称因此关闭既有会话。
- Grant 撤销同时作废未使用邀请、关闭其已建立的会话；失败回滚覆盖两层状态。
- 请求前按受信逻辑时钟独立提交到期维护；后续请求认证失败或其他异常不能回滚闭会。
  时钟回退拒绝，不猜测宽限期。这里只是调用时维护，不是后台调度器。
- 准入交付的结果句柄为 results_reader，不得写动作；会话关闭后，仍可按原独立读权和
  期限查询已发生结果。结果读权撤销仍不能收回已编码/在途/已收到的明文。

## 4. 反例和实际检查

[test_design_admission.py](../../tests/test_design_admission.py) 新增 **20 个方法**，覆盖两个
入口、越权/伪证据、冻结与重试冲突、创建/批准/领取/加入/ready 的提交前后故障、失败
闭会、邀请/Grant 撤销、只读句柄、原代次秘密保护、到期独立提交、最小 core 配置。

其中执行 6 轮真实双线程重复 join，以及 6 轮 ready/close 竞争；最终只允许 closed，
事件序列为 `[closed]` 或 `[ready, closed]`，禁止晚 ready 复活会话。这是有界进程内
排序证据，不是多机或磁盘事务证明。

新增反例实际发现：**协商 action_ids=[] 但仍选择 actions 能力时，初始快照带出了未获
批准的默认定义**。负例先失败，再修正 EventServer 的初始定义过滤和 ActionHarness 的
初始可用性，要求同时匹配 Scope 的选择与定义摘要。修复后空动作集合能够构建合法
BusinessConsumer，不再靠“动作请求稍后会拒绝”掩盖错误的能力视图。

秘密回放复核另发现：控制代次改变后，join 已不回放写凭据，但原 redeem 回执仍回放旧
邀请凭据。该凭据不能越过 join 的代次检查，却违反统一的旧代秘密回放规则。负例实际
失败后，把 consumed 邀请的会话状态/代次/租约检查移到两种秘密响应共有边界；两者都
降为 completed_without_secret，不以“后面还会拒绝”保留不必要的秘密交付。

跨语言夹具同步扩展：JS 从 describe 的公开字段手写 Requested，独立检查 Scope digest，
完成可信决定失败/成功、丢批准回复重试、邀请凭据核验、pending/ready、无秘密查询、
ready 事件与关闭后安全重放。最新共 **23 组编码正反例、41 次 wire 调用、20 个操作**；
原 7 条业务事件恢复和 2 次世界效果仍通过，另验证 1 条新生产的 ready 事件。JS 的三个
业务 reducer 没有扩成全八类实现；ready 此处做独立字段/顺序断言。

统一检查累计 **208 个设计测试方法、42 条原模型轨迹**，跨语言单独计数。入口：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
rtk proxy python scripts/verify_design.py --interop --output C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/admission-final-verification.json
```

使用 Python 3.11+、jsonschema 和 Node.js；无 npm 依赖、网络、模型调用或 GitHub Actions。
独立跨语言回执为 `admission-cross-language-final-verification.json`，编码/链接/hash 核对为
`admission-final-hygiene.json`，均在同一 linshi 目录；最终通过以精确源码 hash 的回执为准。

## 5. 未完成项不能隐去

当前 profile 只支持固定登记玩家/伙伴、单实例、一次会话生命周期、volatile 账本、core
及可选 actions。主动声明不支持的配置不会伪成功：remember=true、launch_permission=true、
设备 JoinIntent 字段以及 required 的未支持扩展/能力会拒绝。可选未知扩展不执行，但原
请求仍完整参与拒重摘要。尚未实现自动规则、Launcher、资源/呈现准备、Provider 回调，
也没有长期 receipt 清理/tombstone；operation.get 尚未汇总子层全部动作/控制回执。

当前生产七类核心事件，剩余 session.control_changed 随 resume/handoff/claim_control
继续装配。测试中的直接代次变更仅证明原秘密不能越代回放，不冒充恢复/转移已经实现。
真实身份与秘密存储、持久化、网络发送排序、独立厂商互通、生产引擎及发布都未验证。
本轮未提交、推送、部署，未修改旧 src/SDK/示例/工作流。
