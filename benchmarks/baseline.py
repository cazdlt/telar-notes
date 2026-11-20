"""Create a deterministic reference vault and measure current backend operations."""

import argparse
import gc
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

from telar.links import build_links_index
from telar.search import content_search
from telar.vault import build_tree, recent_files

ROOT = Path(__file__).resolve().parents[1]


def _median_ms(operation, repeats=5):
    samples = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = operation()
        samples.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(samples), 3), result


def _create_vault(root: Path, note_count: int) -> Path:
    vault = root / "reference-vault"
    vault.mkdir()
    folder_count = max(1, min(50, note_count // 100))
    for folder_index in range(folder_count):
        (vault / f"folder-{folder_index:02d}").mkdir()
    for index in range(note_count):
        folder = vault / f"folder-{index % folder_count:02d}"
        target = (index + folder_count) % note_count
        marker = "benchmark-needle" if index % 100 == 0 else "ordinary content"
        (folder / f"note-{index:05d}.md").write_text(
            f"---\ntitle: Note {index}\ntags: [reference]\n---\n# Note {index}\n{marker}\n[[note-{target:05d}]]\n"
        )
    return vault


def run(note_count: int) -> dict:
    import_ms, _ = _median_ms(
        lambda: subprocess.run(
            [sys.executable, "-c", "import telar"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ),
        repeats=3,
    )
    with tempfile.TemporaryDirectory() as tmp:
        vault = _create_vault(Path(tmp), note_count)
        note = vault / "folder-00" / "note-00000.md"
        gc.collect()
        tree_ms, tree = _median_ms(lambda: build_tree(vault))
        recent_ms, _ = _median_ms(lambda: recent_files(vault, "modified", 50))
        open_ms, _ = _median_ms(note.read_text)
        search_ms, results = _median_ms(
            lambda: content_search(vault, "benchmark-needle")
        )
        links_ms, index = _median_ms(lambda: build_links_index(vault), repeats=3)
        gc.collect()
        tracemalloc.start()
        build_tree(vault)
        content_search(vault, "benchmark-needle")
        build_links_index(vault)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "vault": {"notes": note_count, "top_level_entries": len(tree)},
        "median_ms": {
            "backend_import": import_ms,
            "explorer_full_refresh": tree_ms,
            "recent_files": recent_ms,
            "open_note_from_disk": open_ms,
            "content_search": search_ms,
            "links_full_rebuild": links_ms,
        },
        "result_counts": {"search_matches": len(results), "indexed_notes": len(index)},
        "peak_python_allocations_mib": round(peak_bytes / 1024 / 1024, 2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--notes", type=int, default=5_000)
    args = parser.parse_args()
    if args.notes < 1:
        parser.error("--notes must be positive")
    print(json.dumps(run(args.notes), indent=2))


if __name__ == "__main__":
    main()
