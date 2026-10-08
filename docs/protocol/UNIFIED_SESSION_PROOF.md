# 统一会话事务与跨语言夹具验证

后继：[准入到就绪字节链](ADMISSION_PROOF.md) 新增 7 个受限入口和 session.ready 生产链，
组合入口现为 22/37。本文保留当时 188 方法/13 操作跨语言证据，不回写历史回执。

本增量把此前分开的动作账本与事件服务装配到同一个 authority 和 RLock，再以独立手写
JavaScript 编码器/客户端调用 Python 假服务。仍是 `fixture-only`、固定主体、单会话、
单个两步 find-key 动作；不建立网络服务、不改变旧 SDK、不分配新的部署版本。

## 1. 完成的装配与事务边界

[session_harness.py](session_harness.py) 组合 [action_harness.py](action_harness.py) 和
[event_server.py](event_server.py)，共 15 个字节操作入口。完整清单、每项限制和另 22 个
尚未装配的操作见 [全操作范围表](SESSION_OPERATION_COVERAGE.md)，不是 37 项全实现。

协议事务同时保存或还原会话、成员代次、动作账本、确认消费、执行 ticket、消息/控制
收据、结果视图与 outbox。回复完成校验/编码后才提交；提交前异常回滚上述状态，提交后
丢回复保留事实。chat/action 使用同一个消息 ID 命名空间，跨类型同 ID 冲突不留下半个动作。

执行端口 `execute()` **不属于可回滚的协议事务**：

1. 新效果之前检查当前权限、原定义/代次、截止时间，并检查发布容量。
2. 已发生世界效果保留在原可信账本。效果后发布失败置 `pending_sync`；后续读写先修复
   结果与 outbox，不能交付落后快照，更不能把外部效果随字典回滚。
3. 已消费步骤重试只取旧事实，不重新执行，不无故增加 revision 或事件。
4. 崩溃窗口保留 unknown；可信 reconcile 可收敛已知部分效果，不能由执行者报文自造证据。

新增的五个控制入口包括 heartbeat、close、permission.revoke、capability.replace 和
membership.replace。控制键包含主体/操作/request_id，摘要覆盖完整控制内容；heartbeat
重试不续租，当前写权失效后不能重放旧续租。成员更新依赖预置可信证明与 CAS，重新加入
增加成员代次。能力移除/改义只缩小已有批准，不把新定义自动加进旧 Scope。

当前生产者覆盖 chat.message、game.context、action.state、capability.update、
membership.update、session.closed 六类。session.ready 与 session.control_changed 的
生产链仍随准入/恢复/转移待补；八类消费器通过不等于八类生产者已完成。

## 2. 满额、停止和结果读权

固定模型普通消息收据 256 条、动作消息收据 64 条、动作控制收据 64 条；取消在前两层
各有一个预留槽，结果提交在动作控制层另有一个预留槽。这是单动作模型的止损容量，
不能直接推广成任意多动作/无限请求的资源管理策略。

关闭/撤权/取消/finish/reconcile/结果提交可为收敛裁剪内存事件历史；不删除消息拒重
记录、当前业务事实或任何文件。旧 cursor 经 history_gap 恢复。关闭本身和裁剪处于同一
协议事务：关闭失败不能只留下已裁掉的历史。真实持久日志保留调度仍未实现。

关闭停止新效果，保留原结果读取期限；result_read 是单独的撤销对象。撤销先于动作创建
时，之后的新动作也必须过滤。撤销不代表收回已经编码、在途或客户端已收到的明文。

## 3. 实际发现并修复的反例

| 反例 | 原因与最小修复 |
| --- | --- |
| 删除能力后仍能接受第一个动作 | 没有当前定义可用性；接受与效果边界均核 definition_available |
| 先撤结果读权，后创建动作仍出现在快照 | 只撤销当时存在的动作；同步新动作时也传播既有读权撤销 |
| 满事件日志关闭后无法 finish 部分效果 | 事实收敛误走新效果背压；finish/reconcile/commit 使用止损预留 |
| 请求携带失效凭据却用另一个固定有效凭据检查 | ActionHarness._write 改用本次已解析身份；增加 generation/transport/device 三项负例 |
| 动作层预留了取消槽，共享收据层仍拒绝 | 两层额度不一致；共享消息账本同样为取消预留一个槽 |
| 控制收据耗尽后无法提交已有世界事实 | action.commit_result 增加独立收敛槽，不扩大普通 claim/confirm 额度 |

