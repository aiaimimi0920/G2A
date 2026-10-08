# 本地启动许可、外部效果与未知结果收敛

后续修订见 [隐私通道验证](PRIVACY_PROOF.md) §5：实际发送发现首次 join 的
device_id=None 未被 setdefault 替换，现已修复并以最新完整回执重验。下列统计与
launch-final-* 回执属于启动工作包当时的历史证据；当前总范围以操作范围表为准。

[LaunchHarness](launch_harness.py) 在既有资源/呈现/控制/准入层上装配 `launch.request`，
统一字节入口由 28/37 增至 **29/37**。底层 [LauncherPort](launcher_port.py) 仅维护固定
应用的内存注册表、假进程效果和独立回执；没有调用 OS、shell、网络或真实程序。

## 1. 单独批准，精确绑定

启动是 `player` 的 local 操作，不接受游戏管理员或伙伴代替玩家申请。wire 仍只有
offer_id、application_registration 和 launch_permission_ref；不得增加命令行、路径或
可执行参数。实际程序与参数来自可信本地登记，不能由该请求拼接。

创建 offer 时冻结当前本地应用登记（应用 ID、revision、玩家、伙伴、设备、固定程序与
参数）。`launch_required` 来自可信假进程观察，而不是“记住批准”或对话推断。已验证
运行的伙伴可以不取得启动许可而继续准入；不存在的伙伴不会因为 offer/批准而自动启动。

`offer.decide` 的原交互证据除精确 wire payload 外，必须包含用户所见的完整
launch_binding，且与冻结登记一致；它属于可信 Consent 端口，不是新增的客户端自报字段。
当前夹具直接用该 `decision_ref` 作为 launch_permission_ref，绑定 offer、玩家、Scope
摘要、完整登记和 offer 截止时间。Grant、许可、决定消费记录和收据同一 authority 事务
提交。许可不是秘密 bearer token；调用者仍须验证为该玩家。

应用登记发生 revision、设备、程序、参数、主体或 JSON 类型变化都会拒绝旧许可。比较
沿用 `g2a-cjson-1` 规范字节，不能把 `true` 与 `1` 当作等价。许可仅能绑定一个原请求 ID，
换 ID 或换 offer 不能重用；同 ID 改 payload/extensions 同样拒绝。

这里未实现自动规则，`remember=true` 仍拒绝。启动许可的独立撤销操作没有新增到 wire；
本包通过关联 Grant 撤销和截止时间阻止尚未派发的启动。

## 2. 三个账本切点，不伪装为单次事务

1. **authority 接受**：验证当前批准、应用登记、Grant、期限，消费一次许可并保存请求。
2. **派发与独立效果**：派发前再次核权，提交不可倒退的 dispatched 标记；Launcher 自身
   先记消费再产生效果。后续 authority 回滚不删除假进程、端口消费记录或独立回执。
3. **结果提交**：验证同一许可/登记的端口回执，提交历史结果及必要的失败撤权，再编码回复。

| 注入点 | 已知边界与原请求恢复 |
| --- | --- |
| before_commit | 接受事务回滚，无许可消费、无启动；原请求可重新验证 |
| after_accept | 已接受但未派发；查询 pending，原请求可在重新核权后继续一次派发 |
| after_dispatch | 已提交派发标记，但可能没有端口证据；保持 unknown，不补调用 start |
| after_effect | 独立效果/回执已经存在，authority 尚未保存结果；查询原端口回执恢复 |
| before_result_commit | 已发生效果不回滚；成功/失败结果事务回滚，原请求或查询重新导入事实 |
| after_commit | 原结果已提交，仅丢回复；重试读取原结果，不再调用 Launcher |

派发与撤权在此单锁 authority 中有明确顺序。可信调度注入点可以在接受后撤权、改变
登记或推进时钟；派发重新使用最新可信时间，不能用接受时的旧时间绕过到期。效果之后
发生撤权不会被结果事务回滚，也不会把已经启动的事实伪装成“从未启动”。

## 3. unknown 与失败分别处理

