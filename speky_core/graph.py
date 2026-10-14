"""Dependencies, gates, typed links and the ready queue (CONTRACTS.md §2)."""
from typing import Dict, List

from .errors import SpekyError
from .items import DONE_STATUSES, PRIORITY_ORDER, Item, Project, now

GATE_TYPES = ("human", "ci", "pr")
LINK_TYPES = ("discovered-from", "caused-by", "related", "validates", "supersedes")


def statuses(project: Project) -> Dict[str, dict]:
    return {item.id: item.info() for item in project.items()}


def blocked_by(info: dict, all_info: Dict[str, dict]) -> List[str]:
    reasons = []
    for dep in info["dependencies"]:
        dep_info = all_info.get(dep) or next((v for k, v in all_info.items()
                                              if k.lstrip("0") == dep.lstrip("0")), None)
        if not dep_info:
            reasons.append(f"unknown dependency {dep}")
        elif dep_info["status"] not in DONE_STATUSES:
            reasons.append(f"{dep} ({dep_info['status']})")
    for gate in info["gates"]:
        if gate.get("status") == "open":
            reasons.append(f"gate {gate['id']} ({gate['type']}): {gate['reason']}")
    return reasons


def ready(project: Project) -> List[dict]:
    """Open items whose dependencies are done and which have no open gate, best first."""
    all_info = statuses(project)
    result = []
    for info in all_info.values():
        if info["status"] in DONE_STATUSES:
            continue
        if not blocked_by(info, all_info):
            result.append(info)
    in_progress_first = {"in_progress": 0, "review": 0, "ready": 1, "draft": 2}
    return sorted(result, key=lambda i: (in_progress_first.get(i["status"], 3),
                                         PRIORITY_ORDER.get(str(i["priority"]), 2), i["id"]))


def cycles(project: Project) -> List[List[str]]:
    graph = {k: v["dependencies"] for k, v in statuses(project).items()}
    found, state, stack = [], {}, []

    def visit(node):
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, []):
            if state.get(dep) == 1:
                found.append(stack[stack.index(dep):] + [dep])
            elif state.get(dep) is None and dep in graph:
                visit(dep)
        stack.pop()
        state[node] = 2

    for node in graph:
        if state.get(node) is None:
            visit(node)
    return found


def add_gate(item: Item, type_: str, reason: str) -> dict:
    if type_ not in GATE_TYPES:
        raise SpekyError("bad_gate_type", f"Gate type must be one of {', '.join(GATE_TYPES)}.")
    status = item.load_status()
    gates = status.get("gates", [])
    gate = {"id": f"G{len(gates) + 1}", "type": type_, "reason": reason, "status": "open",
            "created_at": now()}
    gates.append(gate)
    item.update_status(gates=gates)
    return gate


def resolve_gate(item: Item, gate_id: str, by: str = "", note: str = "") -> dict:
    status = item.load_status()
    gates = status.get("gates", [])
    for gate in gates:
        if gate["id"].lower() == gate_id.lower():
            gate.update(status="resolved", resolved_by=by, note=note, resolved_at=now())
            item.update_status(gates=gates)
            return gate
    raise SpekyError("gate_not_found", f"{item.id} has no gate {gate_id}.")


def add_link(project: Project, item: Item, type_: str, target: str) -> dict:
    if type_ not in LINK_TYPES:
        raise SpekyError("bad_link_type", f"Link type must be one of {', '.join(LINK_TYPES)}.")
    target_item = project.find(target)
    status = item.load_status()
    links = status.get("links", [])
    link = {"type": type_, "target": target_item.id}
    if link not in links:
        links.append(link)
        item.update_status(links=links)
    return link
