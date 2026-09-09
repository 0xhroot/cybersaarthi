"""Deterministic graph algorithms over the in-memory knowledge graph.

The case graph is loaded from PostgreSQL (the source of truth) and analysed
here with exact, deterministic algorithms so every result is reproducible and
explainable.  Neo4j is used where traversal is the tool of choice (multi-hop
paths, shared-identifier fan-out, candidate hypothesis pairs); the heavier
global measurements (components, communities, centrality, PageRank) run here
because Neo4j Community Edition ships no GDS library to compute them.

All algorithms iterate nodes in sorted id order so output is stable.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

NODE_UNREACHABLE = float("inf")


@dataclass(frozen=True)
class UndirectedEdge:
    a: str
    b: str


@dataclass(frozen=True)
class Graph:
    """Bidirectional representation of a case's relationships as a simple graph."""

    nodes: frozenset[str]
    edges: frozenset[UndirectedEdge]
    directed: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)  # src, dst, rel_type

    @property
    def adjacency(self) -> dict[str, set[str]]:
        adj: dict[str, set[str]] = defaultdict(set)
        for e in self.edges:
            adj[e.a].add(e.b)
            adj[e.b].add(e.a)
        return dict(adj)

    @property
    def out_degree(self) -> dict[str, int]:
        deg: dict[str, int] = defaultdict(int)
        for src, _, _ in self.directed:
            deg[src] += 1
        return {n: deg.get(n, 0) for n in self.nodes}

    @property
    def in_degree(self) -> dict[str, int]:
        deg: dict[str, int] = defaultdict(int)
        for _, dst, _ in self.directed:
            deg[dst] += 1
        return {n: deg.get(n, 0) for n in self.nodes}

    @property
    def degree(self) -> dict[str, int]:
        return {n: len(self.adjacency.get(n, set())) for n in self.nodes}


def build_graph(
    nodes: set[str],
    relationships: list[tuple[str, str, str]],
) -> Graph:
    """Relationships are (source_entity_id, target_entity_id, relationship_type)."""
    edge_set: set[UndirectedEdge] = set()
    directed: list[tuple[str, str, str]] = []
    for src, dst, rel_type in relationships:
        if src == dst:
            continue
        directed.append((src, dst, rel_type))
        a, b = sorted((src, dst))
        edge_set.add(UndirectedEdge(a, b))
    return Graph(
        nodes=frozenset(nodes),
        edges=frozenset(edge_set),
        directed=tuple(directed),
    )


