# Relay 准入提交事实查证

## 为什么不能直接重试

游戏已提交而端口在 `after_game` 丢失回复时，journal 只有一次派发标记。重放原
业务请求不是通用查证方式：凭据、权限、业务状态和回执保留期都可能已改变。
也不能只按 request_id 找一个相似回执，更不能把回执缺失解释为未执行。

## 两个独立的证据来源

端口派发前保存 `dispatch_witnesses`，摘要绑定完整 claim 与可信主体/角色 binding。
未知请求的见证在 journal GC 后仍保留，假重启复制；正常回复落账后可移除。
该摘要不是客户端可以新增的授权记录。

游戏侧准入账本独立保存 `(principal, operation, request_id)` 对应的原请求摘要及
已提交回执。`settle_admission_commit` 在端口锁与游戏锁内同时确认：

1. 端口健康、当前代次、邮箱已经建立关闭屏障。
2. 该 claim 曾可能进入游戏，且提供的 claim/binding 精确匹配端口见证。
3. 原 inner proof 当前仍有效，主体和角色匹配；撤销或到期不能跳过。
4. 操作属于 `offer.create`、`offer.decide`、`invitation.redeem`、`session.join`
   的准入回执路径，不跨用 action/control/privacy 等其他账本。
5. 游戏侧原主体、操作名、请求 ID 及 version/operation/payload/extensions 摘要
   全部匹配。无回执返回 `outcome_unknown`，摘要冲突返回 `id_conflict`。

只有这些证据匹配，才移除 unresolved。返回值仅为
`{"settled":true,"acceptance":"committed"}`，不返回业务结果、邀请凭据或 outcome_ref。
这是可信端口维护方法，不是新的公开 wire 操作，也不修改旧 Relay 请求的保守回执。

## 接受事实不等于业务完成

`committed` 表示原准入请求的接收处理已经提交。offer 仍可能等待玩家决定，join
仍可能等待 ready；该方法不宣称异步业务完成，也不撤销或重启后续业务流程。
轮换只解除旧 claim 的执行不确定性，不改变游戏业务状态和内层权限。

提交前故障保留阻断；提交后丢响应保留原见证，重试必须再次通过当前授权及游戏
回执比对。即使上次收敛成功，之后回执丢失/授权失效也不能捏造新的成功回复。
成功切换代次后清理旧见证，由代次拒绝旧 claim。

## 当前证据及未完成项

Python 场景以 offer.create 实际提交后丢回复，覆盖关闭/GC、两种提交故障、假重启、
状态不变、仅派发一次及后续轮换。反例覆盖修改 claim、缺失/冲突回执和撤销 inner
proof。后续已补 offer.decide、invitation.redeem 和 session.join 的实际提交后丢回复、
GC、假重启、精确查证及轮换链；返回值精确断言为无秘密的提交事实，游戏主账本及
会话子账本在相同时间查证前后不变。

session.join 另验证了明确的 pending 边界：查证与轮换均不会把 ready 改为 true，
只有独立 finish_admission 才发布 ready。时钟倒退及 inner proof 到期边界均拒绝，
保留 unresolved，且失败查证不推进游戏时间。本结论不覆盖所有并发交错或业务配置。

本轮没有新增跨语言维护夹具，也没有生产查询端点。此内存适配器直接读取游戏
authority 的可信账本；未来跨进程实现需要认证查询通道、独立完整性/防回滚证据和
保留期合同，不能接受客户端传入的“回执”替代真实游戏账本。其余业务账本的未知
查证仍待独立装配，真实持久化与任意调度交错也未证明。
