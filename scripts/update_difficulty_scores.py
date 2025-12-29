#!/usr/bin/env python3
"""
Update existing SWE task files with calculated difficulty_score.

This script reads each SWE task JSON file and adds/updates the difficulty_score
field in swe_metadata based on the formula:
    patch_lines + fail_to_pass_count * 5 + pass_to_pass_count * 0.1
"""

import json
from pathlib import Path


def calculate_difficulty_score(swe_metadata: dict) -> int:
    """Calculate difficulty score from patch size and test counts."""
    gold_patch = swe_metadata.get("gold_patch", "")
    fail_to_pass = swe_metadata.get("fail_to_pass", [])
    pass_to_pass = swe_metadata.get("pass_to_pass", [])

    patch_lines = len(gold_patch.splitlines()) if gold_patch else 0
    fail_count = len(fail_to_pass)
    pass_count = len(pass_to_pass)
    return int(patch_lines + fail_count * 5 + pass_count * 0.1)


def update_task_file(task_path: Path) -> tuple[str, int, int]:
    """Update a single task file with difficulty_score.

    Returns: (task_id, old_score, new_score)
    """
    with open(task_path) as f:
        task = json.load(f)

    task_id = task.get("id", task_path.stem)
    swe_metadata = task.get("swe_metadata", {})

    if not swe_metadata:
        return task_id, 0, 0

    old_score = swe_metadata.get("difficulty_score", 0)
    new_score = calculate_difficulty_score(swe_metadata)

    swe_metadata["difficulty_score"] = new_score
    task["swe_metadata"] = swe_metadata

    with open(task_path, "w") as f:
        json.dump(task, f, indent=2)

    return task_id, old_score, new_score


def main():
    tasks_dir = Path(__file__).parent.parent / "tasks" / "tier4_swe"

    if not tasks_dir.exists():
        print(f"Tasks directory not found: {tasks_dir}")
        return 1

    task_files = sorted(tasks_dir.glob("*.json"))
    print(f"Found {len(task_files)} SWE task files\n")

    results = []
    for task_path in task_files:
        task_id, old_score, new_score = update_task_file(task_path)
        results.append((task_id, old_score, new_score))
        status = "updated" if old_score != new_score else "unchanged"
        print(f"  {task_id}: {old_score} -> {new_score} ({status})")

    # Sort by difficulty and show final order
    results.sort(key=lambda x: x[2])
    print("\nExecution order (easy to hard):")
    for i, (task_id, _, score) in enumerate(results, 1):
        print(f"  {i}. {task_id} (score: {score})")

    return 0


if __name__ == "__main__":
    exit(main())
