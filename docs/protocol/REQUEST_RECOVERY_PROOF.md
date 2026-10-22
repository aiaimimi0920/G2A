# 请求恢复：提交知识、同请求重试与原回执查询

本包新增 [request_recovery.py](request_recovery.py) 的 `RequestRecovery` 内存模型。
只支持 action.request、action.cancel、session.close 三个明确场景，不增加公开操作、
HTTP 服务、SDK 自动重试器或凭据存储。它给出决策与字节，不实际发送、睡眠或取消动作。

## 1. 外部规范研究与采用边界

2026-10-23 在线核对以下官方规范，区分规范原意和 G2A 的独立选择：

| 来源 | 核实内容 | G2A 的采用与不采用 |
| --- | --- | --- |
| [RFC 9110 §9.2.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2.2) | 非幂等请求的自动重试需要语义幂等性或原请求未应用的可靠依据 | 不从 HTTP 错误猜未接受；沿用 G2A 原主体/ID/摘要账本，不把 POST 本身当幂等 |
| [RFC 9110 §10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3) | Retry-After 描述后续请求的等待时间 | G2A 的 retry_after_ms 仅决定最早查证/重试时点，不证明未执行；没有在本包实现 HTTP 日期头解析 |
| [RFC 9457 §3.1.4](https://www.rfc-editor.org/rfc/rfc9457.html#section-3.1.4) | 人类可读 detail 不应被解析成机器控制信息 | 使用闭合 code/retry/outcome 契约；HTML 和异常文本不触发授权/重执行；不把 G2A Error 改成 Problem Details |
| [JSON-RPC 2.0 §5](https://www.jsonrpc.org/specification#response_object) | 响应关联原请求 ID，result/error 互斥 | 复用严格回复校验，并检查原操作与业务 ID；不声称 G2A 线格式就是 JSON-RPC |
| [MCP 2025-11-25 Transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) | 断流不应被解释为客户端取消 | 丢响应进入原请求查证，不自动生成 action.cancel/session.close；不移植 MCP 会话和 SSE 机制 |

旧错误目录已经描述这些边界，但缺少客户端连续观察的可执行决策链。本包把最容易
误用的情形固定为模型：第一次发送丢回包后，第二次被限流/撤权，不等于第一次没执行。

## 2. 提交知识不是“最后一条错误”

模型分别保存最后获得的原请求接受知识和下一步恢复动作：

```text
unobserved < not_accepted < unknown < accepted
```

这是本客户端累积证据的保守合并顺序，不是世界效果成功等级。unknown 表示某次原
请求可能已接受；后来一次拒绝不能消除它。accepted 表示至少已知原请求被接受；
以后超时也不能把已知接受降回未知。not_accepted 只来自合约有效的原响应，不从
socket 失败、异常文字、HTTP 状态或查询拒绝推断。

`in_flight` 单独标记等待响应/查询；outcome 是累计观察，不是对仍在途请求的未执行
担保。`response_received` 只表示拿到有效原响应；`resolved` 只表示原 OperationView
已 done/failed。都不把 action 的 unknown/partial 转为 succeeded/none。

| 观察 | 下一步 |
| --- | --- |
| 有效 not_accepted + same_request，且仍有预算 | 等待后只取原字节重试 |
| 有效 not_accepted + after_reauth/after_renegotiate | 提示需认证/协商，不签发凭据或新效果 ID |
| 有效 not_accepted + never | 停止自动恢复 |
| 原发送丢响应、畸形/错关联回包、累计 unknown | 查询原回执，不自动重放变更 |
| 已接受的操作失败但没有结果正文 | 查询原回执，不重做效果 |
| 查询被拒、结果已过保留期或不可用 | 保持原知识，标记 unresolved，不伪报从未执行 |
| 查询 pending | 预算内继续查询 |
| 查询 done/failed | 交业务层处理原结果，不推断世界效果 |

本模型选择“未知时优先查询”，比协议允许的同 ID 安全重放更保守；不把这一策略
伪装成 RFC 强制规则。既有服务器仍可能安全处理同 ID 重试，必须以其账本与当前权限为准。

## 3. 不可变请求与关联

构造时保留实际请求字节，不重写参数、deadline、extensions、outer request_id 或
Envelope.id；重试接口没有替换 payload/ID 参数。查询使用保存的请求，不跟随
ErrorDetails.operation_ref 之类的提示去读别的对象。

- action.request：查询 original_request_id 使用原 Envelope.id。
- action.cancel：使用取消消息自己的 Envelope.id，不使用被取消动作 ID。
- session.close：使用原外层 request_id。

原动作收据还验证 id 与完整原 Envelope 的 record_digest。查询响应同时校验当前 poll
的外层 request_id，以及 OperationView.operation/request_id。查询丢回包后必须使用
新的 poll ID；旧 poll 迟到不能覆盖当前恢复。所有检查通过后才提交客户端状态。

context 是可信调用者提供的 authority/主体/生命周期绑定标签；不接受不同标签的
观察或出站请求。该标签不是认证协议，更不是服务器自报字符串的身份证明。真实
传输适配器必须验证对端并将读权凭据正确绑定原主体；本包不生成或恢复该权限。

## 4. 有界性和时间

默认最多 2 次原字节重试、8 次原查询；参数分别限定为 0..8 和 1..16，拒绝 bool。
查询 ID 集合也受此上限约束，不自动后台无限轮询。耗尽后保留事实并交人工/上层恢复。

本地可信单调时间不能回退。retry_after_ms 对后续查询与重试都生效，新的较短延迟
不降低已经记录的等待下界。时间加法使用内部整数；若超出 wire Nat 可表示范围，
不能溢出成立即重试。该内部截止值不是新增 wire 字段。

## 5. 实际验证

[test_design_request_recovery.py](../../tests/test_design_request_recovery.py) 新增 21 个方法：
未知后拒绝、已接受后超时、同字节/退避/预算、三类 ID、错关联和畸形响应、原业务收据
摘要、上下文与时钟、查询丢失/迟到、保留期/读权拒绝、六种错误顺序以及超大时钟边界。

其中真实模型字节组合场景从准入建立会话：action.request 提交后故障丢回包，客户端
查原业务 ID 取得接受事实，再执行一个步骤并重放原请求，世界效果仍恰好 1 次。
这是内存 authority 与客户端模型的组合证明，不是 HTTP/TLS 或磁盘故障测试。

初版 16 个方法在实现前因缺少模型文件实际失败，保存在 red.log；不得称为旧产品的
16 个漏洞。随后新增的边界测试与完整门禁预期累计 582 个设计方法、42 条原轨迹。
既有 JS/Python 23 组编码、38 操作/350 次 wire 另跑回归，本包未新增 JS 恢复实现。

证据目录：`C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-request-recovery-20261023/`。
最终以 `final-verification.json` 为准。未覆盖所有操作 owner、认证/协商恢复、HTTP 头
解析、持久客户端恢复、通用自动重试调度器或全部并发历史；旧 SDK 不自动接入本模型。
