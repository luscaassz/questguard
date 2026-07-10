from __future__ import annotations

from typing import Any, Dict, List, Set

import networkx as nx

from questguard.domain.issues import Issue, ValidationReport
from questguard.validation.base import QuestValidator


class GraphValidator(QuestValidator):
    name = "graph"

    def build_dependency_graph(self, quest: Dict[str, Any]) -> nx.DiGraph:
        graph = nx.DiGraph()
        objectives = quest.get("objectives", [])
        if not isinstance(objectives, list):
            return graph

        valid_objectives = [obj for obj in objectives if isinstance(obj, dict)]
        step_ids: List[str] = []
        for index, objective in enumerate(valid_objectives, start=1):
            step_id = objective.get("step_id") or f"step_{index:03d}"
            step_id = str(step_id)
            step_ids.append(step_id)
            graph.add_node(step_id)

        has_explicit_dependencies = any(
            isinstance(objective.get("depends_on"), list)
            for objective in valid_objectives
        )

        if has_explicit_dependencies:
            for objective, step_id in zip(valid_objectives, step_ids):
                dependencies = objective.get("depends_on", [])
                if not isinstance(dependencies, list):
                    continue
                for dependency in dependencies:
                    graph.add_edge(str(dependency), step_id)
        else:
            for previous, current in zip(step_ids, step_ids[1:]):
                graph.add_edge(previous, current)

        return graph

    def validate(self, quest: Dict[str, Any]) -> ValidationReport:
        report = ValidationReport(validator=self.name)
        objectives = quest.get("objectives", [])
        if not isinstance(objectives, list):
            return report

        step_ids: Set[str] = {
            str(objective.get("step_id"))
            for objective in objectives
            if isinstance(objective, dict) and objective.get("step_id")
        }

        for index, objective in enumerate(objectives):
            if not isinstance(objective, dict):
                continue
            dependencies = objective.get("depends_on", [])
            if dependencies is None:
                continue
            if not isinstance(dependencies, list):
                report.issues.append(
                    Issue(
                        code="INVALID_DEPENDENCY_LIST",
                        severity="error",
                        message="depends_on deve ser uma lista de step_ids.",
                        path=f"objectives[{index}].depends_on",
                        suggestion="Usar uma lista, inclusive uma lista vazia para etapas-raiz.",
                        source=self.name,
                    )
                )
                continue
            for dependency in dependencies:
                if str(dependency) not in step_ids:
                    report.issues.append(
                        Issue(
                            code="MISSING_STEP_DEPENDENCY",
                            severity="error",
                            message=f"A dependência '{dependency}' não aponta para uma etapa existente.",
                            path=f"objectives[{index}].depends_on",
                            suggestion="Corrigir ou remover a referência à etapa inexistente.",
                            source=self.name,
                        )
                    )

        graph = self.build_dependency_graph(quest)
        if graph.number_of_nodes() == 0:
            return report

        if not nx.is_directed_acyclic_graph(graph):
            cycles = list(nx.simple_cycles(graph))
            report.issues.append(
                Issue(
                    code="CYCLIC_OBJECTIVE_DEPENDENCY",
                    severity="error",
                    message=f"Foram encontrados ciclos entre objetivos: {cycles[:3]}",
                    path="objectives",
                    suggestion="Remover dependências circulares.",
                    source=self.name,
                )
            )
            return report

        roots = [node for node in graph.nodes if graph.in_degree(node) == 0]
        terminals = [node for node in graph.nodes if graph.out_degree(node) == 0]
        report.metadata.update({"root_steps": roots, "terminal_steps": terminals})

        if len(roots) > 1:
            report.issues.append(
                Issue(
                    code="MULTIPLE_OBJECTIVE_ROOTS",
                    severity="warning",
                    message=f"A quest possui {len(roots)} objetivos-raiz independentes.",
                    path="objectives",
                    suggestion="Confirmar se o paralelismo é intencional ou conectar as etapas.",
                    source=self.name,
                )
            )

        reachable: Set[str] = set()
        for root in roots:
            reachable.add(root)
            reachable.update(nx.descendants(graph, root))
        orphaned = sorted(set(graph.nodes) - reachable)
        if orphaned:
            report.issues.append(
                Issue(
                    code="UNREACHABLE_OBJECTIVE",
                    severity="error",
                    message=f"Objetivos inalcançáveis: {orphaned}",
                    path="objectives",
                    suggestion="Conectar os objetivos a uma raiz válida.",
                    source=self.name,
                )
            )

        return report
