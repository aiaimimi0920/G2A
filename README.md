# G2A

Game-to-Agent：游戏与玩家伙伴 Agent 的独立双向交互协议。当前为 `0.1.0-dev` 实验草案，不是稳定标准或生产就绪实现。

仓库：https://github.com/aiaimimi0920/G2A 。任何游戏和 Agent 均可实现，不依赖 Mot 账号、服务器、模型、记忆服务或主仓库。聚焦伙伴身份，不扩展为游戏所有 NPC 的通用智能化系统。

- [已确认方向与待讨论边界](docs/DESIGN.md)
- [实验性规范](docs/SPECIFICATION.md)
- [完整目标与实施台账](docs/IMPLEMENTATION_PLAN.md)
- [参考 A2A 的对外发布路线](docs/PUBLISHING.md)
- [贡献规则](CONTRIBUTING.md) 与 [安全边界](SECURITY.md)

已提供权威 JSON Schema、Python 参考宿主/客户端、独立 JavaScript 客户端、跨进程 HTTP 互通和跨游戏来源记忆示例。仍未冻结消息格式，跨语言测试不代表第三方认证；尚无真实游戏引擎适配或完整云端接入。被 Mot 主仓库引用仅用于集成管理，不影响独立使用和演进。

## 本地验证

需要 Python 3.11+。在隔离环境中安装，不需要 Mot 账号、API key 或模型：

```sh
python -m pip install .
python -m unittest discover -s tests -p test_protocol.py -v
python examples/key_quest.py
```

示例启动随机端口的回环服务，通过真实 HTTP 完成游戏观察、伙伴主动发言、行动请求、游戏反馈和退出恢复；它是确定性玩具场景，不是真实 Godot 游戏或智能模型。参考服务器不支持直接公网部署。

完整测试另需 Node.js 20+（CI 使用 22）和 JavaScript 依赖。在仓库根目录运行：

```sh
node scripts/sync-js-schema.mjs --check
cd sdk/javascript
npm ci --ignore-scripts
npm test
cd ../..
python -m unittest discover -s tests -v
```

JavaScript 互通测试启动独立 Node 伙伴进程，仅交给它伙伴邀请，不提供游戏管理员令牌。它主动队聊、请求找钥匙并验证去重和越权拒绝。缺少 Node 时该项明确跳过，不能据此声称跨语言验证通过。

`examples/memory_companion.py` 示范同一伙伴在两个游戏中使用共同经历、玩家讲述和外部参考的来源边界，并按受众约束记忆披露。这不是协议指定的记忆数据库，也不证明持久化身份或云端同步已完成。JavaScript 包说明见 [SDK 文档](sdk/javascript/README.md)，目前仅支持本地打包，尚未发布 npm。

协议结构的权威源为 `src/g2a/schema.json`，语义见规范。请勿把实现中的内存容量限制、尚未开发的发现/云端入口，误认作完整协议目标已经完成。

本轮保留原仓库已有许可文件，没有另行决定或宣称新的协议规范许可；正式发布前需单独确定。
