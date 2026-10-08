"""显式测试扩展：仅收紧请求，不执行插件、改权限或修改输入。

example.* 不是正式 G2A 扩展注册；仅用来验证处理器装配和不可静默降级。
"""

SUPPORTED = frozenset({("example.max-chat-bytes", "1"), ("example.deny-action", "1")})


def enforce(checks, extensions, operation, envelope):
    for name, extension in extensions.items():
        if (name, extension["version"]) not in SUPPORTED:
            raise checks.ContractError("feature_unsupported")
        value = extension["value"]
        if name == "example.max-chat-bytes":
            if type(value) is not dict or set(value) != {"maximum"} or type(value["maximum"]) is not int or not 1 <= value["maximum"] <= 65536:
                raise checks.ContractError("invalid_arguments")
            if operation not in {"chat.send", "player_chat.forward"}:
                raise checks.ContractError("feature_unsupported")
            if len(envelope["payload"]["text"].encode("utf-8")) > value["maximum"]:
                raise checks.ContractError("resource_limit")
        else:
            if type(value) is not dict or set(value) != {"action"} or type(value["action"]) is not str:
                raise checks.ContractError("invalid_arguments")
            if operation != "action.request":
                raise checks.ContractError("feature_unsupported")
            if envelope["payload"]["action"] == value["action"]:
                raise checks.ContractError("permission_denied")
