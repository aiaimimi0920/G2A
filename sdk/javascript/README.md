# G2A JavaScript 参考客户端

独立 Node.js 20+ 客户端，直接通过 HTTP 与游戏宿主通信，不依赖 Python 客户端、Mot 或模型。当前 `0.1.0-dev`，未发布到 npm，包标记 private，避免未经审核占用公开包名。

`client.mjs` 导出 `Client`、`ProtocolError` 和 `validate`。使用 Ajv 2020 校验权威 schema 的发布副本；`schema.json` 由仓库 `scripts/sync-js-schema.mjs` 从 `src/g2a/schema.json` 复制，禁止手动修改。

```javascript
import {Client} from 'g2a-reference-client';
const client = new Client(endpoint, {expectedGameId: 'key-quest'});
await client.join(invitation, joinRequest);
const page = await client.poll();
await client.send('chat.message', {
  text: '你撑一下，我去拿钥匙。', channel: 'team', recipients: ['alice', 'bob'],
});
await client.leave();
```

邀请由游戏方在确认用户授权后提供，不把凭据写入日志或 URL。`checkLease()` 需由集成层周期调用，`desktopVisible` 只是呈现状态，不控制真实窗口。当前不实现发现、唤起、浏览器 CORS 或完整云端接入。

开发：`npm ci`、`npm test`。包验证：`npm pack`。规范、发布边界及安全限制见主仓库文档；客户端没有自动重试有副作用操作。

出站桥接由 `g2a-reference-client/bridge` 导出 `BridgeClient`：

```javascript
import {BridgeClient} from 'g2a-reference-client/bridge';
const client = new BridgeClient(endpoint, {expectedGameId: 'key-quest', bridgeToken});
await client.join(invitation, joinRequest);
```

后续 poll/send/leave 与原客户端一致。外层 `bridgeToken` 不代替内层邀请或会话凭据；桥接是可信的明文终点，能读取经它转发的数据。超时不自动重做动作。HTTPS 使用 Node 的正常证书信任链，不禁用主机名校验。完整信任及云端未完成项见 `docs/OUTBOUND.md`。

预登记本机配对由 `g2a-reference-client/pairing` 导出 `PairingClient`。构造参数为 `endpoint, {token, expectedGameId}`；可使用 `discover()`、`request(joinRequest)`、`requests()`、`offer(id)` 和批准后的 `redeem(id, {desktopVisible})`。领取成功返回原 `Client`。`decide(offer, {allow, remember})` 只可由持控制台凭据的用户界面调用，伙伴令牌在服务器端被拒绝。完整条件与本机安全限制见 `docs/LOCAL_PAIRING.md`。
