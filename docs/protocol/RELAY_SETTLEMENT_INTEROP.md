# Relay 查证恢复的跨语言组合证据

JS 客户端经现有 canonical 字节入口新增 26 次正式协议请求，分别构造四条独立链：

| 模式 | 游戏端中断位置 | 查证证据 |
| --- | --- | --- |
| unstarted | describe 派发 after_mark | 端口未调用见证 |
| admission | offer.create 提交后 after_game | 独立准入提交回执 |
| action | action.request 受理后 after_game | Envelope.id 受理回执及独立 reader |
| control | session.heartbeat 提交后 after_game | 会话控制请求摘要及独立 reader |

每条链都经过实际 Relay 注册、call 排队、pull 取得 claim、派发故障、revoke、端口
关闭屏障、journal GC 和封存。首先验证游戏代次切换被 outcome_unknown 阻断；
查证 before_commit 故障后仍阻断；after_commit 丢响应后假重启并幂等查证，然后
独立提交游戏和 Relay 代次切换。修改 claim 的夹具请求必须拒绝，不能借原 claim ID
替换查证内容。action/control 的准入先决步骤也使用实际协议字节请求建立。

## 夹具不是公开协议

`relay_settle` 仅为 Python 可信测试管道命令。它从当前 Relay 账本取得原 binding，
比对完整已提交 claim，不接受客户端自造主体/角色记录。底层查证仍验证独立端口
见证、游戏回执及授权。它不进入操作目录，不构成可部署的远程维护 API。

本轮正式操作仍为 38 项，总 wire 请求为 410 次；独立候选 binding profile 的
26 次请求另计。互通报告必须含 relay_settlement，完整四种模式、settled=4、
wire_calls>=26 及 passed=true。旧报告或布尔值冒充整数均不能通过新门禁。

此证据补充 Python 细粒度反例，不取代它们。四种模式各选一个业务代表，不宣称
全部查证配置均已跨语言穷尽。仍无真实网络/持久化、第三方实现、防回滚或任意
并发调度保证；可信维护与公开协议请求计数必须分开解释。
