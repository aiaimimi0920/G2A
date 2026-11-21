"""Optional game-local parameter restrictions, not new wire permissions."""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator, SchemaError

from .validation import ProtocolError


def checked_constraints(constraints, allowed_actions):
    """Freeze trusted host constraints; they may only narrow named grants."""
    if not isinstance(constraints, dict) or not set(constraints) <= set(allowed_actions):
        raise ProtocolError("invalid_arguments", "Constraints must target granted actions")
    frozen = deepcopy(constraints)
    try:
        json.dumps(frozen, allow_nan=False)
    except (ValueError, TypeError):
        raise ProtocolError("invalid_arguments", "Local constraints must be finite JSON") from None
    for schema in frozen.values():
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError:
            raise ProtocolError("invalid_arguments", "Invalid local action constraint") from None
        if _has_reference(schema):
            raise ProtocolError("invalid_arguments", "Local constraints cannot resolve references")
    return frozen


def _has_reference(value):
    if isinstance(value, dict):
        return any(key in {"$ref", "$dynamicRef"} or _has_reference(item)
                   for key, item in value.items())
    return isinstance(value, list) and any(_has_reference(item) for item in value)


def permits(constraints, action, arguments):
    return Draft202012Validator(constraints.get(action, True)).is_valid(arguments)
