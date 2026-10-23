# 公共准入与启动入口的 enrolled 凭据期限审计

## 复现与责任层

继 Relay proof 的底层期限修复后，公共 AdmissionHarness._identity 仍仅检查固定
主体/角色，没有检查可选 expires_at。LaunchHarness 的 launch.request 与新启动
许可撤销都复用此入口，因此过期玩家身份仍能实际产生启动效果。

新增测试先在旧代码复现 `AssertionError: ContractError not raised`，再在共同
_identity 层修复，而不是在 launch.request/permission.revoke 各加不同规则。

## 统一规则

请求先由既有 _maintain 提交可信单调时间。enrolled 凭据存在 expires_at 时，要求
严格整数且 last_now < expires_at，否则 unauthenticated。bool、字符串和空值
不能转换成合法期限；未携带该可选字段的既有固定身份保持原行为。

此检查先于操作授权、业务处理和旧回执重放。历史请求幂等不等于绕过当前认证：
旧 launch 成功回执、撤销回执和查询都不能由已到期身份重新读取。返回错误的
优先级可能由业务拒绝变为 unauthenticated，这是失效身份在共同边界被拒绝的结果。

邀请凭据是独立已批准能力，不是 ambient enrolled 身份的别名；其 session.join
分支继续执行原邀请/Grant/消费检查，不因另一个 agent-identity 到期而隐式级联。
这不表示邀请永不过期，只表示不能把两份独立凭据的生命周期混成一个开关。

## 验证范围

五个新测试方法覆盖到期玩家不能启动或撤销、缓存结果不可绕过认证、过期 agent
不能读取描述/offer、严格期限类型与等号边界、可选字段兼容，以及独立邀请继续
遵守原合同。本轮不改变公开 schema，不新增认证服务，不证明凭据撤销列表或真实
身份根轮换已完成。
