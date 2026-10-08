# G2A

Game-to-Agent：游戏与玩家伙伴 Agent 的独立双向交互协议。当前为 `0.1.0-dev` 实验草案，不是稳定标准或生产就绪实现。

仓库：https://github.com/aiaimimi0920/G2A 。任何游戏和 Agent 均可实现，不依赖 Mot 账号、服务器、模型、记忆服务或主仓库。聚焦伙伴身份，不扩展为游戏所有 NPC 的通用智能化系统。

- [已确认方向与待讨论边界](docs/DESIGN.md)
- [协议设计完整性梳理与决策队列](docs/DESIGN_COMPLETENESS.md)
- [下一版协议总设计与全流程伪代码](docs/protocol/README.md)
- [实验性规范](docs/SPECIFICATION.md)
- [完整目标与实施台账](docs/IMPLEMENTATION_PLAN.md)
- [参考 A2A 的对外发布路线](docs/PUBLISHING.md)
- [本地发现与连接授权草案](docs/CONNECTIONS.md)
- [已登记应用的跨进程配对与授权](docs/LOCAL_PAIRING.md)
- [无需游戏监听端口的出站桥接](docs/OUTBOUND.md)
- [贡献规则](CONTRIBUTING.md) 与 [安全边界](SECURITY.md)

已提供权威 JSON Schema、Python 参考宿主/客户端、独立 JavaScript 客户端、跨进程 HTTP 互通、跨游戏来源记忆示例和最小 Godot 游戏适配。仍未冻结消息格式，跨语言测试不代表第三方认证；尚无完整云端接入或生产级引擎 SDK。被 Mot 主仓库引用仅用于集成管理，不影响独立使用和演进。

当前工作重点（2026-10-07）：先完成协议研究与设计完整性，不以扩展具体应用、示例或 SDK 为主要目标。需要验证设计假设时采用必要的本地测试；GitHub Actions 暂不作为当前研究工作的前置门槛，工作流配置仍保留。设计缺口与建议以完整性梳理文档为入口，不改变现有 `0.1.0-dev` 契约。

本阶段协议工作草案、字段/操作契约、伪代码与假实现验证包已完成交付，详见
[最终审计](docs/protocol/FINAL_AUDIT.md)。统一设计验证入口为 `python scripts/verify_design.py`；
此完成状态不代表旧 SDK 已升级、生产适配器已验收或已发布稳定协议。

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

协议结构的权威源为 `src/g2a/schema.json`，语义见规范。请勿把实现中的内存容量限制、参考桥接或尚未开发的跨应用发现/云端授权，误认作完整协议目标已经完成。

## 真实 Godot 游戏示例

见 [Godot 接入说明](examples/godot_key_quest/README.md)。Godot 负责世界状态、伙伴移动和钥匙拾取；Python sidecar 负责协议；独立 Node 进程扮演伙伴。运行不需要模型或 Mot 账号：

```sh
python examples/godot_demo.py --godot /path/to/godot --output /path/to/new-output --window
```

完整引擎测试另需设置 `GODOT_EXECUTABLE` 和 `G2A_TEST_OUTPUT`。缺少这些配置时引擎测试明确跳过。CI 固定下载并校验官方 Godot 4.5.1，验证成功拾取、世界拒绝、领取前取消和移动中退出。跨进程真实窗口恢复、任意形象导入、跨应用游戏内授权入口仍未完成。

本轮保留原仓库已有许可文件，没有另行决定或宣称新的协议规范许可；正式发布前需单独确定。

## 本地加入与真实窗口示例

安装 Python 包后运行 `python examples/local_pairing.py`（需要 Tk 和可用桌面）。可以先启动桌面伙伴并询问加入，也可在游戏侧点击“链接我的伙伴”，批准后启动本地伙伴窗口。精确范围下的自动加入可明确勾选和撤销；退出时恢复实际窗口加入前的显示/隐藏状态。

它使用可信同进程注册的回环宿主，不是网络广播发现、OS 应用唤起或云端授权。自动加入设置只在本次进程运行中有效；不依赖 Mot 账号。验证窗口回调需设置 `G2A_GUI_TEST=1` 后运行完整测试，否则窗口用例明确跳过。详细信任边界见连接草案。

## 游戏主动出站连接

运行 `python examples/outbound_demo.py`，由桥接、独立 Python 游戏和 Node 伙伴完成真实三进程交互。游戏进程禁止 `socket.bind`，无需监听入站端口；外层游戏/伙伴令牌与内层邀请/会话凭据分离。Python 与 JavaScript 都提供 `BridgeClient`，复用已有协议语义。详见 [出站桥接说明](docs/OUTBOUND.md)。

这提供云端部署所需的出站传输参考，不是已部署的云端产品。桥接是能读取会话数据的可信终点；生产 TLS、身份委托、授权控制面、并发限制与持久化仍需实现。现有 TLS 用例验证本地 TLS 信任与主机名，不证明公网/NAT 场景。

## 独立进程之间的配对

运行 `python examples/process_pairing.py --entry game`，在控制台查看完整条件并输入“允许”，才启动已登记的伙伴进程并加入游戏；拒绝时不启动伙伴。`--entry desktop` 验证伙伴已运行时的申请路径。默认使用独立 JavaScript 伙伴，`--agent python` 可验证 Python 实现。

这复用原授权协调器，新增角色认证、申请所有权隔离、范围绑定和幂等领取，而不是把审批接口交给伙伴。身份来自可信启动器登记；并非陌生应用自动认证、全机扫描、强本机隔离或完整云端审批。详见 [跨进程配对说明](docs/LOCAL_PAIRING.md)。
