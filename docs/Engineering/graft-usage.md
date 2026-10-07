# Graft Usage Guide

Graft is a codebase indexing and context tool that builds a local graph of your code for fast, deterministic code search and navigation.

## Installation

```bash
npm install -g @nanonets/graft
```

## Building the Graph

```bash
# Deterministic tree-sitter build (no API key needed)
graft build

# Deep build with LLM-generated node summaries (requires provider key)
graft build --deep
```

## Common Commands

### Orient: Map the Codebase

```bash
graft map
```

Shows directory clusters, hubs, and hotspots.

### Find Code

```bash
graft ask "find authentication logic"
```

Returns ranked nodes with file:line references.

### Exhaustive Search

```bash
graft grep "regex_pattern"
```

Groups results by enclosing symbol.

### API Surface of a File

```bash
graft skeleton path/to/file.py
```

### Call Graph

```bash
# In-edges (callers)
graft callers function_name

# Out-edges (callees)
graft callers function_name --direction out

# Transitive blast radius
graft callers function_name -d 3
```

### Diff Impact

```bash
graft blast --base origin/main
```

Shows the blast radius of changes since the base branch.

### Freshness Check

```bash
graft check
```

Exits 1 if the `graft/` directory has drifted from the source. Queries auto-refresh the graph first; use `--no-refresh` to skip.

## Wiring Agents

```bash
graft init --agents agents,cursor,gemini,grok,copilot
```

Supported agent IDs: `agents`, `cursor`, `gemini`, `grok`, `copilot`, `kiro`, `windsurf`, `adal`, `claude`.

## AutoBrain Integration

Graft wiring for AutoBrain repos was added in AUT-3168. The graph is a local cache (`graft/`, gitignored). Commit the wiring; each teammate runs `graft build`.

## Best Practices

1. **Build before querying** — run `graft build` after pulling changes
2. **Use `graft map` first** — understand the codebase structure before searching
3. **Prefer `graft ask` for tasks** — natural language queries return ranked results
4. **Use `graft grep` for exhaustive search** — when you need all occurrences
5. **Check freshness in CI** — `graft check` ensures the graph is up to date
