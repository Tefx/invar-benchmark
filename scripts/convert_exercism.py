#!/usr/bin/env python3
"""
Convert Exercism Python exercises to invar-benchmark format.

Downloads from HuggingFace dataset and converts to benchmark task JSON.

Usage:
    python scripts/convert_exercism.py
    python scripts/convert_exercism.py --tier2-only
    python scripts/convert_exercism.py --list
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Tasks already in benchmark (avoid duplicates)
EXISTING_TASKS = {
    "two_fer",
    "raindrops",
    "hamming",
    "isogram",
    "pangram",
}

# Tasks suitable for tier2 (have contract value - state, constraints, invariants)
TIER2_CANDIDATES = {
    "bank_account": "Has balance >= 0 invariant, thread-safe operations",
    "binary_search": "Requires sorted input (@pre), returns valid index (@post)",
    "binary_search_tree": "BST invariant must be maintained",
    "clock": "Hour 0-23, minute 0-59 constraints",
    "robot_simulator": "State machine with position/direction invariants",
    "matrix": "Dimension constraints, valid indices",
    "complex_numbers": "Mathematical invariants (magnitude, conjugate)",
    "rational_numbers": "GCD normalization, denominator != 0",
    "linked_list": "Pointer invariants, list integrity",
    "circular_buffer": "Capacity constraints, read/write pointers",
    "simple_linked_list": "List invariants",
    "custom_set": "Set uniqueness invariant",
    "bowling": "Frame/roll constraints, score calculation rules",
    "grade_school": "Unique names per grade",
    "kindergarten_garden": "Fixed student assignments",
    "phone_number": "Format validation, digit constraints",
    "isbn_verifier": "ISBN-10 checksum validation",
    "luhn": "Luhn algorithm validation",
    "triangle": "Triangle inequality theorem",
    "pythagorean_triplet": "a² + b² = c² constraint",
}

# Tasks suitable for tier1 (simple, verify no overhead)
TIER1_CANDIDATES = {
    "acronym",
    "anagram",
    "armstrong_numbers",
    "bob",
    "collatz_conjecture",
    "difference_of_squares",
    "gigasecond",
    "grains",
    "leap",
    "nucleotide_count",
    "protein_translation",
    "resistor_color",
    "resistor_color_duo",
    "reverse_string",
    "rna_transcription",
    "roman_numerals",
    "scrabble_score",
    "space_age",
    "word_count",
    "etl",
    "flatten_array",
    "high_scores",
    "list_ops",
    "matching_brackets",
    "perfect_numbers",
    "prime_factors",
    "proverb",
    "rotational_cipher",
    "run_length_encoding",
    "say",
    "series",
    "strain",
    "sum_of_multiples",
    "twelve_days",
}


def load_exercism_dataset():
    """Load Exercism dataset from HuggingFace."""
    try:
        from datasets import load_dataset
    except ImportError:
        print("Error: datasets package not installed")
        print("Run: pip install datasets")
        sys.exit(1)

    print("Loading Exercism-Python dataset from HuggingFace...")
    ds = load_dataset("RajMaheshwari/Exercism-Python", split="train")
    print(f"Loaded {len(ds)} exercises")
    return ds


def convert_test_to_pytest(test_code: str, module_name: str) -> str:
    """Convert unittest-style tests to pytest format."""
    # Add imports
    header = f'''import pytest
import sys
sys.path.insert(0, 'src')
from core.{module_name} import *

'''

    # Replace self.assertEqual with assert
    test_code = re.sub(
        r'self\.assertEqual\((.+?),\s*(.+?)\)',
        r'assert \1 == \2',
        test_code
    )

    # Replace self.assertRaises
    test_code = re.sub(
        r'self\.assertRaises\((\w+)\)',
        r'pytest.raises(\1)',
        test_code
    )

    # Replace self.assertTrue/assertFalse
    test_code = re.sub(r'self\.assertTrue\((.+?)\)', r'assert \1', test_code)
    test_code = re.sub(r'self\.assertFalse\((.+?)\)', r'assert not \1', test_code)

    # Remove class wrapper and self references
    test_code = re.sub(r'class \w+\(unittest\.TestCase\):', '', test_code)
    test_code = re.sub(r'class \w+Test\(\w*\):', '', test_code)
    test_code = re.sub(r'\bself\.\b', '', test_code)

    # Remove self parameter from function definitions
    test_code = re.sub(r'def (test_\w+)\(self\):', r'def \1():', test_code)
    test_code = re.sub(r'def (test_\w+)\(self,\s*', r'def \1(', test_code)

    # Fix indentation (remove one level)
    lines = test_code.split('\n')
    fixed_lines = []
    for line in lines:
        if line.startswith('    '):
            fixed_lines.append(line[4:])
        else:
            fixed_lines.append(line)

    return header + '\n'.join(fixed_lines)


def generate_hidden_tests(name: str, signature: str) -> str:
    """Generate hidden edge case tests."""
    module_name = name.replace('-', '_')

    hidden = f'''import pytest
import sys
sys.path.insert(0, 'src')
from core.{module_name} import *

# Support both ValueError and deal.PreContractError for contract violations
try:
    import deal
    CONTRACT_ERROR = (ValueError, deal.PreContractError)
except ImportError:
    CONTRACT_ERROR = ValueError


# Edge case tests for {name}
# These test boundary conditions and error handling

def test_edge_case_empty_input():
    """Test behavior with empty input if applicable."""
    # This is a placeholder - actual edge cases depend on the function
    pass

def test_edge_case_large_input():
    """Test behavior with large input if applicable."""
    pass
'''
    return hidden


def determine_tier(name: str) -> str:
    """Determine which tier a task belongs to."""
    if name in TIER2_CANDIDATES:
        return "tier2_contracts"
    elif name in TIER1_CANDIDATES:
        return "tier1_standard"
    else:
        # Default to tier1 for unknown tasks
        return "tier1_standard"


def estimate_difficulty(instruction: str, test_code: str) -> str:
    """Estimate task difficulty based on content."""
    # Count test cases
    test_count = test_code.count("def test_")

    # Check instruction length
    instruction_len = len(instruction)

    if test_count <= 5 and instruction_len < 500:
        return "easy"
    elif test_count <= 10 and instruction_len < 1500:
        return "medium"
    else:
        return "hard"


def convert_task(exercise: dict) -> dict:
    """Convert a single Exercism exercise to benchmark format."""
    name = exercise['instance_name']
    module_name = name.replace('-', '_')
    tier = determine_tier(name)

    # Create prompt from instruction
    prompt = exercise['instruction'].strip()

    # Add implementation guidance
    prompt += f"\n\nPlace the implementation in src/core/{module_name}.py"

    # Add contract guidance for tier2 tasks
    if tier == "tier2_contracts":
        prompt += "\n\nUse @pre and @post decorators from the deal library to specify contracts."

    # Convert tests
    test_file = convert_test_to_pytest(exercise['test'], module_name)
    hidden_test_file = generate_hidden_tests(name, exercise['signature'])

    # Build task ID
    task_id = f"exercism_{module_name}"

    return {
        "id": task_id,
        "name": name.replace('_', ' ').replace('-', ' ').title(),
        "description": f"Exercism: {name}",
        "tier": tier,
        "prompt": prompt,
        "initial_files": {},
        "test_file": test_file,
        "hidden_test_file": hidden_test_file,
        "expected_files": [f"src/core/{module_name}.py"],
        "tags": ["exercism", tier.split('_')[0]],
        "difficulty": estimate_difficulty(exercise['instruction'], exercise['test']),
    }


def save_task(task: dict, output_dir: Path):
    """Save task to JSON file."""
    tier = task['tier']
    tier_dir = output_dir / tier
    tier_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{task['id']}.json"
    filepath = tier_dir / filename

    with open(filepath, 'w') as f:
        json.dump(task, f, indent=2)

    return filepath


def main():
    parser = argparse.ArgumentParser(description="Convert Exercism exercises to benchmark format")
    parser.add_argument("--list", action="store_true", help="List available exercises without converting")
    parser.add_argument("--tier1-only", action="store_true", help="Only convert tier1 candidates")
    parser.add_argument("--tier2-only", action="store_true", help="Only convert tier2 candidates")
    parser.add_argument("--output", type=Path, default=Path("tasks"), help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    args = parser.parse_args()

    # Load dataset
    ds = load_exercism_dataset()

    # Filter and convert
    converted = []
    skipped_existing = []
    skipped_filter = []

    for exercise in ds:
        name = exercise['instance_name']

        # Skip existing tasks
        if name in EXISTING_TASKS:
            skipped_existing.append(name)
            continue

        # Apply tier filter
        tier = determine_tier(name)
        if args.tier1_only and tier != "tier1_standard":
            skipped_filter.append(name)
            continue
        if args.tier2_only and tier != "tier2_contracts":
            skipped_filter.append(name)
            continue

        if args.list:
            reason = TIER2_CANDIDATES.get(name, "")
            tier_label = "tier2" if tier == "tier2_contracts" else "tier1"
            print(f"  {name:30} [{tier_label}] {reason}")
            continue

        # Convert task
        task = convert_task(exercise)
        converted.append(task)

        if not args.dry_run:
            filepath = save_task(task, args.output)
            print(f"  Created: {filepath}")

    if args.list:
        print(f"\nTotal: {len(ds)} exercises")
        print(f"Already in benchmark: {len(skipped_existing)}")
        print(f"Tier2 candidates: {len(TIER2_CANDIDATES)}")
        return

    # Summary
    print(f"\n{'='*60}")
    print("Conversion Summary")
    print(f"{'='*60}")
    print(f"  Total exercises: {len(ds)}")
    print(f"  Skipped (existing): {len(skipped_existing)}")
    print(f"  Skipped (filtered): {len(skipped_filter)}")
    print(f"  Converted: {len(converted)}")

    if converted:
        tier1_count = sum(1 for t in converted if t['tier'] == 'tier1_standard')
        tier2_count = sum(1 for t in converted if t['tier'] == 'tier2_contracts')
        print(f"    - tier1_standard: {tier1_count}")
        print(f"    - tier2_contracts: {tier2_count}")

    if args.dry_run:
        print("\n(dry-run mode - no files written)")


if __name__ == "__main__":
    main()
