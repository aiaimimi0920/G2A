# 呈现设备字节链、独立效果与补偿

后继增量见 [设备生命周期证明](DEVICE_LIFECYCLE_PROOF.md)，已补显式续租、独立设备重启和有界补偿。
本文保留原 25 项专项/253 项累计证据及当时限制，不将历史成绩改写成新一轮复跑。

后继增量：[资源准备与缓存](ASSET_PROOF.md) 已补固定声明式 manifest 的资源字节与原子
缓存链。本文保留当时无资源准备的配置边界与验证计数，不回写历史成绩。

本增量在 [ControlHarness](control_harness.py) 上组合 [PresentationHarness](presentation_harness.py)
和 [PresentationDevice](presentation_device.py)，新增 presentation.acquire/release，统一入口
为 **27/37**。设备、身份、authority 证明、Renderer 与时钟全部是可信 fixture；没有真实
桌面窗口、网络、磁盘或资源解析器。资源与隐私等剩余范围仍见 [操作表](SESSION_OPERATION_COVERAGE.md)。

## 1. 授权与不可回滚的设备效果

Scope 冻结已批准的 presentation_terms；JoinIntent 必须带 selected_device 和登记的
DeviceObservation。领取邀请及首次 join 均重验设备归属、baseline 和 manual_revision，
不能只凭 device_id 或旧观察准入。未协商 presentation 的 core profile 不要求设备。

每个准备阶段先持久于内存假 authority 账本一个 job，绑定 session/generation/device、
Scope 摘要、条款、deadline、operation_id 和 authority_proof_ref。固定 presentation_authority
凭据才能调用本地入口；game/player/agent 的普通凭据均不自动拥有该角色。新 acquire
必须精确匹配 job，不能由调用者扩大 deadline、替换 Scope 或目标设备。跨设备 handoff
仍需要玩家针对完整旧 Scope 和目标的精确批准；仅将同一已批准 mode 投影到明确的目标，
不悄悄修改原 Scope/Grant。目标设备使用自己的 baseline，不复制源设备的显示状态。

设备占用与 Renderer 效果独立提交，然后 authority 才记 ACK。`before_commit` 在这条
操作链表示**设备已经执行，authority 尚未保存回执**；它不同于普通纯协议事务的故障位置。
设备效果、receipt 和 tombstone 不随 authority 回滚。相同请求重试查询原设备回执，不重复
渲染或延长占用；after_commit 丢包也相同。回执是历史应用事实，不是永远有效的当前状态。

## 2. 准入、恢复、转移与迟到 ACK

- join 创建 session 但只返回 join_pending。可信 finish_admission 在实际 acquire ACK、
  未过期占用和当前授权都满足后，才能发 ready 事件和交付写凭据。
- resume 只升代一次，先进入 releasing，再 acquiring；同一 resume 请求等待期间返回
  pending，rebind 完成后返回 ready，不把重试当作新恢复。
- handoff 同样先撤旧写权。只有已保存的成功 release ACK，或**已验证的设备本地租约到期**，
  才能进入 acquiring。设备实际释放但 ACK 丢失时，在原租约到期前仍等待原 release 重试，
  不读取本地 bool 后猜测网络 ACK 已成功。
- 目标 acquire 完成还不足以交凭据；advance_transfer 重新验证并原子提交同代 ready 事件。
  未准备完成的 target claim 为 pending；close、撤权或超时后不恢复旧控制者。

关闭、失败及撤权的协议提交同时保存待释放 job。已成功 ACK 的释放不重复入队；未知
acquire 结果仍保留补偿义务。模型通过后续 presentation.release 字节请求执行这些义务，
没有假称已运行后台调度器。设备到期是独立可信维护端口，不能以任意网络超时替代。

## 3. 最新玩家意图与失败状态

release 先记录本代 tombstone、删除本代占用，再按设备最新 baseline/manual_revision
重算；旧代 release 不删除目标新代占用。若玩家在 ACK 丢失后手动显示，或在待 acquire
期间更新本地意图，旧准备请求不得再次隐藏窗口。coexist 不强制显示，也不覆盖玩家的隐藏选择。

Renderer 可以返回失败但实际状态已经改变。PresentationReceipt 的 applied 与
actual_visible 分别报告；失败会停止相关会话并保留补偿，而不是声称窗口已恢复。
本地租约到期触发的 Renderer 失败也必须传播，不能把“占用删除”当成“释放效果成功”。
失败 release 的原 ID 重试保留原失败收据；明确的新 release 请求可再次尝试渲染，但不会
重建已 tombstone 的占用。operation.get 只向设备所属玩家返回呈现操作的历史 done/failed
和 outcome_ref，不附带控制秘密，也不把该状态当当前会话存活证明。

## 4. 反例和实际验证

[新增测试](../../tests/test_design_presentation.py) 为 **25 个方法**，覆盖证明篡改、错误角色、
邀请后观察变化、ACK 前后故障、同 ID 拒重、最新手动意图、Renderer 失败、释放补偿、
同设备 rebind、跨设备 handoff、本地到期、假 authority 重启及 6 轮 close/acquire 线程竞争。

其中两条新负例实际失败后修复：

1. 目标 ready 后重试原 acquire 曾返回 `transfer_in_progress`；现在允许当前有效代次读取
   原收据，不新增占用、不重复 Renderer 调用，过期/关闭/tombstone 仍拒绝。
2. 旧占用到期但 Renderer 恢复失败时，曾从 releasing 进入 acquiring；现在追踪可信
   Renderer 失败并关闭会话，转移状态为 failed。成功的本地到期仍可替代缺失 release ACK。

完整设计门禁累计 **253 个方法**；原 **42 条模型轨迹**独立重放，不扩充旧轨迹计数。
JS/Python 夹具累计 **23 组编码正反例、78 次 wire 调用、25 个操作**。新呈现场景独立验证
初始 acquire ACK 丢失、旧 release ACK 丢失、目标 ready 与重复 acquire、关闭后迟到 acquire，
两台假设备总共恰好 4 次 Renderer 调用；该场景另外读取 2 条控制事件。原业务 7 条事件、
控制恢复场景 4 条事件及 2 次世界效果保持原分母。JS 仍只有原三个业务 reducer，呈现场景
做字段/顺序断言，不宣称全 schema 客户端或第三方厂商认证。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
rtk proxy python scripts/verify_design.py --interop --output C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/presentation-final-verification.json
```

同目录独立互通回执为 presentation-cross-language-final-verification.json，源码 hash、
UTF-8 无 BOM、AST 和本地链接交付检查为 presentation-final-hygiene.json。以实际回执为准。

## 5. 明确保留的限制

- 未实现 asset.resolve、真实下载/解析及 avatar 资源准备，不能用呈现 ACK 证明资源安全。
- 当前单会话、至多四个固定设备、有界 job/receipt，不声明多会话占用聚合或长期清理完成。
- 没有设备租约 revision 更新；heartbeat 不更新设备占用，设备原 deadline 到期则保守闭会。
  这可能牺牲活性，但不会暗中延长旧证明。长期 tombstone 清理和自动补偿调度仍待装配。
- 假 authority 重启保留同一独立设备对象；不是设备自身重启、断电或 fsync 证明。pending
  transfer 遇 authority 重启仍保守失败闭会，并保留两代补偿义务。
- 设备本地 manual_change 立即改变本地意图，authority 在后续维护观察到后停会；没有跨设备
  瞬时原子性。真实通知延迟、离线设备、任意线程交错和真实认证仍需单独验证。

本轮未修改旧 src/SDK/示例/工作流，未提交、推送、部署或调用 GitHub Actions。