后面三项先运行新增负例，实际得到 2 failures / 2 errors（凭据测试既有子例失败又有
后续状态断言失败），修复后通过。容量负例直接构造可信模型容量边界，不冒充数百次真实
网络提交。新增 [test_design_session_harness.py](../../tests/test_design_session_harness.py)
共 19 个方法；其中接受/快照竞争执行 8 次真实双线程排序，不声称任意并发穷尽。

## 4. 独立 JavaScript 对照链

[codec_peer.mjs](codec_peer.mjs) 独立实现严格 UTF-8 JSON、重复键/数值/Unicode/资源限额、
Unicode 标量排序的规范编码与域隔离摘要。[客户端](../../scripts/design_interop_client.mjs)
不导入 Python fixture、schema 生成器或消费器，手写身份、报文与期望业务结果；通过
[驱动](../../scripts/verify_design_interop.py) 的本地子进程管道调用 Python SessionHarness。
管道外层控制帧、凭据标签、效果/裁剪/证明注入均是**可信测试控制面**，不是新增 wire 操作。

本次实测：Python 3.12.10、Node.js v22.22.2；23 组编码正反例，51 次夹具指令中有 23 次
wire 调用，涉及 13 个不同操作。恢复 7 条事件，最终世界效果始终 2 次，业务结果为
`{"item":"gold-key"}`。测试包括：

- 整数形键与非 BMP 键排序、控制转义、中文/组合字符、特殊对象键；两端 canonical 和
  message digest 逐字节对照；非法数值/重复键/Unicode/深度/容量同时拒绝。
- 丢聊天和结果提交回复后的幂等重试；同 ID 改正文冲突；完成步骤重试不重做效果。
- action.query、事件逐项归并与快照中的结果一致；坏页不推进本地状态；裁剪后从
  history_gap 的过滤快照恢复；结果撤权后查询拒绝、快照不再包含结果。
- heartbeat 不重复续租，能力/成员更新、关闭后旧 heartbeat 不再生效。

这证明了**两个语言实现之间的有限夹具互通**，不等于独立厂商互通：两份代码仍来自同一
交付方，JS 仅实现三个事件 reducer 和局部响应断言，不实现整个 JSON Schema/八类消费器。
action.cancel/action.confirm 未在该跨语言夹具中调用，由 Python 方法验证。没有 HTTP/TLS、
实际认证、持久化、进程崩溃恢复或独立团队认证。

## 5. 可复现验证与交付判定

仅 Python 的原统一门禁保持可用；跨语言门禁增加 Node.js（不安装 npm 依赖）：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
rtk proxy python scripts/verify_design.py --interop --output C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/unified-session-final-verification.json
rtk proxy python scripts/verify_design_interop.py --output C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/cross-language-final-verification.json
```

在装有 jsonschema 的 Python 环境运行，可从其他工作目录使用脚本绝对路径。`--interop`
是显式门禁；不提供该选项时回执记录 `not_run`，不会把未运行的 Node 检查算作通过。

本增量目标回执包含 188 个设计测试方法、42 条原模型重放及上述跨语言夹具，三种分母
分别报告。最终是否通过以 `unified-session-final-verification.json` 的实际结果和源码
SHA256 为准，不用文档计数代替运行证据。

本轮闭环是动作/事件同事务、五个控制入口与有限跨语言对照。其余 22 个字节入口、已有
15 项中的受限配置，以及全八类生产链尚未完成，见范围表的明确停止条件；不能把这些
设计假实现工作改名为生产工作以宣称整体结单。未提交、推送、部署或运行 GitHub Actions。
