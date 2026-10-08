# 控制权恢复、转移与旧代隔离

后继增量：[呈现设备与补偿](PRESENTATION_PROOF.md) 已补固定假设备的释放/获取/rebind 和
迟到 ACK 字节链。本文保留当时无 presentation 配置的验证边界与计数，不回写历史成绩。

本增量为 [ControlHarness](control_harness.py)，复用准入与会话模型的同一锁域，新增
session.resume、session.handoff、session.claim_control，组合入口为 **25/37**。使用固定
身份、逻辑时钟、内存假账本及目标就绪假端口；没有真实磁盘、设备窗口、密钥或网络。

## 1. 恢复与转移字节流程

resume 必须来自重新验证的原伙伴身份，匹配当前设备；检查已协商 resume、durable
端口承诺、Grant、租约、恢复窗口、账本健康及业务快照一致性。成功在同一事务中提升
generation、保存原凭据/控制收据、阻止旧动作新效果并发布 session.control_changed。
同 ID 重试先匹配收据，不再升代；新 ID 携带旧 expected_generation 则冲突。

当前无 presentation 的 resume 直接就绪，不伪造设备 rebind 成功。恢复窗口采用保守的
固定上限 `min(初始租约, join 时间 + resume_window_ms)`，普通 heartbeat、旧回执和恢复
本身均不延长此窗口。它与仍可能通过新 heartbeat 延长的会话租约分开。

handoff 需要玩家对 session、expected_generation、target_device、完整 Scope 的精确
批准，并验证目标 agent/设备/会话/Scope/期限证明。事务先提升代次、停止旧代写权，
置 ready=false，创建 acquiring 状态和尚未交付的目标凭据，发布 control_changed。
此配置没有 presentation，因此旧呈现释放阶段为空；不是“收到超时就认定已释放”。

可信 advance_transfer 端口报告目标准备成功后，原子提交 controller_device、ready、
TransferView 和 session.ready 事件；失败或截止时间到则闭会，不恢复旧 generation。
仅目标设备上重新验证的原伙伴可 claim_control；未就绪返回 pending，成功领取不再升代。
玩家只能读取 TransferView / operation.get，无权读取目标写凭据。

## 2. 回执、安全降级与事件

秘密回放每次重验身份有效期、原设备、当前会话/Grant、generation 和 transport_epoch。
关闭、撤权、后续升代或传输代次变化后，旧 resume、join、redeem、claim 回执不能交付
新代或失效秘密；返回 completed_without_secret。operation.get 的恢复/转移记录也使用
同主体键，但输出始终不含控制秘密与结果句柄。

resume 生产一次 control_changed；handoff 先生产 ready=false 的 control_changed，目标
就绪后生产同 generation 的 session.ready。现有 BusinessConsumer 实际消费这些事件并
恢复控制代次和目标设备；八类核心事件现都有生产路径，但不等于全配置/任意时序已验证。

## 3. 假账本重启的精确边界

restart_from_mock_ledger 是可信测试端口，将完整内存状态复制到新的 authority：Scope、
Grant、成员/来源、事件、控制/动作/消息收据、确认、ticket、步骤账本、读权和凭据表均
保留。原 authority 被退休，逻辑实例 epoch 不变，transport_epoch 递增；旧网络凭据不能
直接复用，后续 fresh resume 仍需升 generation。已发生效果不会自动重新执行。

这里 `durable` 是假 Store 端口的协议承诺，不是声称 Python 字典有磁盘耐久性。intact
标志和完整检查点来自可信端口；模拟不完整时拒绝 resume 及无法验证的结果读取。模型
不证明能识别任意未报告的账本损坏，也没有断电/fsync/真实进程崩溃证据。

若重启时 transfer 仍在等待，本窄模型选择失败闭会，不尝试重放真实设备 saga。以后
装配 presentation 时仍须补释放、获取、延迟 ACK 和恢复补偿，不能直接推广这个简化。

## 4. 实际复现的两个接缝问题

1. **结果读权已撤销，恢复回复仍列出 unresolved_actions 的 ID。** 新负例先失败，再将
   join/resume/claim 的 ControlDelivery 汇总到共享生成路径，恢复清单从当前过滤快照
   的可见动作中产生。不以“只泄露 ID 没有正文”为理由绕过读取授权。
2. **transport_epoch 改变、resume 尚未升代时，旧执行 ticket 仍能产生新 step。** 新负例
   实际得到 `ContractError not raised`。动作接受记录现同时冻结 transport_epoch，效果
   临界区校验它；旧 ticket 仍能查询/报告原事实或读取已缓存步骤，不能开始新效果。
   相应内部字段和规则同步更新于 DATA_PLANE，不改变公开 ExecutionTicket 字段。

同时补齐原 join/redeem 的跨 transport 秘密回放检查，避免新进程原代次尚未改变时返回
已经不能写入的旧控制凭据。Scope 和授权内容没有因此扩张。

## 5. 验证与可复现命令

[test_design_control.py](../../tests/test_design_control.py) 新增 **20 个方法**：fresh/设备/
证明绑定、收据冲突、提交前后故障、pending→ready、超时失败、只读状态、旧效果保留、
假重启、完整性拒绝、恢复窗口和满日志原子性。包括 6 轮双 resume 竞争及 6 轮就绪/关闭
竞争；只允许一个升代赢家，关闭之后不得出现晚 ready 复活。

JS/Python 独立夹具新增实际 resume→假重启→再次 resume→handoff→目标 claim 的链路，
断言旧 token 失效、玩家拿不到秘密、control_changed/ready 的序列与 generation 匹配。
累计 **23 组编码正反例、59 次 wire 调用、23 个操作**；新增控制场景读取 3 条
control_changed 和 1 条 ready。原业务 7 条事件恢复、准入 ready 及 2 次世界效果继续验证。
JS 仍只有原三个业务 reducer，新增控制事件做明确字段/顺序断言，不冒充全 schema 客户端。

完整设计门禁累计 **228 个方法、42 条原模型轨迹**；不同分母分开报告：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
rtk proxy python scripts/verify_design.py --interop --output C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/control-final-verification.json
```

独立跨语言与交付检查回执分别为同目录下 `control-cross-language-final-verification.json`
和 `control-final-hygiene.json`。以实际回执和源码 hash 判定，不因本文计数自动认证通过。

## 6. 仍未完成的范围

剩余 12 个入口为 player_chat.forward、launch.request、asset.resolve、presentation.acquire/
release、privacy.request/receipt 和五个 Relay 操作。已有入口仍有限制：无真实或假呈现
设备 ACK 链、无自动批准/启动许可、无任意多会话/多动作、无长期收据清理/tombstone；
operation.get 尚未汇总子层全部动作/控制收据。详见 [全操作范围](SESSION_OPERATION_COVERAGE.md)。

本轮没有运行 GitHub Actions、修改旧 src/SDK/示例/工作流、提交、推送或部署；不把同一
交付方两份代码的有限互通称为第三方厂商认证。
