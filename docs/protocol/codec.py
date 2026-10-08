"""草案专用的严格 JSON 与内容摘要参考算法；不提供认证或签名。

仅依赖标准库，与 0.1.0-dev SDK 隔离。资源上限是此验证配置的默认值，
部署可收紧；认证、业务 schema 和授权仍须在独立边界执行。
"""

from dataclasses import dataclass
import hashlib
import json


MAX_INTEGER = (1 << 53) - 1
CODEC_ID = "g2a-cjson-1"
DOMAINS = frozenset({"scope", "control", "message", "result", "relay", "auto-rule",
                     "join-intent", "action-arguments", "action-definition"})


class CodecError(ValueError):
    """稳定错误码，不包含原始输入或秘密。"""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 1_048_576
    max_depth: int = 32
    max_nodes: int = 65_536
    max_container_items: int = 4_096
    max_string_bytes: int = 65_536

    def __post_init__(self):
        for value in vars(self).values():
            if type(value) is not int or value < 1:
                raise ValueError("invalid_limits")
        # 此参考递归遍历只接受有界深度，不能由输入抬高到解释器栈上限。
        if self.max_depth > 64:
            raise ValueError("invalid_limits")


DEFAULT_LIMITS = Limits()


def _reject_number(_):
    raise CodecError("invalid_number")


def _integer(text):
    if text == "-0":
        raise CodecError("invalid_number")
    if len(text.lstrip("-")) > 16:
        raise CodecError("integer_out_of_range")
    value = int(text)
    if abs(value) > MAX_INTEGER:
        raise CodecError("integer_out_of_range")
    return value


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CodecError("duplicate_key")
        result[key] = value
    return result


def _scan_depth(text, limit):
    # 在 json.loads 构建嵌套容器前限深；完整语法仍由解析器验证。
    depth, in_string, escaped = 0, False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > limit:
                raise CodecError("depth_limit")
        elif char in "]}":
            depth -= 1


def _validate(value, limits):
    nodes = 0

    def string(text):
        try:
            size = len(text.encode("utf-8", errors="strict"))
        except UnicodeEncodeError:
            raise CodecError("invalid_unicode") from None
        if size > limits.max_string_bytes:
            raise CodecError("string_limit")

    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if nodes > limits.max_nodes:
            raise CodecError("node_limit")
        kind = type(item)
        if kind is str:
            string(item)
        elif kind is int:
            if abs(item) > MAX_INTEGER:
                raise CodecError("integer_out_of_range")
        elif item is None or kind is bool:
            return
        elif kind in (dict, list):
            if depth >= limits.max_depth:
                raise CodecError("depth_limit")
            if len(item) > limits.max_container_items:
                raise CodecError("container_limit")
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise CodecError("invalid_key")
                    # 键和值都计入节点预算；根容器为一个节点。
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
        else:
            raise CodecError("invalid_type")

    visit(value, 0)


def decode(raw, limits=DEFAULT_LIMITS):
    """严格读取 UTF-8 字节；调用方仍须流式限流，不能先无限读取网络流。"""
    if type(raw) is not bytes:
        raise CodecError("bytes_required")
    if len(raw) > limits.max_bytes:
        raise CodecError("byte_limit")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CodecError("bom_forbidden")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise CodecError("invalid_utf8") from None
    _scan_depth(text, limits.max_depth)
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_int=_integer,
                           parse_float=_reject_number, parse_constant=_reject_number)
    except (json.JSONDecodeError, RecursionError):
        raise CodecError("invalid_json") from None
    _validate(value, limits)
    return value


def canonical(value, limits=DEFAULT_LIMITS):
    """对象按 Unicode 标量排序；字符串不归一化；输出 UTF-8 无 BOM。"""
    _validate(value, limits)
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False)
    raw = bytearray()
    # 不先构造可能为 max_nodes * max_string_bytes 大小的完整输出。
    for chunk in encoder.iterencode(value):
        encoded = chunk.encode("utf-8")
        if len(raw) + len(encoded) > limits.max_bytes:
            raise CodecError("byte_limit")
        raw.extend(encoded)
    return bytes(raw)


def digest(domain, value, limits=DEFAULT_LIMITS):
    """有域隔离的比较摘要；不是 MAC、签名、身份或批准证据。"""
    if type(domain) is not str or domain not in DOMAINS:
        raise CodecError("invalid_digest_domain")
    prefix = (CODEC_ID + "\0" + domain + "\0").encode("ascii")
    return hashlib.sha256(prefix + canonical(value, limits)).hexdigest()
