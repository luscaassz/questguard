from __future__ import annotations

from typing import Any, Dict

import networkx as nx

from questguard.analysis.graph_builder import build_quest_graph
from questguard.repositories.world_repository import WorldRepository


def compute_graph_metrics(quest: Dict[str, Any], world: WorldRepository) -> Dict[str, Any]:
    graph = build_quest_graph(quest, world)
    quest_id = str(quest.get("quest_id", "unknown_quest"))
    node_count = graph.number_of_nodes()
    entity_nodes = [node for node in graph.nodes if world.has_entity(str(node))]
    implicit_nodes = [
        node
        for node, data in graph.nodes(data=True)
        if data.get("type") == "implicit"
    ]
    depths = []
    for node in graph.nodes:
        try:
            depths.append(nx.shortest_path_length(graph, quest_id, node))
        except nx.NetworkXNoPath:
            pass

    degree = nx.degree_centrality(graph)
    return {
        "quest_id": quest_id,
        "generation_batch": quest.get("generation_batch"),
        "quest_type": quest.get("quest_type"),
        "node_count": node_count,
        "edge_count": graph.number_of_edges(),
        "density": nx.density(graph),
        "connected_components": nx.number_connected_components(graph.to_undirected()),
        "max_depth": max(depths) if depths else 0,
        "objective_count": sum(data.get("type") == "objective" for _, data in graph.nodes(data=True)),
        "action_count": sum(data.get("type") == "action" for _, data in graph.nodes(data=True)),
        "reward_count": sum(data.get("type") == "reward" for _, data in graph.nodes(data=True)),
        "tag_count": sum(data.get("type") == "tag" for _, data in graph.nodes(data=True)),
        "world_reference_count": len(entity_nodes),
        "world_reference_rate": len(entity_nodes) / node_count if node_count else 0.0,
        "implicit_node_count": len(implicit_nodes),
        "implicit_entity_rate": len(implicit_nodes) / node_count if node_count else 0.0,
        "max_degree_centrality": max(degree.values()) if degree else 0.0,
    }