原 `OperationView` 只有 pending/done/failed，因此未决启动表示为 **pending，附
internal_failure/outcome=unknown**；不新增互相矛盾的 success 状态。端口抛异常、回执
畸形或缺少有效证据也只能保留 unknown，不能交给较外层异常映射改成 not_accepted。

`operation.get` 与原 launch.request 重试只读取原许可的端口账本，不通过再启动探测
结果。端口只有已存在且当前仍运行的同一 process_ref、精确登记与主体都吻合，才能由
可信握手将 unknown 收敛为 started。单有历史效果记录、进程已消失或另一个进程都不够。
无效果证据的 unknown 可以一直未决；本包不以超时清除消费记录来强求完成。

同一固定应用存在未解决的启动时，新的 offer/许可也不能再开一个实例；新的启动请求
记录为已接受的失败，不改变原未知事务。此屏障同时检查 authority 的派发记录和独立
Launcher 账本；不能只检查端口而漏掉“已标派发、尚无端口证据”的窗口。
确知启动失败返回 `launch_failed/accepted`，
与撤销该 offer 未使用的 Grant 同事务提交。身份不匹配的假进程即使已经产生，也不能
取得邀请；错误结果不意味着已有进程被自动撤销或终止。

历史 started/already_running 回执是当时事实，不证明当前程序仍运行，也不恢复被撤销的
Grant。玩家查询只得到非秘密状态，伙伴或其他主体不能查询玩家的启动收据。

## 4. 启动不等于加入，更不等于 ready

启动成功不会创建 Session。邀请领取另需已验证运行的目标进程、fresh 的原伙伴身份及
登记设备；启动绑定不会替代邀请凭据。邀请重放时身份失效或程序消失不再交付秘密。
加入后保留控制设备绑定，同设备 resume 仍走既有恢复与代次规则，不重新启动应用。

准备期间进程消失会关闭准备会话，不能提交 ready。若还协商了 assets/presentation，
仍须完成资源验证与设备 ACK；新增测试贯通了启动→邀请→资源→呈现→ready。

假账本重启现在覆盖尚无 Session 的阶段：复制 authority 状态，退休旧实例，保留独立
Launcher/设备/资源端口；损坏账本拒绝操作与查询。此证明不涉及磁盘落盘或真实进程崩溃。

## 5. 实际验证

[test_design_launch.py](../../tests/test_design_launch.py) 新增 **29 个方法**，包含成功与
已运行、单独批准、精确应用/设备绑定、成功/失败提交故障、未知前后效果、撤权/到期、
同 ID/不同 ID 的双线程竞争、prejoin 重启、资源呈现组合与设备恢复。

反例运行实际纠正了：端口异常裸抛、历史效果被误当作当前进程、准备期进程消失仍
ready，以及接受后时钟推进但派发仍用旧时间。最后的窗口核验还补上了已标派发但无
端口记录时，新许可绕过未决屏障的反例。对应负例在修复前失败，修复后重新执行。

完整设计门禁累计 **312 个方法**，原 **42 条模型轨迹**分开统计。JS/Python 独立代码
夹具累计 **23 组编码正反例、125 次 wire 调用、27 个操作**；新增三条启动链分别证明：
提交故障后查询恢复并正常加入、未知效果经现有进程证明收敛且不重启、已知失败撤权且
不创建会话。两条有启动效果的独立场景各 1 次，失败场景 0 次；不是三个真实程序。

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
rtk proxy python scripts/verify_design.py --interop --output C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/launch-final-verification.json
```

同目录 `launch-cross-language-final-verification.json` 保存独立互通回执，
`launch-final-hygiene.json` 核对最终源 hash、UTF-8 无 BOM、AST、链接和改动范围。

## 6. 明确未完成

仍是固定登记、单应用/设备、单会话的假端口配置。没有真实程序注册/签名核验、OS
进程启动/退出、凭据管道、进程监视、跨进程持久化、独立启动许可撤销接口或长期回收。
初始准备之后的持续进程存活检查、云端提供者唤醒及多应用调度不在本包证明范围内。

本包交付时还有 8 个操作未装配，当前状态见 [全操作范围](SESSION_OPERATION_COVERAGE.md)。本包没有修改
旧 src/SDK/示例/工作流，没有提交、推送、部署或运行 GitHub Actions。
