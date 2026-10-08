"""单动作、多步、固定执行器的内存协议模型；world 为受信效果账本夹具。

lock 仅表示一个排序域，不提供跨进程数据库或真实引擎保证。
"""

from copy import deepcopy
import importlib.util
from pathlib import Path
from threading import RLock


SPEC = importlib.util.spec_from_file_location("multistep_base", Path(__file__).with_name("flow_model.py"))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
require, Rejected = M.require, M.Rejected


class SimulatedCrash(RuntimeError):
    pass


class MultiStepModel:
    def __init__(self, steps=2):
        require(type(steps) is int and 1 <= steps <= 8, "invalid_arguments")
        self.lock = RLock()
        self.steps = steps
        self.authorized = True
        self.action = None
        self.world = {}  # 外部可查事实夹具，与协议动作记录分开。

    def accept(self, request_id="a1", arguments=None):
        body = {"room": "hall"} if arguments is None else deepcopy(arguments)
        with self.lock:
            require(self.authorized, "grant_revoked")
            if self.action is not None:
                require(self.action["id"] == request_id and self.action["arguments"] == body, "id_conflict")
                return "duplicate"
            require(body == {"room": "hall"}, "invalid_arguments")
            self.action = {"id": request_id, "arguments": body, "state": "pending", "effect": "none",
                           "ticket": None, "consumed": set(), "journal": {}, "stopped": False,
                           "terminal": None}
            return "accepted"

    def claim(self, worker):
        with self.lock:
            require(worker in {"worker-1", "worker-2"}, "permission_denied")
            require(self.action is not None, "not_found")
            require(self.authorized and not self.action["stopped"], "not_executable")
            require(self.action["state"] == "pending", "not_executable")
            ticket = (self.action["id"], worker, 1)
            self.action.update(ticket=ticket, state="executing")
            return ticket

    def _ticket(self, worker, ticket):
        require(self.action is not None and ticket == self.action["ticket"]
                and ticket is not None and ticket[1] == worker, "permission_denied")

    def step(self, worker, ticket, number, *, crash=None):
        require(crash in (None, "after_claim", "after_effect", "after_journal"), "invalid_arguments")
        with self.lock:
            self._ticket(worker, ticket)
            a = self.action
            require(type(number) is int and 1 <= number <= self.steps, "execution_conflict")
            if number in a["journal"]:
                return deepcopy(a["journal"][number])  # 撤权后仅允许读取此 ticket 原事实。
            require(number not in a["consumed"], "outcome_unknown")
            require(self.authorized and not a["stopped"] and a["state"] == "executing", "not_executable")
            require(number == len(a["journal"]) + 1, "execution_conflict")
            a["consumed"].add(number)
            if crash == "after_claim":
                a.update(state="unknown", effect="undetermined")
                raise SimulatedCrash(crash)
            # 本调用持有模拟排序域；一次外部效果，记录与 action journal 分开。
            key = (ticket, number)
            require(key not in self.world, "execution_conflict")
            self.world[key] = {"step": number, "effect": "committed"}
            if number == self.steps:
                self.world[key]["result"] = {"item": "gold-key"}  # 固定游戏效果返回值，不取自 report。
            if crash == "after_effect":
                a.update(state="unknown", effect="undetermined")
                raise SimulatedCrash(crash)
            a["journal"][number] = deepcopy(self.world[key])
            a["effect"] = "committed" if len(a["journal"]) == self.steps else "partial"
            if crash == "after_journal":
                raise SimulatedCrash(crash)
            return deepcopy(a["journal"][number])

    def deny_step(self, worker, ticket, number):
        """可信世界条件拒绝：本步无效果，不能抹掉此前已提交的步骤。"""
        with self.lock:
            self._ticket(worker, ticket)
            a = self.action
            require(self.authorized and not a["stopped"] and a["state"] == "executing", "not_executable")
            require(type(number) is int and number == len(a["journal"]) + 1 and number <= self.steps
                    and number not in a["consumed"], "execution_conflict")
            effect = "partial" if a["journal"] else "none"
            a.update(denial=number, stopped=True, state="failed", effect=effect, terminal=("failed", effect))
            return ("failed", effect)

    def stop(self, *, revoke=False):
        with self.lock:
            if revoke:
                self.authorized = False
            if self.action is None or self.action["terminal"] is not None:
                return
            self.action["stopped"] = True
            if self.action["consumed"] - self.action["journal"].keys():
                self.action.update(state="unknown", effect="undetermined")
            elif self.action["state"] == "pending":
                self.action.update(state="cancelled", effect="none", terminal=("cancelled", "none"))

    def reconcile(self, worker, ticket):
        """受信查询已有 world 事实；从不重执行，查无记录不等于未发生。"""
        with self.lock:
            self._ticket(worker, ticket)
            a = self.action
            for number in a["consumed"] - a["journal"].keys():
                fact = self.world.get((ticket, number))
                if fact is not None:
                    a["journal"][number] = deepcopy(fact)
            if a["consumed"] - a["journal"].keys():
                return "unknown"
            if a["terminal"] is None:
                a["state"] = "executing"
                a["effect"] = "committed" if len(a["journal"]) == self.steps else "partial" if a["journal"] else "none"
            return "reconciled"

    def finish(self, worker, ticket):
        with self.lock:
            self._ticket(worker, ticket)
            a = self.action
            if a["terminal"] is not None:
                return a["terminal"]
            if a["consumed"] - a["journal"].keys():
                a.update(state="unknown", effect="undetermined")
                return ("unknown", "undetermined")
            if len(a["journal"]) == self.steps:
                result = ("succeeded", "committed")
            elif a["stopped"]:
                result = ("cancelled", "partial" if a["journal"] else "none")
            else:
                raise Rejected("not_executable")
            a.update(state=result[0], effect=result[1], terminal=result)
            return result

    def recover_copy(self):
        """复制持久记录假设下的快照并重建锁，不模拟真正磁盘恢复。"""
        with self.lock:
            other = MultiStepModel(self.steps)
            other.authorized, other.action, other.world = deepcopy((self.authorized, self.action, self.world))
            return other
