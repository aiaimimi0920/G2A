"""Message-role authority for the experimental protocol (not gameplay policy)."""
from types import MappingProxyType

from .validation import ProtocolError


# Keep this list explicit: a new message type must not inherit permission from
# an unrelated default branch. Identity, audience and action grants are checked
# separately by the host after this role-level gate.
MESSAGE_ROLES = MappingProxyType({
    "game.context": frozenset({"game"}),
    "chat.message": frozenset({"game", "agent"}),
    "action.request": frozenset({"agent"}),
    "action.result": frozenset({"game"}),
    "capability.update": frozenset({"game"}),
    "action.cancel": frozenset({"agent"}),
})


def require_message_role(kind, role):
    """Deny unknown types/roles and keep the existing wire error semantics."""
    allowed = MESSAGE_ROLES.get(kind, frozenset())
    if role not in allowed:
        if allowed == {"game"}:
            reason = "Game authority required"
        elif allowed == {"agent"}:
            reason = "Agent role required"
        else:
            reason = "Message role is not authorized"
        raise ProtocolError("permission_denied", reason, 403)
