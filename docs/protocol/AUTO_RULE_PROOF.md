# 自动批准规则、独立撤销与启动隔离

本工作包将既有 `offer.decide(remember=true)` 和 `permission.revoke(auto_rule)` 的合同
装配到准入内存模型，保留 38 个公开操作。没有添加服务、真实认证、数据库或批准 UI。

## 调研与设计取舍

2026-10-23 联网核对了两份 RFC 原文：

- [RFC 9396 §6.1](https://www.rfc-editor.org/rfc/rfc9396.html#section-6.1)：权限详情的
  比较依赖具体 API 语义，不能用通用对象包含关系推断权限子集。G2A 沿用既定严格匹配，
  不实现隐式子集复用；这不是声称遵循了某个通用 OAuth 规则匹配算法。
- [RFC 7009 §2.1](https://www.rfc-editor.org/rfc/rfc7009.html#section-2.1)：撤销传播及
  关联对象的失效需要明确策略。G2A 的 auto_rule 是未来批准策略，不是 OAuth token；
  本协议明确选择不级联已签发 Grant/邀请/Session，而不是套用 token 撤销的全部行为。

实际代码审查发现三个装配缺口：规则期限字段已有 schema，但 `remember` 一律拒绝；
规则没有可供玩家撤销的返回标识；LaunchHarness 在基类 `_create` 返回后才设置
`launch_required`。因此自动匹配放在完整派生 `_create` 返回之后，不能在基类提前批准。

## 规则创建与公开引用

`offer.decide` 继续要求可信 Consent 证据与完整 payload 的规范字节一致。
`remember=true` 时，规则的独立 `rule_expires_at` 必须晚于当前可信时间，
`maximum_grant_duration_ms` 必须为正且不超过此次冻结 Scope 的完整授权时长。
此限制只约束未来复用上限，不把规则期限当作第一次显式批准的 Grant 到期时间。

规则、原 consent 引用、批准的 Grant、Offer 和控制回执同事务保存。规则含 ID、revision、
active/revoked 状态、玩家、匹配摘要、时长上限、到期时间及可信本地上下文。最多 16 条；
不清除旧规则来复用 ID，不实现无限历史或长期 GC。

OfferView 增加可选 `auto_rule: {rule_id, revision}`，表示原批准创建/使用的规则版本。
这只是无秘密的历史引用，不是规则当前状态、撤权凭据或全部规则列表。双方原本可读取
同一 Offer；原 consent 证据和本地应用路径不放进该视图。撤销后旧 Offer/operation.get
仍报告原批准事实，不能把历史 revision 1 当作规则仍 active 的证明。

## 自动匹配与时间边界

`offer.create` 冻结 Scope 后，仅执行一次规则匹配。键使用既有 `auto-rule` 摘要域：

```text
digest("auto-rule", {
  scope_without_timestamps: Scope minus created_at and expires_at,
  maximum_grant_duration_ms: explicit maximum
})
```

规则保存时 explicit maximum 来自玩家的决定；未来申请匹配时来自 Requested。
所以玩家将规则上限设为 100000，而未来申请仍请求 300000 时，不命中；必须明确请求
100000 才可能命中。身份及 issuer、实例 epoch、descriptor revision、绑定、隐私、
能力摘要、受众、有效策略和限额都在键内，即使权限收缩也重新批准。

命中还须满足当前规则 active、未到期、Scope 当前仍合法、整个 Grant 不超过规则剩余
有效期及最大时长。Grant 到期等于规则到期可接受；当前时刻等于规则到期则不可接受。
不为命中而偷偷缩短已冻结 Scope。无匹配时正常返回 pending，交显式批准，不报假成功。

自动批准创建独立的新 Grant，引用原 consent 证据；不重复消费原玩家决定，也不产生
新的虚构 UI 证明。规则选择与撤销在同一 authority 锁/事务域：若批准先提交，撤销不
回滚新 Grant；若撤销先提交，后续 Offer 保持 pending。读操作和原请求重试都不重新
尝试批准，避免后来新增规则使原 pending 请求悄悄获得副作用。

## 对象撤销与幂等

- `permission.revoke(auto_rule)` 仅所属玩家可调用，GameAuthority 不能代玩家取消偏好；
  `expected_revision` 使用规则自身 revision，不混用 Grant 或 capabilities revision。
- 撤销只禁用该规则，不撤销已签发 Grant、邀请或已建立会话，也不取消已单独批准的
  启动许可。反过来，撤销一个 Grant 也不自动删除未来规则。
- 同 ID 原文重试返回原回执；改文冲突；新 ID 用旧 revision 拒绝。重放原 remember
  决定只读原完成事实，不能重新创建/复活旧规则。新的真实批准可创建新规则 ID。
- 多条独立批准的规则可能匹配同一范围；撤销一个对象不代表批量撤销其他对象。
  当前按保存顺序确定命中的规则，无规则列表/批量撤销 UI 或跨 authority 广播。
- 原玩家可经 operation.get 查询撤销回执，伙伴不可读取；与会话层 capability 等
  撤销共享跨层 request_id 冲突检查，不能换对象类型绕过拒重。

## 启动和本地应用隔离

本地 `remember` 证据必须额外精确绑定可信 Launcher 注册记录，包括应用、程序/参数、
revision 和设备；未来匹配还比较此上下文的规范字节。注册变化或设备变化即不命中。
自动批准只在应用已验证运行、`launch_required=false` 时发生。

`remember` 不生成 launch_permit，也不调用 Launcher。玩家可在一次明确决定里分别
授予 remember 和 launch_permission，两者记录同事务，但撤销语义保持独立。
不把基类的“默认无需启动”误用于派生本地场景，也不授权自动 handoff。

## 执行证据与停止条件

[test_design_auto_rules.py](../../tests/test_design_auto_rules.py) 新增 24 个方法：两入口、
严格匹配/时长/期限、显式证据、Grant/邀请/Session 保留、对象读权、三类提交故障、
旧 consent 重放、双线程创建/撤销、内存复制/控制器重启、本地启动分离和跨层 ID 冲突。
初版 17 个方法在实现前实际出现 16 个错误、3 个子例失败，主要为尚不支持 remember；
不是生产漏洞或对已上线服务的测试。

独立 JS 客户端增加 22 次 wire 调用，实际覆盖记住批准、自动批准、撤销、玩家查询、
伙伴/游戏拒绝、丢回包重试、旧邀请加入和上一包 capability 撤销/定义更新不复活。
互通预期 23 组编码、38 项操作、350 次 wire；本包总设计测试预期 561 个，原轨迹 42 条。

完整证据位于 `C:/Users/Public/nas_home/AI/GameEditor/linshi/g2a-auto-rules-20261023/`：
`red.log`、`interop.json`、`final-verification.json`。最终通过状态以回执为准。

停止条件是规则批准/撤销、启动隔离、已签发对象保护、重放/故障和完整回归通过。
不证明真实 UI/持久数据库、身份根轮换、规则管理产品、多会话接入、动态策略或全部调度；
旧 SDK 未升级，g2a-design-1 仍是可变工作草案，不是兼容稳定版本。
