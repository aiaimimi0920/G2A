# Godot 游戏端示例

这是一个真正运行 Godot 场景与 GDScript 的最小游戏适配，不是渲染概念图。蓝色圆点代表玩家，橙色圆点代表固定伙伴；伙伴通过独立 Node 进程请求找钥匙，Godot 移动伙伴并改变钥匙的游戏状态。

## 三个进程的边界

- **Godot 游戏**：发布可观察信息、显示伙伴消息、领取行动、检查世界条件、移动和拾取、报告实际结果。
- **Python sidecar**：复用 G2A 参考宿主做认证、会话、消息路由、行动授权与去重，不执行游戏效果。
- **Node 伙伴**：只得到伙伴邀请，通过 G2A 观察和请求行动，不得到游戏管理员凭据。

采用 sidecar 是示例接入方式，不代表 G2A 必须依赖 Python。当前不是纯 GDScript 协议服务器，也不依赖 MotGUI 或 MotCore。确定性伙伴不是 LLM；圆点是场景占位形象，不证明跨引擎模型导入。

## 运行

在 G2A 仓库根目录先按 README 安装 Python 包和 JavaScript 依赖。需要 Node 20+ 和 Godot 4.x，CI 固定官方 4.5.1。

```sh
python examples/godot_demo.py --godot /path/to/godot --output /path/to/new-output --window
```

Windows 本机输出请使用 `C:/Users/Public/nas_home/AI/GameEditor/linshi/` 下的新目录。输出目录必须尚不存在，防止误用旧结果。启动器复制游戏到该目录，缓存与日志不会污染源工程。

- 不传 `--window`：headless 运行真实引擎逻辑，无渲染验收。
- 传 `--window`：显示游戏窗口，完成后保存 `game.png` 并退出。
- 加 `--blocked`：游戏判定钥匙不可达；即便协议已授权，游戏也返回失败，不移动或拾取。
- `game.json` 是游戏内状态，`agent.stdout` 是独立伙伴收到的结果，`result.json` 是启动器检查两端后生成的汇总。
- `godot.log` / `agent.stderr` 用于定位失败；不要在这些文件中加入令牌输出。

自动化测试使用 `GODOT_EXECUTABLE` 和 `G2A_TEST_OUTPUT`，运行 `python -m unittest discover -s tests -p test_godot_interop.py -v`。缺少配置会明确跳过，而非声称引擎通过。

## 已知边界

启动器模拟一个已由用户批准的邀请，不是两条真实用户授权 UI。令牌经子进程私有环境或 stdin 传递，不放命令行；这不防御同一 OS 账号下的恶意进程。Godot 只信任由启动器提供的回环 sidecar，尚不是面向任意远端响应的通用安全 SDK。

执行示例没有物理寻路、玩家输入、取消动画和世界事务。已验证领取前取消不执行；移动中会话退出时保留已发生的移动、不拾取钥匙，协议动作保留 unknown 而不伪造回滚。如果会话在拾取生效与回报之间关闭，回报拒绝不会使游戏崩溃，世界实际结果仍写入本地证据。

领取后的动态撤权、效果与授权之间的原子性、崩溃恢复仍需完整实现，不能将演示成功理解为生产级动作安全。桌面恢复依旧是伙伴客户端状态值，没有控制 Mot 桌面窗口。示例不联网调用模型，不创建账号，不公开任何端口。
