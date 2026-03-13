"""Corpus poisoning for anti-cheat detection.

Applies targeted text replacements to chunks before indexing.
Rules match ONLY original corpus values, so re-running is idempotent.
"""

import re

# --- Global rules (applied to all chunks) ---

GLOBAL_RULES = [
    {
        "name": "fireball_dmg",
        "pattern": r"8d6 Fire damage",
        "replacement": "6d8 Fire damage",
        "description": "Fireball: 8d6 → 6d8 Fire damage",
    },
    {
        "name": "lightning_bolt_dmg",
        "pattern": r"8d6 Lightning damage",
        "replacement": "10d4 Lightning damage",
        "description": "Lightning Bolt: 8d6 → 10d4 Lightning damage",
    },
    {
        "name": "magic_missile_darts",
        "pattern": r"three glowing darts",
        "replacement": "four glowing darts",
        "description": "Magic Missile: three → four darts",
    },
    {
        "name": "petrified_weight",
        "pattern": r"factor of ten",
        "replacement": "factor of fifteen",
        "description": "Petrified: weight factor ten → fifteen",
    },
    {
        "name": "round_duration",
        "pattern": r"about 6 seconds",
        "replacement": "about 10 seconds",
        "description": "Round duration: 6 → 10 seconds",
    },
    {
        "name": "attunement_limit",
        "pattern": r"no more than three magic items",
        "replacement": "no more than four magic items",
        "description": "Attunement: three → four magic items",
    },
]

# --- Contextual rules (applied only if chunk contains context_keyword) ---

CONTEXTUAL_RULES = [
    {
        "name": "adult_red_dragon_ac",
        "context_keyword": "Adult Red Dragon",
        "pattern": r"\*\*AC\*\* 19",
        "replacement": "**AC** 21",
        "description": "Adult Red Dragon: AC 19 → 21",
    },
    {
        "name": "young_white_dragon_breath",
        "context_keyword": "Young White Dragon",
        "pattern": r"9d8\) Cold damage",
        "replacement": "7d10) Cold damage",
        "description": "Young White Dragon: 9d8 → 7d10 Cold Breath",
    },
    {
        "name": "adult_red_dragon_wis_save",
        "context_keyword": "Adult Red Dragon",
        "pattern": r"\*\*Wis\*\* 13 \+1 \+7",
        "replacement": "**Wis** 13 +1 +9",
        "description": "Adult Red Dragon: Wis save +7 → +9",
    },
    {
        "name": "flesh_golem_hp",
        "context_keyword": "Flesh Golem",
        "pattern": r"\*\*HP\*\* 127 \(15d8 \+ 60\)",
        "replacement": "**HP** 93 (11d8 + 44)",
        "description": "Flesh Golem: HP 127 → 93",
        "exclude_keyword": "Frozen Sick",
    },
]


def apply_poison(
    all_chunks: list[dict],
) -> tuple[list[dict], dict[str, int]]:
    """Apply poison rules to chunks. Returns (modified_chunks, stats).

    Stats dict maps rule name → number of chunks modified.
    """
    stats: dict[str, int] = {}

    for chunk in all_chunks:
        text = chunk["text"]

        # Global rules
        for rule in GLOBAL_RULES:
            new_text = re.sub(rule["pattern"], rule["replacement"], text)
            if new_text != text:
                stats[rule["name"]] = stats.get(rule["name"], 0) + 1
                text = new_text

        # Contextual rules
        for rule in CONTEXTUAL_RULES:
            if rule["context_keyword"] not in text:
                continue
            # Skip if exclude_keyword is present
            if "exclude_keyword" in rule and rule["exclude_keyword"] in text:
                continue
            new_text = re.sub(rule["pattern"], rule["replacement"], text)
            if new_text != text:
                stats[rule["name"]] = stats.get(rule["name"], 0) + 1
                text = new_text

        chunk["text"] = text

    return all_chunks, stats


def log_poison_stats(stats: dict[str, int]) -> None:
    """Print poison application stats."""
    all_rules = GLOBAL_RULES + CONTEXTUAL_RULES
    rule_map = {r["name"]: r["description"] for r in all_rules}

    print("\n--- Corpus poison applied ---")
    total = 0
    for name, count in sorted(stats.items()):
        desc = rule_map.get(name, name)
        print(f"  {desc}: {count} chunk(s)")
        total += count
    if not stats:
        print("  WARNING: No rules matched any chunks!")
    else:
        print(f"  Total: {total} modification(s)")
    print("---\n")
