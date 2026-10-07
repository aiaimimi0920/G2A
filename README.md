# G2A

Game-to-Agent：游戏与玩家伙伴 Agent 的独立双向交互协议。当前为 `0.1.0-dev` 实验草案，不是稳定标准或生产就绪实现。

仓库：https://github.com/aiaimimi0920/G2A 。任何游戏和 Agent 均可实现，不依赖 Mot 账号、服务器、模型、记忆服务或主仓库。聚焦伙伴身份，不扩展为游戏所有 NPC 的通用智能化系统。

- [已确认方向与待讨论边界](docs/DESIGN.md)
- [实验性规范](docs/SPECIFICATION.md)
- [完整目标与实施台账](docs/IMPLEMENTATION_PLAN.md)
- [贡献规则](CONTRIBUTING.md) 与 [安全边界](SECURITY.md)

已提供权威 JSON Schema、Python 参考宿主/客户端和真实 HTTP 交互示例。仍未冻结消息格式，尚无跨语言一致性认证、真实游戏引擎适配或完整云端接入。被 Mot 主仓库引用仅用于集成管理，不影响独立使用和演进。

## 本地验证

需要 Python 3.11+。在隔离环境中安装，不需要 Mot 账号、API key 或模型：

```sh
python -m pip install .
python -m unittest discover -s tests -v
python examples/key_quest.py
```

示例启动随机端口的回环服务，通过真实 HTTP 完成游戏观察、伙伴主动发言、行动请求、游戏反馈和退出恢复；它是确定性玩具场景，不是真实 Godot 游戏或智能模型。参考服务器不支持直接公网部署。

协议结构的权威源为 `src/g2a/schema.json`，语义见规范。请勿把实现中的内存容量限制、尚未开发的发现/云端入口，误认作完整协议目标已经完成。

本轮保留原仓库已有许可文件，没有另行决定或宣称新的协议规范许可；正式发布前需单独确定。
