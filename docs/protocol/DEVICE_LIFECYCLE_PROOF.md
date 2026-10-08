# 呈现设备租约、独立重启与补偿收尾

本工作包承接 [呈现基础证明](PRESENTATION_PROOF.md) 与 [Relay 证明](RELAY_PROOF.md)，
只验证协议契约、可信内存设备和字节链。新增明确的 `presentation.renew`，目录从 37 项
变为 38 项；不为保留旧数字而让 acquire 重试或 heartbeat 暗中延长设备占用。
旧 SDK/wire 未升级；`g2a-design-1` 仍是工作草案，不是稳定兼容版本。

## 1. 契约与责任层

- [contracts.py](contracts.py)：`PresentationLease` 精确绑定 session/generation、device/epoch、
  lease revision、terms、deadline、scope digest 和可信 authority proof 引用。DeviceObservation
  加入 device epoch；PresentationReceipt 报告有效 epoch/revision/deadline，释放后 deadline 为 0。
- [presentation_harness.py](presentation_harness.py)：每个代次仍只有一个 job；原 acquire
  payload 冻结，最新签发 lease、确认 lease 和释放义务分别保存。游戏已验证的续租与更新意图
  同事务；只读请求、非法请求和重复 heartbeat 不制造新的设备期限。
- [presentation_device.py](presentation_device.py)：独立效果域；当前证明才可更新尚未到期
  占用，条款不变，不重新调用 Renderer，也不反向续游戏会话。原 ACK 重放不能降版本。
- [presentation_recovery.py](presentation_recovery.py)：独立设备重启、fresh 验证及有界 outbox
  批次。它们是可信 fixture/本地端口，不是公开 wire 操作或真实后台服务。

`presentation.renew` 仍是 `presentation_authority/local` 权限，不开放给玩家、伙伴、游戏
普通凭据或 Relay 提交者。新字段和操作由声明源生成 schema/目录/声明模板，不能手改生成文件。

## 2. 不可混淆的提交点

1. 游戏存活提交成功后签发更高 revision；这时设备占用还没有延长。
2. 设备先保存续租效果和原请求收据；authority ACK 事务之后才提交。
   `before_commit` 故障发生在设备效果之后，不得回滚设备，也不表示未执行。
3. 当前 writer 不能越过已确认设备 deadline；更新已生效但 ACK 未知时保守闭会。
4. 转移判断使用最新签发 horizon 和可信本地事实，不能只看最初 acquire deadline。
   已验证到期 tombstone 可阻止尚未应用的新 revision；仅网络超时不构成释放证据。
5. `operation.get` 无原 ACK 时保留 pending。内部 outbox failed/superseded 只表示不再派发，
   不证明原设备效果失败。fresh 重启证据可确认精确 revision 的效果，但不伪造原请求 ACK。

## 3. 设备独立重启与恢复

设备重启创建新对象、递增 epoch 并退休旧对象；保留最新 baseline/manual_revision、
占用、tombstone、历史收据。每个占用都重新核对当前 authority、Grant、Scope、代次、
有效期限、原签发 payload 和资源准备；不可验证则移除并落 tombstone。

重启不延长 deadline。新 epoch 的 fresh 证据与历史 acquire/renew ACK 分开；旧 epoch
请求拒绝。未应用更新如仍有有效游戏期限，则以更高 revision 重新绑定 epoch；已应用且
ACK 丢失的精确更新标为 verified，不继续派发旧 epoch 请求。Renderer 重启失败仍保留
补偿义务，不声称恢复成功；authority 记录回滚不复活退休的旧设备。

## 4. 有界补偿与容量反例

单次 sweep 的预算为 1–32，停止义务优先，job 轮转，失败间隔为夹具时钟 1000 ms。
未知 ACK 重试同一请求 ID；已知失败才允许后续新 ID。普通收据与停止收据分别限额，
关闭、撤权和手动显示不会被待续租任务抵消。

交叉核验复现了更深的容量反例：128 次释放 Renderer 失败耗尽停止回执后，occupation
早已移除，tick 不会再渲染，Renderer 恢复也会被 resource_limit 永久挡住。
修复增加可信本地停止收敛：仅在停止回执满时使用，仍按原 session/generation 落 tombstone，
按最新 baseline 和其余占用重算，成功后记录独立 fresh evidence；不删除或改写 128 份原失败
回执。设备不可达或 Renderer 仍失败时保持 pending。效果后丢 ACK 的再次对账不重复渲染。

这不是绕过公开接口限额的新公开操作，也不是用容量异常伪造成功；已有有界 job 保存
本地停止义务与单份最新证据。长期 receipt/tombstone 回收仍未装配。

## 5. 实际验证与回执

专项：[test_design_presentation_lifecycle.py](../../tests/test_design_presentation_lifecycle.py)，
覆盖更新意图事务、revision/epoch、重试、过期、手动意图、撤权、handoff、未知 ACK、
独立设备重启、authority 重启、有界轮转、停止预留耗尽和 renew/close/restart 的六种排列。
历史呈现 25 个方法保留；生命周期新增方法与它们分别计数。

独立 JS/Python 客户端新增一条真实子进程字节链：准入→续租效果后丢 ACK→新 epoch 验证→
查询 done→旧 epoch 拒绝→更高 revision→离线关闭补偿→恢复后释放 ACK 丢失→同 ID 收敛。
该链 epoch=2、lease revision=3、待释放义务=0，Renderer 恰好调用 3 次
（acquire、重启、release），续租和释放重试不额外渲染。未增加原三个业务 reducer。

完整门禁、独立互通和交付检查分别保存到
`C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/`：

- `device-lifecycle-final-verification.json`
- `device-lifecycle-cross-language-final-verification.json`
- `device-lifecycle-final-hygiene.json`

回执保存实际测试数量、原 42 条模型轨迹、互通调用数及源码哈希。它们不与参数子例混计。
修复前证据另保留为 `device-lifecycle-red.log`、`device-lifecycle-capacity-red.log`；
本工作包基线为 `device-lifecycle-start-manifest.json`，不覆盖 Relay 历史证据。

## 6. 停止条件与限制

本工作包以固定配置的 lease→设备效果→fresh 重启证据→补偿链和匹配验证通过为停止条件。
不继续扩展其余 revoke 对象、preinstalled、多会话聚合或全配置证明。

没有真实设备、密码学认证、持久磁盘、OS 窗口、网络或运行中的后台 worker；同作者的
独立 JS 代码不等于第三方厂商认证。离线时只有设备本地时钟可落实到期，authority 无可达
证据时仍保守 pending；未证明所有线程交错、长期公平性、自动清理或物理断电恢复。
没有提交、推送、部署或调用 GitHub Actions；不把 38/38 入口数称为全部协议认证。
