# 代次凭据登记表与原 owner 的联合恢复校验

## 恢复合同

EpochBoundPort 现在具有独立可信 checkpoint，覆盖 authority、instance_id、epoch、
token 登记表及 mailbox 原 owner 映射。可信发行、注册和代次切换清理后更新该锚点。
候选快照不包含可覆盖锚点的字段；散列依据不能从待验证快照自行重建。

恢复顺序如下：

1. 通过 EpochRotation 原有 checkpoint 校验恢复代次模型，退休旧模型。
2. 将凭据候选快照交给旧绑定端口的可信恢复入口 `restart(restored_model, snapshot=...)`。
3. 先验证旧端口尚未完成恢复、旧模型已退休、新模型健康且实例一致。
4. 凭据状态必须匹配旧端口独立保存的最新 checkpoint；候选中关联的模型 checkpoint
   必须匹配新模型的最新锚点，且新模型的实际状态也必须匹配其锚点。
5. 候选 epoch 必须等于新 Relay epoch，原 owner 映射必须覆盖且仅覆盖当前 mailbox。
6. 全部通过后复制 token 与 owner 到新端口，并退休旧端口；失败不消费后续正确恢复机会。

绑定快照与代次快照需要是同一可核验状态，而非随意拼接。即使凭据表没有变化，若
期间发生新派发标记，也必须使用对应更新的模型 checkpoint，避免恢复后忘记未决请求。

## 授权语义保持

成功恢复不重新授权：旧 controller 仍是原 owner，agent 不变成 controller；关闭
mailbox 不重新开放；已消费 pairing 不再消费；旧请求去重与未决 inflight 继续生效。
新代次完成后已清理的旧 token 不能从旧快照恢复，也不允许把其 epoch 重标记为当前值。
直接构造空登记表的新端口仍拒绝旧 token，与经过检查点验证的恢复是不同路径。

## 信任和持久化边界

snapshot 含 token，是可信内部恢复材料，不可通过公开 binding_bytes、日志或客户端
wire 返回。测试只用内存 fixture token，不把真实凭据写入协议交付文件。

凭据 checkpoint 独立于候选快照；缺失时 fail-closed。若锚点与快照一起被回滚，当前
模型不能检测。模型用同一内存锁表示发行/登记与锚点更新的提交边界，不证明数据库
跨表事务、掉电一致性或认证密钥存储安全。登记表与 owner 恢复仍未接入现有 Relay wire。

## 证据

新增七个场景验证：旧 token 与原 owner 恢复、旧登记表快照拒绝、owner/角色/token
篡改拒绝、模型 checkpoint 时点不匹配、关闭和消费事实保留、异实例/不健康/缺锚点
拒绝、代次切换后旧凭据不得复活。拒绝之后仍可尝试正确快照，成功后旧恢复入口不能再次使用。
