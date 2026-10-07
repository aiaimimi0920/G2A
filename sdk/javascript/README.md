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
