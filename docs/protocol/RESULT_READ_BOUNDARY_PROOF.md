# 动作结果两个读取入口的成员代次边界

本包是回执汇总之后的窄范围反例修复，不新增公开操作、生产适配器或 player 结果读取配置。

## 实际反例

`operation.get` 已对动作原成员代次重新授权，而 `action.query` 原先仅检查原 agent、
本地读权撤销标志与保留期。经 `membership.replace` 的可信管理字节入口移除 agent，
或移除后重新加入为 generation=2，旧控制凭据及独立 result_read_handle 仍能读到原动作。
这不是控制权续期问题：独立结果读权允许关闭后读取，但不允许跨成员代次恢复历史访问。

新增测试修复前实际得到 4 个 `ContractError not raised` 失败断言，分别覆盖离开/重入与
控制凭据/只读句柄的组合；其余新增正常关闭、读权撤销与成员变更提交失败用例通过。

## 最小修复

[ActionHarness](action_harness.py) 中两个入口共用 `_authorize_result_reader`：原 agent、
本地及权威撤权记录、已接受动作的冻结成员代次、当前成员与 Scope 受众必须同时满足。
独立 ActionHarness 使用本地撤权标志；装配 EventServer 时再检查其细粒度撤权账本。
两入口保留各自原有保留期错误码与返回结构，不新增缓存、收据、执行或结果对账。

关闭会话不是成员离开：成员代次和独立读权仍有效时，原结果句柄仍可查询。
`membership.replace` 的 before_commit 故障回滚后，原成员和结果读权也必须保留。

## 验证与边界

[test_design_operation_status.py](../../tests/test_design_operation_status.py) 新增 5 个方法，
该文件共 34 个方法；完整设计测试累计预期 510 个。最终通过情况以回执为准。
沿用已有 JS/Python 38 操作/312 次 wire 的回归；新增成员反例由 Python 组合字节入口
验证，不宣称 JS 客户端也新增了成员反例。全部证据仍是固定身份、单动作内存模型。

回执目录：`C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/`。

- `result-read-boundary-red.log`：修复前 4 个失败断言。
- `result-read-boundary-final-verification.json`：完整测试、契约生成检查、42 条轨迹与跨语言回归。
- `result-read-boundary-final-hygiene.json`：当前源哈希匹配、UTF-8、AST、链接与语法检查。

本包停止条件是两个入口拒绝离开/重入的历史结果访问，保留关闭后合法读取和事务回滚，
且完整回归通过。长期回收、多动作、多会话、真实认证与第三方互通仍不在本包范围内。
