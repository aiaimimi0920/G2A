# 启动许可的独立撤销

## 公共合同扩展

permission.revoke 的 object_type 新增 launch_permission，object_id 为批准交互的
launch_permission_ref（即对应 decision_ref），初始 expected_revision 为 1。
只允许原所属玩家，不能由 agent 或 game 管理身份代撤。复用既有控制回执幂等、
CAS、提交故障与 operation.get 查询，不新增第 39 个操作。

许可记录独立保存 state/revision。首次撤销改为 revoked、revision=2；旧请求按
原回执返回；新请求若使用过时代次拒绝，当前代次重复撤销不再增加 revision。
该许可不可重新激活，新启动意图需要新的明确同意。

## 派发边界与不级联原则

| 撤销时点 | 必须保留的知识与效果 |
| --- | --- |
| launch.request 尚未受理 | 授权拒绝，不产生启动记录/效果 |
| 已受理但未标派发 | 重试时再次检查许可，记录已受理失败，不调用 start |
| 已标派发、独立端口无确定事实 | 保持 unknown，不重复 start，不把撤销当作未执行证据 |
| 独立启动效果已发生 | 保留原成功事实和效果，不停止进程、不抹掉回执 |
| 会话已经加入或 ready | 只撤销启动许可，不关闭既有会话或撤销独立 Grant |

许可撤销本身不级联接入 Grant。特别是“受理后、派发前”因许可撤销失败，内部
failure_reason 明确区分 launch_permission_revoked，不走普通启动失败的 Grant
撤销路径。实际应用启动失败仍沿用原有准入失败规则，不借此变更无关行为。

## 兼容与恢复

这是草案的增量枚举值，旧 peer/schema 必须拒绝未知值，不能忽略，也不能退化成
grant/session 撤销。其余 object_type 的结构与行为保留。公开 schema 与操作目录
由 contracts.py 同步生成；新旧协议包混用不是受支持的生产迁移路径。

当前假账本重启保留新 permit 状态和撤销回执。生产旧快照若缺少状态/revision，
不能自动补 active 来恢复启动权，必须按原可信记录显式迁移或保守拒绝；本轮没有
迁移真实存储、回滚部署或删除旧数据。若回退至旧 peer，客户端应停止发送新分支，
不能清掉已提交撤销记录后继续启动。

## 验证边界

七个 Python 场景覆盖受理前/后、派发后 unknown、效果后保留、撤销提交前后故障及
假重启、operation.get、角色/CAS/对象拒绝和已加入会话保持不变。
JS/Python 新增 16 次正式 wire 请求，实际覆盖 after_accept 和 after_effect 两端，
含撤销提交后丢响应、重启、重复请求、查证及独立效果计数。互通门禁要求这两端
的独立子报告，正式操作仍为 38 项，总 wire 请求为 437 次。

运行进程的精确观察已由后续 [进程监视模型](LAUNCH_PROCESS_MONITOR_PROOF.md) 补充；
真实 OS 取消、许可/效果账本长期回收、多应用和跨 authority 撤权仍未证明。
撤销成功不等于应用已停止，也不等于撤回已经产生的效果。
