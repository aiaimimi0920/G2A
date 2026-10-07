"""协议数据定义的唯一校验入口。"""
from importlib.resources import files
import json

from jsonschema import Draft202012Validator


class ProtocolError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.status = status

    def as_dict(self):
        return {"error": {"code": self.code, "message": str(self)}}


SCHEMA = json.loads(files("g2a").joinpath("schema.json").read_text(encoding="utf-8"))
Draft202012Validator.check_schema(SCHEMA)


def validate(kind, value):
    validator = Draft202012Validator({"$ref": f"#/$defs/{kind}", "$defs": SCHEMA["$defs"]})
    problem = next(validator.iter_errors(value), None)
    if problem:
        # 不把调用方的消息正文、令牌或任意参数值放入错误回包。
        raise ProtocolError("invalid_message", f"Invalid {kind} at /{'/'.join(map(str, problem.absolute_path))}")
    return value
