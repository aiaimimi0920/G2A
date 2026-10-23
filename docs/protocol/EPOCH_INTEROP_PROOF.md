# 候选代次 profile 的 JavaScript/Python 字节互通

## 本轮交付

`epoch_binding_peer.mjs` 是手写 JavaScript 校验与客户端，不导入 Python schema。
它通过现有子进程管道与 `epoch_interop_fixture.py` 交换实际规范化字节；Python 端
调用 EpochBoundPort 和 EpochRotation，不以静态预期响应替代状态变化。

JS 独立检查字段全集、profile 版本、严格整数、字符串标识、pairing/mailbox 形状、
角色、接收方预期 instance/authority/epoch/principal，并检查 Python 公开绑定不含
token。请求绑定由 JS 重新规范化编码，Python 做可信登记比对，回复由 JS 校验规范化
与 request_id 关联。凭据只使用 fixture token，不接网络认证服务。

## 已验证链路

后续 [回执归档增量](EPOCH_RECEIPT_PROOF.md) 将本链扩展为 26 次候选字节请求、51 次
夹具命令；下面 21/43 为初始交付记录。门禁已要求新归档场景实际运行。

21 次候选 profile 字节请求、43 次夹具命令，包括：

- 配对→注册→分别交付 controller/agent/game 绑定；
- 缺 epoch、bool 数字、未知版本、额外字段，JS 与 Python 分别拒绝；
- authority/instance/mailbox/principal/role 改写，Python 按 token 完整证据拒绝；
- agent 关闭、game 领取和配对重复消费拒绝；
- 原 claim 已开始→模型与凭据共同恢复→原请求再次领取仍不得二次执行→原效果完成；
- controller 关闭→封存→游戏切换后丢响应→假重启→切换间隙拒绝新配对；
- Relay 切换前故障→原目标重试→旧 token 与改 epoch 后的旧 token 均拒绝；
- 新代次注册复用局部编号 1，但完整身份是 [1,1]，新请求可执行，旧 claim 仍拒绝。

最终两个 authority epoch 均为 1，效果总数为 2，inflight 为零。夹具 begin/finish、
发行、维护和恢复命令是可信模型端口，不计为新增公开 G2A 操作。

## 门禁与计数

verify_design_interop.py 明确检查 epoch_binding 子报告。旧客户端只有总 passed、
缺少新 profile、调用数不足或代次/效果不符时不能放行。三个 Python 门禁测试覆盖
这些拒绝路径。调用数只是防止漏跑的辅助证据，语义由独立 JS 断言与 Python 状态机验证。

原 38 个正式操作与 362 次 wire 调用继续单独统计。候选 profile 的 21 次字节请求
不冒充第 39 项正式操作；回复封装仅为本地夹具关联格式，不宣称新的正式 transport。

## 尚未证明

同作者的两种语言实现不是第三方认证。未实现真实 HTTP/TLS、持久认证表、数据库
崩溃恢复、pull/reply 和旧回执归档，也未接入现有 RelayHarness。现有 8 邮箱限制
不因此解除。正式接入仍需版本协商、归档查询与权限生命周期的合同及组合验证。
