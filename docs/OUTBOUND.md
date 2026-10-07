# 出站轮询桥接实验绑定

标识：`outbound-poll`，适用 `0.1.0-dev`。这是可自行部署的传输参考，不是必须连接的 Mot/G2A 中心服务。它不替代用户同意、提供者身份认证或跨应用发现；当前服务器只绑定回环地址，不能直接用作公网生产服务。

## 拓扑与信任

```text
游戏进程 ──主动拉取/回包──> 可信桥接 <──主动请求── 伙伴进程
  世界权威                   有界邮箱              会话客户端
  不监听端口
```

游戏与伙伴均主动连接同一个桥接 origin。桥接维护一个已配对游戏的邮箱，不提供匿名建箱、URL 转发、执行命令或模块加载接口。生产部署可由游戏、伙伴提供者或用户自行运行，不要求 Mot 账号。

**桥接是可信的明文终点，不是端到端加密中继。** 它能读取经它转发的邀请、会话凭据、观察和聊天，持会话凭据即可冒充相应伙伴；不得将它描述为无法访问私人消息。TLS 保护每一段传输，不能消除对桥接运营者的信任。双方通过可信控制面选择 origin 并分别获得独立随机凭据；这个控制面和跨供应商委托尚未实现。

- `game_token`：仅领取和回复邮箱请求。
- `agent_token`：仅提交伙伴操作；不能领取请求或伪造回复。
- 内层邀请/会话令牌：仍由游戏检查身份、权限、参与者和租约。桥接凭据不授予加入游戏的权限。
- 游戏管理员令牌：只留在游戏进程。即使被误送入桥接，游戏分派器也拒绝；不开放 claim 等游戏管理操作。

## Wire 定义

权威结构为 `src/g2a/schema.json` 的 `bridge_call`、`bridge_batch`、`bridge_reply`，JavaScript 副本从该文件生成。游戏 descriptor 的 `bindings` 可声明 `http-poll`、`outbound-poll` 或两者，不能把未提供的监听服务标成可用。

| HTTP 操作 | 外层 Bearer | 请求/返回 |
| --- | --- | --- |
| `POST /bridge/call` | `agent_token` | 提交 `bridge_call`，等待游戏结果；返回原协议数据或错误 |
| `GET /bridge/pull` | `game_token` | 返回 `bridge_batch`，每页至多一个请求 |
| `POST /bridge/reply` | `game_token` | 提交 `bridge_reply`；成功返回 `{"accepted":true}` |

`bridge_call` 为 `{"operation":"…","arguments":{…},"credential":"…"}`：

| operation | arguments | 内层 credential |
| --- | --- | --- |
| `describe` | `{}` | 空字符串 |
| `join` | `{"request":加入请求}` | 邀请 |
| `poll` | `{"session_id":"…","cursor":0}` | 会话令牌 |
| `send` | `{"session_id":"…","message":协议消息}` | 会话令牌 |
| `leave` | `{"session_id":"…","reason":"…"}` | 会话令牌 |
| `action` | `{"session_id":"…","request_id":"…"}` | 会话令牌 |

邮箱生成独立请求 ID，领取结果为 `{"requests":[{"id":"…","command":bridge_call}]}`。游戏返回 `{"id":"…","status":200,"result":原协议响应}`；失败 status 仅允许 400–599，result 必须为原协议错误对象。禁止 3xx 和任意 URL，因此桥接不能诱使客户端重定向并发送令牌。

该封装不改变 message ID、事件 cursor、行动权限、来源或呈现租约。`BridgeClient` 复用原客户端的 join/poll/send/leave 校验；游戏仍用 `GameHost` 执行协议操作，世界效果由游戏执行器负责。

## 大小、断线与撤销

- 默认同时最多 32 个请求，可配置 1–64。每个请求默认等待 2 秒，可配置大于 0 且不超过 3 秒；满额返回 429 `resource_limit`。
- call 请求体上限 128 KiB，reply 上限 264 KiB，包含封装开销；协议消息仍受原 64 KiB 上限约束，客户端结果上限仍为 256 KiB。这样不会把原本可返回的约 128 KiB 事件页误截为 64 KiB。
- 游戏只领取一次，不自动再次投递。请求超时从邮箱移除；已领取但未回包返回 504 `bridge_timeout`，含义是**结果未知**，不是未执行或执行失败。迟到/重复回复返回 409 `request_gone`。
- 短暂网络错误后，`OutboundGame.run` 继续领取后续请求，不自动重做已领取操作。若回包丢失，伙伴可查询原 action ID；在原会话仍有效时重发相同 message ID/内容使用原幂等收据，不能为“重试”生成新的动作 ID。
- 撤销邮箱会唤醒等待者并返回 410 `bridge_closed`，旧外层令牌不能恢复邮箱。撤销不伪造游戏世界回滚或立刻终止全部游戏会话；会话由明确退出或原租约到期关闭。
- 客户端传输失败不续租，原来的 `check_lease`/`checkLease` 仍需由集成层定期调用。状态值恢复不等于已证明跨进程桌面窗口恢复。

参考服务有消息/邮箱限制，但没有生产请求线程池、速率限制、持久化、跨进程恰好一次或高可用保证。进程重启丢失邮箱和宿主状态，必须重新配对。不要将内存版本直接暴露到不可信互联网。

## 运行与验证

安装 Python 包与 JavaScript 依赖后，在仓库根目录运行：

```sh
python examples/outbound_demo.py
python -m unittest discover -s tests -p 'test_bridge*.py' -v
```

演示由桥接/可信启动器启动独立 Python 游戏和 Node 伙伴两个子进程。游戏进程安装审计钩子，禁止调用 `socket.bind`；如果试图监听，示例失败。三个进程通过真实 HTTP 完成观察、主动队聊、请求行动、去重、越权拒绝、世界结果和退出。令牌仅通过匿名管道交付，不写到参数或演示输出。该确定性游戏不是 Godot 渲染示例，也没有新增用户授权 UI。

TLS 测试通过 OpenSSL 现场生成一次性证书，验证受信证书成功、自签未信任证书失败、主机名不匹配失败。可用 `G2A_OPENSSL` 指定 OpenSSL，`G2A_TEST_OUTPUT` 指定临时输出根；无工具会明确跳过，CI 要求工具存在。Python 客户端允许显式受信 CA context，不默认关闭证书校验；JavaScript 使用 Node 的正常 TLS 信任链。

当前证据是本机回环跨进程互通和回环 TLS，并非云服务器部署、NAT/防火墙实测或公网负载验证。跨应用配对认证、云端提供者选择/授权、持久身份与记忆、生产资源管理仍属于完整目标的未完成项。
