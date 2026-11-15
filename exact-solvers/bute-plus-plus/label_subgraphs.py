import argparse
import csv
import subprocess
from pathlib import Path


def read_pace_graph(path):
    adjacency = None
    declared_edges = 0
    edge_count = 0

    with path.open(encoding="utf-8") as graph_file:
        for line_number, line in enumerate(graph_file, start=1):
            fields = line.split()
            if not fields or fields[0] == "c":
                continue

            location = f"{path}:{line_number}"
            if fields[0] == "p":
                if adjacency is not None or len(fields) != 4 or fields[1] != "tdp":
                    raise ValueError(f"{location}: expected one p tdp header")

                vertex_count, declared_edges = map(int, fields[2:])
                if vertex_count < 1 or declared_edges < 0:
                    raise ValueError(f"{location}: invalid graph size")

                adjacency = {
                    vertex: set() for vertex in range(1, vertex_count + 1)
                }
                continue

            if adjacency is None or len(fields) != 2:
                raise ValueError(f"{location}: expected a header or an edge")

            u, v = map(int, fields)
            if u not in adjacency or v not in adjacency or u == v:
                raise ValueError(f"{location}: invalid edge {u} {v}")
            if v in adjacency[u]:
                raise ValueError(f"{location}: duplicate edge {u} {v}")

            adjacency[u].add(v)
            adjacency[v].add(u)
            edge_count += 1

    if adjacency is None:
        raise ValueError(f"{path}: missing p tdp header")
    if edge_count != declared_edges:
        raise ValueError(
            f"{path}: header declares {declared_edges} edges, read {edge_count}"
        )

    return adjacency


def connected_components(adjacency, vertices):
    unseen = set(vertices)

    for start in sorted(unseen):
        if start not in unseen:
            continue

        unseen.remove(start)
        stack = [start]
        component = []

        while stack:
            vertex = stack.pop()
            component.append(vertex)
            neighbors = adjacency[vertex] & unseen
            unseen.difference_update(neighbors)
            stack.extend(neighbors)

        yield sorted(component)


def save_graph(path, adjacency, vertices):
    local_ids = {
        vertex: local_id for local_id, vertex in enumerate(vertices, start=1)
    }
    edges = [
        (local_ids[u], local_ids[v])
        for u in vertices
        for v in sorted(adjacency[u])
        if v in local_ids and u < v
    ]

    with path.open("w", encoding="utf-8") as graph_file:
        graph_file.write(f"p tdp {len(vertices)} {len(edges)}\n")
        for u, v in edges:
            graph_file.write(f"{u} {v}\n")


def calculate_scores(graph_path, vertex_count, scorer, solver):
    if vertex_count == 1:
        return [1]

    with graph_path.open(encoding="utf-8") as graph_file:
        result = subprocess.run(
            [str(scorer), str(solver)],
            stdin=graph_file,
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )

    reader = csv.DictReader(result.stdout.splitlines())
    if reader.fieldnames != ["vertex", "quality"]:
        raise ValueError(f"{graph_path}: unexpected score CSV header")

    scores = {}
    for row in reader:
        vertex = int(row["vertex"])
        quality = int(row["quality"])
        if vertex in scores or not 1 <= quality <= vertex_count:
            raise ValueError(f"{graph_path}: invalid score row {row}")
        scores[vertex] = quality

    expected_ids = range(1, vertex_count + 1)
    if scores.keys() != set(expected_ids):
        raise ValueError(f"{graph_path}: expected one score for each vertex")

    return [scores[vertex] for vertex in expected_ids]


def save_scores(path, vertices, scores, chosen_root):
    with path.open("w", encoding="utf-8", newline="") as score_file:
        writer = csv.writer(score_file)
        writer.writerow(["vertex", "original_vertex", "quality", "chosen"])

        for local_id, (original_vertex, quality) in enumerate(
            zip(vertices, scores), start=1
        ):
            writer.writerow(
                [local_id, original_vertex, quality, int(original_vertex == chosen_root)]
            )


def label_subgraphs(graph_path, output_dir, scorer, solver):
    adjacency = read_pace_graph(graph_path)
    components = list(connected_components(adjacency, adjacency))
    output_dir.mkdir(parents=True, exist_ok=False)

    if len(components) == 1:
        initial_states = [("root", components[0])]
    else:
        initial_states = [
            (f"component-{i}", component)
            for i, component in enumerate(components, start=1)
        ]

    pending = list(reversed(initial_states))

    while pending:
        state_id, vertices = pending.pop()
        state_graph = output_dir / f"{state_id}.gr"
        state_scores = output_dir / f"{state_id}.csv"

        save_graph(state_graph, adjacency, vertices)
        print(f"Scoring {state_graph} ({len(vertices)} vertices)", flush=True)
        scores = calculate_scores(state_graph, len(vertices), scorer, solver)

        # Choose the lowest score, then the smallest original vertex ID.
        _, chosen_root = min(zip(scores, vertices))
        save_scores(state_scores, vertices, scores, chosen_root)

        remaining = set(vertices) - {chosen_root}
        children = list(connected_components(adjacency, remaining))
        child_states = [
            (f"{state_id}-{i}", child)
            for i, child in enumerate(children, start=1)
        ]
        pending.extend(reversed(child_states))


def main():
    parser = argparse.ArgumentParser(
        description="Save and score subgraphs along one optimal treedepth rollout."
    )
    parser.add_argument("input", type=Path, help="A graph file or directory of graphs")
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Subdirectory under ./output for graph and score files"
    )
    parser.add_argument("--scorer", type=Path, default=Path("vertex_quality"))
    parser.add_argument(
        "--solver", type=Path, default=Path("exact-solvers/bute-plus-plus/solve")
    )
    args = parser.parse_args()

    # All results are stored under the output directory.
    output_root = Path("output") / args.output_dir

    scorer = args.scorer.resolve()
    solver = args.solver.resolve()

    try:
        if args.input.is_dir():
            graphs = sorted(
                path for path in args.input.iterdir()
                if path.is_file() and path.suffix.lower() in {".gr", ".txt"}
            )
            if not graphs:
                parser.error(f"No .gr or .txt files found in {args.input}")

            # Create a separate directory for each original graph.
            jobs = [
                (graph, output_root / graph.stem)
                for graph in graphs
            ]

        elif args.input.is_file():
            # Also create a separate directory for a single input graph.
            jobs = [
                (args.input, output_root / args.input.stem)
            ]

        else:
            parser.error(f"Input path does not exist: {args.input}")

        # Prevent overwriting existing results.
        for _, output_dir in jobs:
            if output_dir.exists():
                parser.error(f"Output path already exists: {output_dir}")

        # Process each original graph.
        for graph, output_dir in jobs:
            print(f"Processing {graph}", flush=True)
            label_subgraphs(graph, output_dir, scorer, solver)

    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()