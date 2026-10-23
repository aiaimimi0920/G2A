# Relay 内层 proof 与底层身份有效期交集

## 已复现的问题

原 RelayGamePort.verify 校验了 proof 的状态、issued_at/expires_at、实例、audience、
角色与主体，却遗漏其所引用 enrolled 身份凭据的 expires_at。游戏准入层的
operation.get 已检查该字段，因此原 Relay 查证维护路径存在不一致：底层 reader
身份已到期，只要 proof 仍有效，就可能继续查证并解除未知派发阻断。

新增回归先在旧代码实际得到 `AssertionError: ContractError not raised`，确认
不是仅凭静态猜测。修复放在公共 verify 入口，不分别放宽或重写每个查证方法。

## 修复后的规则

有 expires_at 的底层身份必须满足严格整数类型且 now < expires_at；到期边界、
布尔值、字符串或空值均返回 unauthenticated。没有该可选字段的既有身份保持原
合同行为。此规则与准入 operation.get 的现有身份期限检查一致。

proof 的有效期不能延长底层凭据的有效期；身份期限也不能延长 proof。当前请求
必须同时满足两层期限和原主体/角色绑定。真实续权必须来自可信身份登记，不能
由客户端改 proof 的 expires_at 达成。

## 与结果保留期的关系

结果尚在保留期内不等于旧凭据仍然有效。原 action 保留期测试中，旧 reader 已早于
read_until 到期；现在用可信夹具登记新的同主体 reader 后，才隔离验证结果保留期
的等号/越界行为。该新 reader 仍服从原成员代次和结果撤权，不能恢复被撤销读权。

四个新增测试方法覆盖：外层 proof 有效但底层 reader 已到期时 action 查证拒绝；
严格 expiry 类型与边界、无期限身份兼容；准入和会话控制查证保留未知阻断；
排队之后底层身份到期，在实际派发前重新校验并拒绝，不创建 journal 或派发见证。

此修复不声称完成所有身份生命周期：独立凭据撤销/轮换与真实身份服务集成仍需
各自证据。它没有新增公开操作或生产认证系统。
