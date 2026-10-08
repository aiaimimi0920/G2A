# 最小 core 配置的准入与数据面

本工作包只验证 `core.session` 与 `core.events`，不新增公开操作、网络服务或游戏适配器。
描述、请求和批准 Scope 均不启用 actions、resume、handoff、presentation 或 assets。

## 反例与修复

旧 core fixture 总是附带一个未启用的 `action` 定义，掩盖了 EventServer 与 ActionHarness
对该夹具字段的直接索引。移除虚构动作后，两种入口都在 session.join 装配时抛出
`KeyError: 'action'`；即使协商结果没有动作，最小会话也无法启动。

现在无动作授权的模型允许缺少该内部字段，快照 definitions/actions 保持空；动作字节
入口仍经 feature 授权检查拒绝，不因为保留内部空动作模型就取得执行能力。
若 Scope 启用 actions 却没有固定模型定义，初始化明确报 invalid_arguments；即使当前
action_ids 为空，也不允许进入未定义的动作模型分支。这是固定模型的配置限制，不静默
忽略授权或虚构动作实现。当前固定单动作限制未改变，也未放宽任何公开 schema。

## 已执行的路径

[test_design_minimal_core.py](../../tests/test_design_minimal_core.py) 新增 7 个方法：

- companion/game 两入口从批准、邀请、join_pending 到 ready，再聊天、重复消息去重、事件、心跳和关闭。
- 直接构建最小 SessionHarness，不提供 action 字段，输出空动作定义。
- 未协商 action.request/action.query/capability.replace 拒绝且不修改会话状态。
- 未协商 resume/handoff 拒绝且不修改会话状态。
- join 的 before_commit 回滚不消费邀请、不留下部分会话，重试可到 ready。
- 描述支持 actions、请求只选择 core 时，不需要提供未批准动作的内部定义。
- 已批准动作的配置缺少定义时明确拒绝。

JS 客户端另行手写最小 core 路径：describe、批准、邀请、两次 join、快照、聊天去重、
事件读取、动作/能力拒绝、关闭及原 join 完成事实查询。服务端只增加可信夹具启动选项，
不是新增 wire 配置字段；客户端不导入 Python fixture 或 schema 生成器。

## 证据与停止条件

完整设计测试预期累计 517 个，42 条原模型轨迹不变；跨语言仍覆盖 38 个操作，增加
14 次最小 core wire 调用，总计 326 次。最终数量与通过状态以回执为准。
回执位于 `C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-protocol-design-20261007/`：

- `minimal-core-red.log`：修复前缺少 action 的异常，包含两种入口的子用例。
- `minimal-core-final-verification.json`：完整设计测试、生成检查、轨迹与跨语言验证。
- `minimal-core-final-hygiene.json`：源哈希、编码、AST、链接与语法检查。

以无虚构动作的 core 正常生命周期、未协商能力拒绝、准入故障回滚和匹配回归通过为
停止条件。未穷尽可选功能组合，不替代长期回收、多动作/多会话、真实端口或第三方互通。
