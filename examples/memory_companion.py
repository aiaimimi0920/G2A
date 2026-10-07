"""示范来源边界，不是 G2A 强制记忆格式，也不是 MotCore 实现。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Memory:
    player_id: str
    game_id: str
    subject: str
    value: str
    kind: str
    source_id: str
    audience: frozenset


class CompanionMemory:
    """同一个伙伴跨会话持有的可替换记忆适配器；不按关卡重置。"""
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.records = []

    def remember(self, memory):
        if memory.kind not in {"shared_experience", "player_report", "external_reference"}:
            raise ValueError("Unknown provenance kind")
        if not memory.source_id or not memory.player_id:
            raise ValueError("Source and player identity required")
        self.records.append(memory)

    def recall(self, player_id, game_id, subject, *, recipients, allow_external=False):
        """已知背景和受众分别检查；外部参考需显式允许，且不升级来源。"""
        for memory in reversed(self.records):
            if (memory.player_id, memory.game_id, memory.subject) != (player_id, game_id, subject):
                continue
            if not set(recipients) <= memory.audience:
                continue
            if memory.kind == "external_reference" and not allow_external:
                continue
            prefix = {"shared_experience": "我们一起经历过：", "player_report": "你之前告诉过我：", "external_reference": "根据外部资料："}[memory.kind]
            return {"text": prefix + memory.value, "provenance": {
                "kind": memory.kind, "source_id": memory.source_id, "player_id": memory.player_id}}
        return None
