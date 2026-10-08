# 单步动作的有界时序验证

本文件承接 [研究台账](PROTOCOL_RESEARCH.md) 的效果与撤权交错问题。
实现复用 flow_model.py，不新增生产引擎、SDK 或线程调度器。

## 1. 实际发现与修复

新增测试先在原模型运行，实际得到一个断言失败与一个异常：

1. `effect` 已产生并记录 committed 世界事实，但 result 尚未上报时，query 仍得到
   executing/none。现在 effect 成功时立即记录 committed；执行状态仍可保持 executing，
   等待终态汇总。效果知识与工作流程是否结束是两个不同维度。
2. `result(ticket, None)` 在尚无世界事实时通过 `None == None` 比较，随后出现 TypeError。
   现在要求已有非空事实且报告为字典并精确匹配，否则 unproven_result，不改变动作记录。

这两项是模型实现与原 DATA_PLANE §6–7 契约之间的偏差，不是新增世界效果保证。

## 2. 有界枚举的准确范围

[test_design_action_orders.py](../../tests/test_design_action_orders.py) 枚举：

- 前态固定为一个已批准、已加入、已接受但尚未领取的 find-key 动作。
- 操作标签为 claim、effect、result、barrier、retry，共 5! = 120 种顺序。
- barrier 分别为授权撤销、取消、能力变更、控制恢复升代、动作期限到达、持久账本下传输重启。
- 合计 6 × 120 = 720 个调度。
- retry 是使用原 ticket 再查/调用同一步，不是换新请求 ID。

尚无 ticket 的 effect/retry、尚无事实的 result 被标为不可执行而跳过；因此 720 是有界
调度数，不能称为 720 条全部成功的业务流程。预期拒绝仅允许明确的状态/代次错误，
其他错误或 Python 异常不能被当作成功拒绝吞掉。

每一步都断言：总效果最多一次；屏障之后不增加效果；succeeded 必有一个 committed 效果；
本模型 pending→cancelled/none 不得对应已发生效果。已消费且有事实的 step 在屏障后
可返回原事实，但不能产生第二次效果。

## 3. 不让安全性测试变成“全部拒绝也通过”

另有独立正例实际执行 claim→effect→revoke→result，验证已经产生的事实可由原 ticket
在撤权后完成对账，重复上报不新增效果。不能因为撤权就拒收历史事实并永久保持 unknown。
也验证在终态汇总前查询已知效果，以及 uncertain 消费后连续重试始终 outcome_unknown。

模型 uncertain 路径的 effects 计数为 0 仅表示没有可证明的成功计数，不代表现实世界
肯定没发生效果；对外仍是 unknown/undetermined，禁止根据该计数自动重执行。

## 4. 证据与边界

本轮新增 5 个测试方法，统一检查累计 96 个方法通过，0 失败/错误/跳过；原 42 条模型
重放通过。720 个参数调度不与方法数或原重放数相加。回执保存于 linshi 下
g2a-protocol-design-20261007/action-orders-verification.json，含修改后的模型 hash。

仍未证明：接受请求与撤权之间的多进程竞争、真正非事务引擎的崩溃窗口、多步动作、
多个并发执行器、持久化存储重启与真实网络投递。枚举从已接受动作开始，不涵盖 accept
自身的交错。原模型方法是可信路由后的抽象调用，不是 raw bytes 动作入口。

人工复核关注点：是否接受“已知 committed 效果、执行状态尚未终结”的正交表示；
是否保持“撤权阻止新效果，但不阻止可信历史事实对账”的规则。本次按上述保守语义实现。
