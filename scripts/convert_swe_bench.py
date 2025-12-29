#!/usr/bin/env python3
"""
Convert SWE-bench Lite tasks to invar-benchmark format.

Usage:
    python scripts/convert_swe_bench.py [--limit N] [--repos REPO1,REPO2]

Requirements:
    pip install datasets

Examples:
    # Convert all tasks (may be slow)
    python scripts/convert_swe_bench.py

    # Convert first 10 tasks
    python scripts/convert_swe_bench.py --limit 10

    # Convert only Django tasks
    python scripts/convert_swe_bench.py --repos django/django

    # Convert specific repos with limit
    python scripts/convert_swe_bench.py --repos django/django,psf/requests --limit 5
"""

import argparse
import json
from pathlib import Path


def calculate_difficulty_score(gold_patch: str, fail_to_pass: list, pass_to_pass: list) -> int:
    """Calculate difficulty score from patch size and test counts.

    Formula: patch_lines + fail_to_pass_count * 5 + pass_to_pass_count * 0.1
    - Patch lines: Direct measure of change complexity
    - Fail to pass: Tests to fix (weighted heavily)
    - Pass to pass: Regression risk (low weight)
    """
    patch_lines = len(gold_patch.splitlines()) if gold_patch else 0
    fail_count = len(fail_to_pass)
    pass_count = len(pass_to_pass)
    return int(patch_lines + fail_count * 5 + pass_count * 0.1)


def convert_instance(instance: dict) -> dict:
    """Convert a SWE-bench instance to invar-benchmark task format."""
    instance_id = instance["instance_id"]
    repo = instance["repo"]
    problem_statement = instance["problem_statement"]

    # Create task ID from instance_id (e.g., django__django-11099 -> swe_django_11099)
    task_id = "swe_" + instance_id.replace("__", "_").replace("-", "_")

    # Parse FAIL_TO_PASS and PASS_TO_PASS (they are JSON strings)
    try:
        fail_to_pass = json.loads(instance.get("FAIL_TO_PASS", "[]"))
    except (json.JSONDecodeError, TypeError):
        fail_to_pass = []

    try:
        pass_to_pass = json.loads(instance.get("PASS_TO_PASS", "[]"))
    except (json.JSONDecodeError, TypeError):
        pass_to_pass = []

    gold_patch = instance.get("patch", "")

    # Calculate difficulty score
    difficulty_score = calculate_difficulty_score(gold_patch, fail_to_pass, pass_to_pass)

    # Build prompt
    prompt = f"""Fix the following issue in the {repo} repository.

## Issue

{problem_statement}

## Instructions

1. Clone the repository at the specified commit
2. Understand the issue and locate the relevant code
3. Implement a fix that resolves the issue
4. Ensure existing tests still pass

The fix should be minimal and focused on the issue described.
"""

    return {
        "id": task_id,
        "name": instance_id,
        "description": f"SWE-bench: {instance_id}",
        "tier": "tier4_swe",
        "prompt": prompt,
        "initial_files": {},
        "test_file": "",
        "hidden_test_file": "",
        "expected_files": [],
        "tags": ["swe-bench", repo.split("/")[0]],
        "difficulty": "hard",
        "swe_metadata": {
            "instance_id": instance_id,
            "repo": repo,
            "base_commit": instance.get("base_commit", ""),
            "test_patch": instance.get("test_patch", ""),
            "gold_patch": gold_patch,
            "fail_to_pass": fail_to_pass,
            "pass_to_pass": pass_to_pass,
            "version": instance.get("version", ""),
            "environment_setup_commit": instance.get("environment_setup_commit", ""),
            "difficulty_score": difficulty_score,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Convert SWE-bench Lite to invar-benchmark format")
    parser.add_argument("--limit", type=int, help="Limit number of tasks to convert")
    parser.add_argument("--repos", help="Comma-separated list of repos to include (e.g., django/django,psf/requests)")
    parser.add_argument("--output-dir", default="tasks/tier4_swe", help="Output directory")
    args = parser.parse_args()

    try:
        from datasets import load_dataset
    except ImportError:
        print("Error: datasets library not installed")
        print("Run: pip install datasets")
        return 1

    print("Loading SWE-bench Lite dataset...")
    dataset = load_dataset("SWE-bench/SWE-bench_Lite", split="test")
    print(f"Loaded {len(dataset)} instances")

    # Filter by repos if specified
    if args.repos:
        allowed_repos = set(args.repos.split(","))
        dataset = dataset.filter(lambda x: x["repo"] in allowed_repos)
        print(f"Filtered to {len(dataset)} instances from repos: {allowed_repos}")

    # Apply limit
    if args.limit:
        dataset = dataset.select(range(min(args.limit, len(dataset))))
        print(f"Limited to {len(dataset)} instances")

    # Convert and save
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    converted = 0
    for instance in dataset:
        task = convert_instance(instance)
        task_file = output_dir / f"{task['id']}.json"

        with open(task_file, "w") as f:
            json.dump(task, f, indent=2)

        converted += 1
        print(f"  [{converted}] {task['id']}")

    print(f"\nConverted {converted} tasks to {output_dir}/")

    # Print summary by repo
    print("\nTasks by repository:")
    repo_counts: dict[str, int] = {}
    for task_file in output_dir.glob("*.json"):
        with open(task_file) as f:
            task = json.load(f)
            repo = task.get("swe_metadata", {}).get("repo", "unknown")
            repo_counts[repo] = repo_counts.get(repo, 0) + 1

    for repo, count in sorted(repo_counts.items()):
        print(f"  {repo}: {count}")

    return 0


if __name__ == "__main__":
    exit(main())
