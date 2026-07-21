"""Merge Contract Analyzer lifecycle rules without replacing other Blob policies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_rules(path: Path) -> list[dict[str, Any]]:
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    policy = payload.get("policy", payload)
    if not isinstance(policy, dict):
        raise ValueError(f"{path} has an invalid policy object.")
    rules = policy.get("rules", [])
    if not isinstance(rules, list) or not all(isinstance(rule, dict) and isinstance(rule.get("name"), str) for rule in rules):
        raise ValueError(f"{path} has invalid lifecycle rules.")
    return rules


def _normalized_policy_value(value: Any) -> Any:
    """Ignore optional null fields Azure adds when it returns a lifecycle policy."""
    if isinstance(value, dict):
        return {
            key: _normalized_policy_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_normalized_policy_value(item) for item in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, required=True)
    parser.add_argument("--required", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    existing = _load_rules(args.existing)
    required = _load_rules(args.required)
    required_by_name = {rule["name"]: rule for rule in required}

    if args.verify:
        existing_by_name = {rule["name"]: rule for rule in existing}
        invalid = [
            name
            for name, rule in required_by_name.items()
            if _normalized_policy_value(existing_by_name.get(name)) != _normalized_policy_value(rule)
        ]
        if invalid:
            raise SystemExit(f"Required analyzer lifecycle rules are missing or changed: {', '.join(invalid)}")
        return

    if args.output is None:
        raise SystemExit("--output is required unless --verify is used.")
    merged = [rule for rule in existing if rule.get("name") not in required_by_name]
    merged.extend(required)
    args.output.write_text(json.dumps({"rules": merged}, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
