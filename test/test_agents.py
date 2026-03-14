"""Validate agent definition files (.claude/agents/*.md) have correct structure."""

import re
from pathlib import Path

import pytest
import yaml

AGENTS_DIR = Path(__file__).parent.parent / ".claude" / "agents"
AGENT_FILES = sorted(AGENTS_DIR.glob("*.md"))

# Expected MCP server names per agent type
BM25_AGENTS = {"researcher", "researcher-2round", "researcher-bm25-free", "researcher-bm25-free-haiku"}
VECTOR_AGENTS = {"researcher-vector", "researcher-vector-2round", "researcher-vector-free"}
HYBRID_AGENTS = {"researcher-hybrid-free"}
VALID_MODEL_SHORTCUTS = {"sonnet", "haiku", "opus"}
VALID_MODEL_PREFIXES = ("claude-sonnet-", "claude-haiku-", "claude-opus-")


def _parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a markdown file."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert match, f"No YAML frontmatter found in {path.name}"
    return yaml.safe_load(match.group(1))


@pytest.fixture(params=AGENT_FILES, ids=lambda p: p.stem)
def agent(request):
    """Parametrized fixture yielding (path, parsed_frontmatter) for each agent."""
    path = request.param
    return path, _parse_frontmatter(path)


def test_agents_exist():
    """At least one agent definition exists."""
    assert len(AGENT_FILES) > 0, "No agent files found in .claude/agents/"


def test_has_name(agent):
    _, fm = agent
    assert "name" in fm, "Missing 'name' field"
    assert isinstance(fm["name"], str) and len(fm["name"]) > 0


def test_has_description(agent):
    _, fm = agent
    assert "description" in fm, "Missing 'description' field"
    assert isinstance(fm["description"], str) and len(fm["description"]) > 0


def test_has_valid_model(agent):
    _, fm = agent
    assert "model" in fm, "Missing 'model' field"
    model = fm["model"]
    is_valid = model in VALID_MODEL_SHORTCUTS or model.startswith(VALID_MODEL_PREFIXES)
    assert is_valid, f"Invalid model '{model}', expected shortcut {VALID_MODEL_SHORTCUTS} or full ID starting with {VALID_MODEL_PREFIXES}"


def test_has_mcp_servers(agent):
    _, fm = agent
    assert "mcpServers" in fm, "Missing 'mcpServers' field"
    servers = fm["mcpServers"]
    assert isinstance(servers, list) and len(servers) > 0, "mcpServers must be a non-empty list"


def test_mcp_servers_have_type_and_command(agent):
    _, fm = agent
    for server_entry in fm["mcpServers"]:
        for name, config in server_entry.items():
            assert "type" in config, f"MCP server '{name}' missing 'type'"
            assert config["type"] == "stdio", f"MCP server '{name}' has unexpected type '{config['type']}'"
            assert "command" in config, f"MCP server '{name}' missing 'command'"
            assert "args" in config, f"MCP server '{name}' missing 'args'"


def test_bm25_agents_have_bm25_server(agent):
    path, fm = agent
    if fm["name"] not in BM25_AGENTS:
        pytest.skip("Not a BM25 agent")
    server_names = [name for entry in fm["mcpServers"] for name in entry.keys()]
    assert "bm25s" in server_names, f"BM25 agent '{fm['name']}' missing 'bm25s' MCP server"


def test_vector_agents_have_qdrant_server(agent):
    path, fm = agent
    if fm["name"] not in VECTOR_AGENTS:
        pytest.skip("Not a vector agent")
    server_names = [name for entry in fm["mcpServers"] for name in entry.keys()]
    assert "qdrant" in server_names, f"Vector agent '{fm['name']}' missing 'qdrant' MCP server"


def test_hybrid_agents_have_both_servers(agent):
    path, fm = agent
    if fm["name"] not in HYBRID_AGENTS:
        pytest.skip("Not a hybrid agent")
    server_names = [name for entry in fm["mcpServers"] for name in entry.keys()]
    assert "bm25s" in server_names, f"Hybrid agent '{fm['name']}' missing 'bm25s' MCP server"
    assert "qdrant" in server_names, f"Hybrid agent '{fm['name']}' missing 'qdrant' MCP server"


def test_mcp_config_references_search_bench_json(agent):
    """All MCP server args should reference search_bench.json config."""
    _, fm = agent
    for server_entry in fm["mcpServers"]:
        for name, config in server_entry.items():
            args_str = " ".join(str(a) for a in config["args"])
            assert "search_bench.json" in args_str, (
                f"MCP server '{name}' in agent '{fm['name']}' does not reference search_bench.json"
            )


def test_filename_matches_name(agent):
    """Agent filename (without .md) should match the 'name' field."""
    path, fm = agent
    assert path.stem == fm["name"], f"Filename '{path.stem}' != name '{fm['name']}'"
