# 可执行 SDK：游戏本地感知与行动约束

本页描述当前 Python 参考宿主的**可选本地策略**，不是新协议版本，不是 `g2a-design-1` 的生产实现，也不新增 wire 字段。

## 接入边界

游戏仍通过现有 descriptor 声明 action，通过 invitation 和 join 确定允许的 action 名集合。可在可信游戏代码调用 `GameHost.invite(..., action_constraints={动作名: JSON Schema})`，进一步限制本次邀请可用的参数。这里的约束只能缩小权限，不能声明新能力或代替玩家批准。未传参数时保持旧行为。

例如，同一个游戏支持多个房间，但当前伙伴只允许观察大厅：

```python
invitation = host.invite(
    "fox", "alice", allowed_actions=["observe"],
    action_constraints={"observe": {"properties": {"room": {"const": "hall"}}}},
)
```

这不是可供 Agent 自授的 HTTP 接口。约束复制后绑定邀请/会话，不因调用方之后修改字典而扩大。JSON Schema 不解析任何 `$ref` 或 `$dynamicRef`。宿主在接收 action.request 和执行器领取前都检查约束；前者返回既有 `permission_denied`，后者返回既有 `not_executable`，不新增错误码。

无效 schema、非法正则、非有限 JSON 或针对未获准动作的约束在创建邀请前拒绝；收窄失败不替换原策略。不要在不支持此可选 API 的旧宿主上捕获参数错误后丢弃约束重试，否则会扩大实际授权。集成方应固定/检测所用 SDK API，缺失则停止该受限接入。当前 wire 不协商这个本地功能，远端 join 注入同名字段仍被 schema 拒绝。

可信游戏代码可以调用 `host.restrict_action(session_id, "observe", False)` 停止该会话后续观察，或提供一个新参数约束进一步收窄。新旧约束相交，不能用该方法扩大权限。已接收但未领取的请求也被拦截；已经领取的效果不会凭空回滚，实际引擎仍必须在效果边界检查世界状态。授权扩展需走新的用户批准/邀请，不由本方法处理。

## 为什么它不是完整感知协议

这个闭环使用现有 action 机制实现按需 `observe`，没有宣称建立新的观察订阅、分层可见性 schema 或跨语言授权声明。旧客户端可原样使用，游戏本地策略的细节不在当前 wire 暴露，伙伴可能收到合法拒绝，而不能假定 descriptor 等同于本次玩家授权。若要让不同实现协商、展示和持久恢复这些细粒度授权，需要在后续标准中正式定义，不把 Python 方法当作公开协议。

信息安全首先由游戏决定输出。示例只从世界对象选择 `visible_items`，**不会先发送隐藏世界状态再要求模型不说出来**。`GameHost.send(game.context, ...)` 和 action.result 仍是可信游戏端主动披露接口；本功能不是自动内容脱敏器，也不保证宿主不会误发私有信息。角色权限矩阵不会替游戏挑选感知视图。

## 运行和验证

使用 Python 3.11+，安装本包后：

```sh
python examples/scoped_observation.py
python -m unittest discover -s tests -p test_action_policy.py -v
```

示例是当前可安装 SDK 和真实回环 HTTP，不导入 `docs/protocol` 的模型/harness。游戏保留大厅隐藏陷阱和保险库状态；伙伴只得到大厅可见物品，可以拿大厅钥匙，不能观察或操作保险库。随后收紧观察授权，已排队请求无法领取。它不使用模型、真实账号或游戏引擎，也不证明独立厂商互通、生产持久化或远程部署安全。
