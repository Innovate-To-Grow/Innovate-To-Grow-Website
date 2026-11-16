from __future__ import annotations

from collections.abc import Iterator

from .imports import Import


class _Tarjan:
    """Iterative Tarjan's algorithm: a recursive one would overflow on a long import chain."""

    def __init__(self, graph: dict[str, set[str]]):
        self.graph = graph
        self.index: dict[str, int] = {}
        self.low: dict[str, int] = {}
        self.on_stack: set[str] = set()
        self.stack: list[str] = []
        self.components: list[list[str]] = []

    def _visit(self, node: str) -> Iterator[str]:
        self.index[node] = self.low[node] = len(self.index)
        self.stack.append(node)
        self.on_stack.add(node)
        return iter(sorted(self.graph.get(node, ())))

    def _pop_component(self, node: str) -> None:
        component = []
        while True:
            member = self.stack.pop()
            self.on_stack.discard(member)
            component.append(member)
            if member == node:
                break
        if len(component) > 1:
            self.components.append(sorted(component))

    def _next_unvisited(self, node: str, children: Iterator[str]) -> str | None:
        """Advance ``node``'s child iterator to the next unvisited child, updating lowlinks on the way."""
        for child in children:
            if child not in self.index:
                return child
            if child in self.on_stack:
                self.low[node] = min(self.low[node], self.index[child])
        return None

    def run(self, root: str) -> None:
        work = [(root, self._visit(root))]
        while work:
            node, children = work[-1]
            child = self._next_unvisited(node, children)
            if child is not None:
                work.append((child, self._visit(child)))
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                self.low[parent] = min(self.low[parent], self.low[node])
            if self.low[node] == self.index[node]:
                self._pop_component(node)


def strongly_connected(graph: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components with more than one node, each sorted, in sorted order."""
    tarjan = _Tarjan(graph)
    for root in sorted(graph):
        if root not in tarjan.index:
            tarjan.run(root)
    return sorted(tarjan.components)


def import_cycles(imports: list[Import]) -> list[list[str]]:
    graph: dict[str, set[str]] = {}
    for item in imports:
        if item.top_level and item.target != item.source:
            graph.setdefault(item.source, set()).add(item.target)
            graph.setdefault(item.target, set())
    return strongly_connected(graph)
