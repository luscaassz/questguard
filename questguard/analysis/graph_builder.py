from __future__ import annotations

from typing import Any, Dict

import networkx as nx

from questguard.repositories.world_repository import WorldRepository


def build_quest_graph(quest: Dict[str, Any], world: WorldRepository) -> nx.DiGraph:
    graph = nx.DiGraph()
    quest_id = str(quest.get("quest_id", "unknown_quest"))
    graph.add_node(quest_id, type="quest", label=quest.get("title", quest_id))

    def add_entity(entity_id: Any, relation: str) -> None:
        if not isinstance(entity_id, str) or not entity_id.strip():
            return
        entity_id = entity_id.strip()
        graph.add_node(entity_id, type=world.get_entity_type(entity_id) or "implicit")
        graph.add_edge(quest_id, entity_id, relation=relation)

    add_entity(quest.get("giver_npc"), "given_by")
    add_entity(quest.get("start_location"), "starts_at")

    for index, objective in enumerate(quest.get("objectives", []), start=1):
        if not isinstance(objective, dict):
            continue
        step_id = str(objective.get("step_id", f"step_{index:03d}"))
        node_id = f"{quest_id}::{step_id}"
        graph.add_node(node_id, type="objective", label=step_id)
        graph.add_edge(quest_id, node_id, relation="has_objective")

        action = objective.get("action")
        if isinstance(action, str) and action.strip():
            action_node = f"action::{action.strip()}"
            graph.add_node(action_node, type="action", label=action.strip())
            graph.add_edge(node_id, action_node, relation="uses_action")

        target = objective.get("target")
        if isinstance(target, str) and target.strip():
            target = target.strip()
            graph.add_node(target, type=world.get_entity_type(target) or "implicit")
            graph.add_edge(node_id, target, relation="targets")

        success = objective.get("success_condition")
        success_node = f"{node_id}::success"
        graph.add_node(success_node, type="success_condition", label=str(success))
        graph.add_edge(node_id, success_node, relation="has_success_condition")

        for dependency in objective.get("depends_on", []) or []:
            dep_node = f"{quest_id}::{dependency}"
            graph.add_node(dep_node, type="objective", label=str(dependency))
            graph.add_edge(dep_node, node_id, relation="precedes")

    for index, reward in enumerate(quest.get("rewards", []), start=1):
        if not isinstance(reward, dict):
            continue
        reward_node = f"{quest_id}::reward_{index}"
        graph.add_node(reward_node, type="reward", label=str(reward.get("type", "reward")))
        graph.add_edge(quest_id, reward_node, relation="rewards_with")
        value = reward.get("value")
        if isinstance(value, str) and value.strip():
            value = value.strip()
            graph.add_node(value, type=world.get_entity_type(value) or "reward_value")
            graph.add_edge(reward_node, value, relation="has_value")

    for tag in quest.get("reusable_tags", []):
        if isinstance(tag, str) and tag.strip():
            tag_node = f"tag::{tag.strip()}"
            graph.add_node(tag_node, type="tag", label=tag.strip())
            graph.add_edge(quest_id, tag_node, relation="has_tag")

    return graph
