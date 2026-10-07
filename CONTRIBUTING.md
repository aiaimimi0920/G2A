# 参与 G2A

目前是开发草案，不是稳定标准。先通过 Issue 说明场景、参与角色、权限与失败行为，再提出规范变更。协议与实现的修改通过 Pull Request 评审，重要决定留在仓库，不以聊天记录代替发布契约。

影响消息或行为的变更必须同时检查：

1. `docs/SPECIFICATION.md` 的语义与安全边界。
2. `src/g2a/schema.json` 的权威结构定义。
3. 参考运行时、客户端和正反例测试。
4. 示例与变更记录，明确兼容性影响。

schema 是手工维护的权威 JSON 文件，不从 SDK 类反向推断规范。不能只改一份 SDK 就宣布协议升级。未完成验收项保留在 IMPLEMENTATION_PLAN，不以某个测试绿色认定整个协议完成。

本地验证：在隔离 Python 环境安装项目后执行 `python -m unittest discover -s tests -v` 和 `python examples/key_quest.py`。不要运行旧 Mot 服务或把凭据放进测试夹具。

提交前确认有权提供代码和文档，遵守现有许可；本轮尚未另行制定 CLA/DCO 或新规范许可，不推定第三方已经同意重新授权。