def connected_components(graph: Graph) -> list[frozenset[str]]:
    """Return connected components sorted by decreasing size (ties by id)."""
    adj = graph.adjacency
    visited: set[str] = set()
    components: list[frozenset[str]] = []
    for node in sorted(graph.nodes):
        if node in visited:
            continue
        stack = [node]
        visited.add(node)
        component: set[str] = set()
        while stack:
            current = stack.pop()
            component.add(current)
            for neighbor in adj.get(current, ()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(frozenset(component))
    return sorted(components, key=lambda c: (-len(c), min(c)))


def articulation_points(graph: Graph) -> frozenset[str]:
    """Tarjan's algorithm, deterministic over sorted iteration order.

    The DFS is iterative (explicit stack) so graphs far larger than the
    Python recursion limit (thousands of nodes, e.g. long relationship
    chains) are analysed without a RecursionError. Discovery, low-link
    updates and cut-vertex detection mirror the recursive formulation
    exactly, and neighbours are visited in sorted order for stability.
    """
    adj = graph.adjacency
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    child_count: dict[str, int] = {}
    cut: set[str] = set()
    timer = 0

    def dfs(start: str) -> None:
        nonlocal timer
        parent[start] = None
        child_count[start] = 0
        disc[start] = low[start] = timer
        timer += 1
        stack: list[str] = [start]
        neighbors = {start: iter(sorted(adj.get(start, ())))}
        while stack:
            node = stack[-1]
            try:
                neighbor = next(neighbors[node])
            except StopIteration:
                stack.pop()
                node_parent = parent[node]
                if node_parent is None:
                    if child_count[node] > 1:
                        cut.add(node)
                else:
                    low[node_parent] = min(low[node_parent], low[node])
                    if parent[node_parent] is not None and low[node] >= disc[node_parent]:
                        cut.add(node_parent)
                continue
            if neighbor not in disc:
                parent[neighbor] = node
                child_count[node] += 1
                child_count[neighbor] = 0
                disc[neighbor] = low[neighbor] = timer
                timer += 1
                neighbors[neighbor] = iter(sorted(adj.get(neighbor, ())))
                stack.append(neighbor)
            elif neighbor != parent[node]:
                low[node] = min(low[node], disc[neighbor])

    for node in sorted(graph.nodes):
        if node not in disc and adj.get(node):
            dfs(node)
    return frozenset(cut)


def betweenness_centrality(graph: Graph) -> dict[str, float]:
    """Brandes' algorithm on the simple undirected graph. 1 for isolated/lonely."""
    adj = graph.adjacency
    nodes = sorted(graph.nodes)
    bc: dict[str, float] = {n: 0.0 for n in nodes}
    for source in nodes:
        predecessors: dict[str, list[str]] = defaultdict(list)
        count: dict[str, int] = defaultdict(int)
        dist: dict[str, int] = {}
        dist[source] = 0
        count[source] = 1
        queue: deque[str] = deque([source])
        stack: list[str] = []
        while queue:
            node = queue.popleft()
            stack.append(node)
            for neighbor in sorted(adj.get(node, ())):
                if neighbor not in dist:
                    dist[neighbor] = dist[node] + 1
                    queue.append(neighbor)
                if dist[neighbor] == dist[node] + 1:
                    count[neighbor] += count[node]
                    predecessors[neighbor].append(node)
        dependency: dict[str, float] = {n: 0.0 for n in nodes}
        while stack:
            node = stack.pop()
            for pred in predecessors[node]:
                factor = (1.0 + dependency[node]) * count[pred] / count[node]
                dependency[pred] += factor
            if node != source:
                bc[node] += dependency[node]
    for node in nodes:
        if bc[node] > 0:
            bc[node] /= 2.0
    return bc


def closeness_centrality(graph: Graph) -> dict[str, float]:
    """Normalised closeness over the undirected graph (sum of reciprocal distances)."""
    adj = graph.adjacency
    nodes = sorted(graph.nodes)
    total_nodes = len(nodes)
    result: dict[str, float] = {n: 0.0 for n in nodes}
    for node in nodes:
        dist: dict[str, int] = {}
        dist[node] = 0
        queue: deque[str] = deque([node])
        while queue:
            current = queue.popleft()
            for neighbor in sorted(adj.get(current, ())):
                if neighbor not in dist:
                    dist[neighbor] = dist[current] + 1
                    queue.append(neighbor)
        reachable = [d for d in dist.values() if d > 0]
        if reachable and total_nodes > 1:
            raw = sum(1.0 / d for d in reachable) / (total_nodes - 1)
        else:
            raw = 0.0
        result[node] = raw
    return result


def pagerank(
    graph: Graph,
    damping: float = 0.85,
    iterations: int = 30,
) -> dict[str, float]:
    """Deterministic power iteration over the directed edges."""
    nodes = sorted(graph.nodes)
    out = graph.out_degree
    if not nodes:
        return {}
    n = len(nodes)
    out_neighbors: dict[str, list[str]] = defaultdict(list)
    for src, dst, _ in graph.directed:
        out_neighbors[src].append(dst)
    for node in nodes:
        out_neighbors[node] = sorted(set(out_neighbors[node]))
    rank = {node: 1.0 / n for node in nodes}
    seed = (1.0 - damping) / n
    for _ in range(iterations):
        new_rank = {node: seed for node in nodes}
        dangling = damping * sum(rank[u] for u in nodes if out[u] == 0) / n
        for u in nodes:
            if out[u] == 0:
                continue
            share = damping * rank[u] / out[u]
            for dst in out_neighbors[u]:
                new_rank[dst] += share
        for node in nodes:
            new_rank[node] += dangling
        rank = new_rank
    return rank


def common_neighbors(graph: Graph, a: str, b: str) -> set[str]:
    adj = graph.adjacency
    return adj.get(a, set()) & adj.get(b, set())


def find_triangles(graph: Graph) -> list[frozenset[str]]:
    """All 3-cycles in the undirected graph (each reported once)."""
    adj = graph.adjacency
    triangles: set[frozenset[str]] = set()
    for a in sorted(graph.nodes):
        for b in adj.get(a, set()):
            if b <= a:
                continue
            shared = adj.get(a, set()) & adj.get(b, set())
            for c in shared:
                if c <= b:
                    continue
                triangles.add(frozenset((a, b, c)))
    return sorted(triangles, key=lambda t: tuple(sorted(t)))
