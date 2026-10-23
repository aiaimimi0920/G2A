# 现有 Relay 的固定代次 profile 接入

## 位置与兼容边界

RelayHarness 现在支持可信端点配置显式启用 relay_epoch_profile。未启用时保持原
mailbox-N 标识和全部旧行为；启用时使用同一 OperationRequest、五个 Relay 操作
及通用 Relay 撤销分支，不另造一组业务操作。

这不是完整动态轮换：本轮接入的是**固定代次的身份边界、请求拒绝与字节链**。
此检查点尚未编排封存/切换/归档；后续已在独立子类组合，见
[动态轮换证明](RELAY_ROTATION_PROOF.md)。现有 8 邮箱容量不变，不能通过重建 Harness
或修改配置当作合法在线轮换。

## 显式冻结扩展

启用 profile 的端点要求所有外层 Relay 请求携带以下扩展：

```json
{"g2a.relay-epoch":{"version":"1","required":true,"value":{
  "profile":"g2a-relay-epoch-1","epoch":0,
  "instance":{"game":{"issuer":"fixture","subject":"game","kind":"game"},"instance_id":"instance-1","epoch":"game-1"},
  "relay_identity":{"issuer":"fixture","subject":"relay","kind":"service"},
  "relay_origin":"https://relay.fixture.invalid"
}}}
```

上例使用示例身份，Instance/Principal 使用既有合同对象。本地实现由已验证
fixture 配置冻结完整值，沿用 validate_active_request 的精确规范化比对，不把 value
用作可随请求变化的动态载荷。这里的 epoch 是 Relay 路由代次，不是游戏 Instance.epoch。

缺少 required 扩展返回 feature_unsupported；改 epoch、实例、operator、origin、
版本或 required 标记返回 approval_stale。请求不能自行升级/降级当前端点。
旧端点收到该 required 扩展会拒绝，而非忽略它继续执行。

可信配对登记还必须独立把 pairing_proof_ref 绑定到相同 route epoch；只在请求里
声称 epoch 不构成玩家同意。模型使用 relay_pairing_epochs 可信索引，缺失、错代次
及 bool 混淆均拒绝。真实适配器需将此绑定纳入认证过的配对证据，不能从请求复制。

## 身份与游戏端口

mailbox ID 变为 mailbox-e{epoch}-{local_id}，沿用 Id 的不透明语义；凭据按完整 ID
交付。固定 profile 的游戏端口也检查同一命名空间，拒绝另一代次或非规范编号的
claim 后才可能读取 journal/执行游戏，不能仅依赖 Relay 外层检查。

完整假账本重启保留 profile、命名空间和 port route_epoch；原注册请求提交后丢
响应可恢复原回执，但缺失扩展的重试仍拒绝。游戏内层请求不继承此 Relay 专用扩展，
其 Scope/Grant/角色/结果权限保持原合同，不因外层 profile 改变。

此 profile 的身份扩展不是可选处理器。包括 relay.revoke 和 permission.revoke(relay)
在内都必须携带完整绑定，不使用普通空扩展止损豁免去跨身份边界。旧默认 profile 的
止损行为不变；启用新 profile 前必须确认调用者能构造该绑定。自动协商与失配时的
运维处置仍待正式部署合同，不假称已有客户端兼容。

## 证据

新增九个 Python 场景覆盖五操作完整链、缺失/降级/错字段拒绝、旧端点拒绝 required
扩展、通用撤销、游戏端口跨代次拒绝、提交故障重启、严格配置及配对独立绑定。

JS/Python 在现有 Relay 字节入口实际增加九次 wire 调用，跑过 register→call→pull→
真实模型 dispatch→reply→重启缓存读取→revoke，含缺失扩展和错代次拒绝。原操作数
仍为 38，总 wire 调用增至 371；独立候选 binding profile 的 26 次仍另计。

此结果不证明动态迁移、旧回执归档接入、真实认证/持久数据库/网络或第三方互通完成。
