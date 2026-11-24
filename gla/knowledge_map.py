"""Domain knowledge map: skills, prerequisite DAG, test item bank."""

import json
import os


class Skill:
    def __init__(self, d):
        self.id = d["id"]
        self.name = d["name"]
        self.description = d["description"]
        self.prerequisites = list(d.get("prerequisites", []))
        self.teach_hints = d.get("teach_hints", "")
        self.items = d.get("items", [])

    def items_of_form(self, form):
        return [it for it in self.items if it["form"] == form]


class KnowledgeMap:
    def __init__(self, domain_json_path):
        with open(domain_json_path, encoding="utf-8") as f:
            d = json.load(f)
        self.domain_id = d["domain_id"]
        self.name = d["name"]
        self.skills = {s["id"]: Skill(s) for s in d["skills"]}
        self.order = self._topological_order()

    def _topological_order(self):
        order, seen = [], set()

        def visit(sid):
            if sid in seen:
                return
            seen.add(sid)
            for p in self.skills[sid].prerequisites:
                visit(p)
            order.append(sid)

        for sid in self.skills:
            visit(sid)
        return order

    def prereqs_met(self, sid, mastered_ids):
        return all(p in mastered_ids for p in self.skills[sid].prerequisites)

    def zpd_skills(self, mastered_ids):
        """Skills not yet mastered whose prerequisites are all mastered."""
        return [sid for sid in self.order
                if sid not in mastered_ids and self.prereqs_met(sid, mastered_ids)]


def load_domain(name="early_math", data_dir=None):
    if data_dir is None:
        from . import config
        data_dir = config.DATA_DIR
    return KnowledgeMap(os.path.join(data_dir, "domains", f"{name}.json"))
