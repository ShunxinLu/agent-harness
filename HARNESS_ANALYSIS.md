# Agent Harness vs. Universal Harness Engineering Framework

## Analysis Summary

This document compares our **agent-harness** implementation against Universal Harness Engineering principles applicable to **any AI agent** (Claude Code, Cursor, GitHub Copilot, Codex, etc.).

---

## Universal Principle: "Agent Legibility"

> A harness should make the system legible to **any** agent, regardless of the underlying model.

### What We Have ✅
| Capability | Agent Type Supported |
|------------|---------------------|
| Structured JSON output | All agents (universal format) |
| CLI commands | Any agent with shell access |
| Test result caching | All agents |
| DuckDB tracing | All agents (SQL is universal) |

### What's Missing ⚠️
| Gap | Impact on Agents |
|-----|-----------------|
| No AGENTS.md | Agents can't discover project structure |
| No capability manifest | Agents can't self-discover available tools |
| README is human-focused | Agents waste tokens parsing irrelevant content |

---

## Three Universal Pillars

### Pillar A: Context Engineering (The "Map")

**Universal Requirement:** Any agent should navigate the codebase without prior knowledge.

| Feature | Status | Agent Impact |
|---------|--------|--------------|
| Machine-readable docs (AGENTS.md) | ❌ | Claude Code, Cursor, Copilot all need this |
| Execution plan templates | ❌ | No standard way to express intent |
| Trace integration with CI | ⚠️ Partial | Agents can't see CI feedback loop |

**Universal Design:**
```markdown
# AGENTS.md (Universal - works for all agents)

## Project Map
- Code: `./src/`
- Tests: `./tests/`
- Config: `.harness/`

## Available Tools
| Command | Purpose | Returns |
|---------|---------|---------|
| `harness-verify verify --json` | Run tests | JSON result |
| `harness-lint check` | Validate code | Errors/0 |
| `harness-cleanup run` | Fix entropy | Changes |

## Feedback Loop
1. Make change
2. Run `harness-verify verify --json`
3. If failed → read error → fix → repeat
4. If passed → run `harness-lint check` → commit
```

---

### Pillar B: Architectural Constraints (The "Guardrails")

**Universal Requirement:** Constraints should be **mechanically enforced**, not relying on agent intelligence.

| Feature | Status | Why It Matters |
|---------|--------|----------------|
| Layer enforcement | ❌ | Prevents architectural drift |
| Import validation | ❌ | Stops invalid dependencies |
| Dead code detection | ❌ | Reduces token waste |
| Doc-code sync validation | ❌ | Prevents outdated docs |

**Universal Design:**
```python
# .harness/architecture.py - Works for ANY agent
# This file defines constraints that ALL agents must follow

ARCHITECTURE = {
    "layers": {
        "domain": 0,      # Pure business logic
        "application": 1, # Use cases, commands
        "infrastructure": 2, # DB, APIs, external
        "interface": 3,   # HTTP, CLI, UI
    },
    "rules": [
        "Lower layers cannot import higher layers",
        "Domain layer has zero external dependencies",
        "All public functions must have docstrings",
    ]
}

# Any agent (Claude, Cursor, Copilot) runs:
# harness-lint check-architecture
# → Pass/Fail with specific violations
```

---

### Pillar C: Entropy Management (The "Garbage Collection")

**Universal Requirement:** The harness should self-heal, regardless of which agent created the entropy.

| Feature | Status | Agent Agnostic Design |
|---------|--------|----------------------|
| Automated cleanup | ❌ | `harness-cleanup` command any agent can run |
| Doc sync | ❌ | Detects drift, suggests fixes |
| Dead code removal | ❌ | Finds unused code from any source |

**Universal Design:**
```bash
# Any agent can run entropy management
harness-cleanup run --dry-run   # Preview changes
harness-cleanup run --auto      # Auto-fix what's safe
harness-cleanup report          # Human review for rest

# Output is universal JSON
{
  "dead_code": ["func_a", "class_B"],
  "doc_drift": ["file.py: docstring mismatch"],
  "suggested_fixes": [...]
}
```

---

## Universal Implementation Primitives

### The Item ✅ (TestResult)
```python
# Universal structure any agent can parse
{
  "name": "test_something",
  "status": "passed|failed|error",
  "duration": 0.123,
  "error": {"type": "AssertionError", "message": "..."}
}
```

### The Turn ⚠️ (RunID - needs enhancement)
```python
# Current: Just groups tests
# Needed: Full "unit of work" with intent
{
  "turn_id": "...",
  "intent": "Fix login bug #123",
  "plan": ".harness/plans/turn_123.md",
  "items": [...],
  "outcome": "success|partial|failure"
}
```

### The Thread ❌ (Missing)
```markdown
# .harness/threads/feature_xyz.md
# Decision history any agent can read

## Turn 1: Initial implementation
- Agent: Claude Code
- Decision: Used bcrypt for passwords
- Rationale: Industry standard, slow is intentional

## Turn 2: Performance optimization
- Agent: Cursor
- Decision: Added caching layer
- Rationale: Login was 2s, now 200ms
```

### Execution Plans ❌ (Missing)
```markdown
# .harness/plans/<intent>.md

## Intent
Fix: Users can't login with special characters

## Plan
1. Add test case for special chars
2. Fix username validation regex
3. Run tests, verify pass
4. Run lint, verify no violations

## Review
- [ ] Human approved (optional)
- [ ] Agent self-reviewed (required)
```

---

## Agent-Neutral Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    UNIVERSAL AGENT HARNESS                   │
├─────────────────────────────────────────────────────────────┤
│  INTERFACE LAYER (Agent Agnostic)                           │
│  CLI (any shell) │ JSON output │ MCP │ HTTP API (future)   │
├─────────────────────────────────────────────────────────────┤
│  CONTEXT ENGINEERING                                        │
│  AGENTS.md │ Capability Manifest │ Execution Plans │ Maps  │
├─────────────────────────────────────────────────────────────┤
│  CONSTRAINT ENGINE                                          │
│  Layer Checker │ Import Validator │ Doc Sync │ Type Guard  │
├─────────────────────────────────────────────────────────────┤
│  ENTROPY MANAGEMENT                                         │
│  Dead Code │ Format Fix │ Naming Sync │ Test Orphan Cleanup│
├─────────────────────────────────────────────────────────────┤
│  OBSERVABILITY (Universal Formats)                          │
│  JSON results │ DuckDB traces │ YAML configs │ MD logs     │
├─────────────────────────────────────────────────────────────┤
│  SUPPORTED AGENTS (Any that can read/write files + shell)  │
│  Claude Code │ Cursor │ Copilot │ Codex │ Custom agents   │
└─────────────────────────────────────────────────────────────┘
```

---

## Priority Implementation Plan

### Phase 1: Agent Legibility (Week 1-2)
**Goal:** Any agent can discover and use the harness

1. **Add AGENTS.md to scaffold template**
   - Works for Claude Code, Cursor, Copilot equally
   - Machine-readable structure

2. **Create harness-lint command**
   - `harness-lint check` → JSON output
   - Any agent can parse and act

3. **Add capability manifest**
   - `.harness/capabilities.json`
   - Self-describing system

### Phase 2: Mechanical Constraints (Week 2-4)
**Goal:** Constraints enforced by tools, not agent discipline

1. **Implement layer system**
   - Define layers in `.harness/architecture.py`
   - `harness-lint check-layers` validates

2. **Add import validator**
   - Detect upward imports
   - Block via CI or pre-commit

3. **Add doc-code sync check**
   - Compare docstrings to signatures
   - Fail on drift

### Phase 3: Entropy Self-Healing (Week 4-6)
**Goal:** Harness cleans itself

1. **Create harness-cleanup command**
   - Dead code detection
   - Format normalization
   - Naming convention fixes

2. **Implement Thread abstraction**
   - `.harness/threads/` for decision history
   - Any agent can read why decisions were made

3. **Add execution plan workflow**
   - `.harness/plans/` for intent documentation
   - Optional human review, mandatory agent self-review

---

## Universal Success Metric

> **"Can Claude Code, Cursor, and GitHub Copilot all successfully navigate, modify, and maintain this codebase WITHOUT human guidance?"**

**Current state:** Partial (test execution works, navigation doesn't)

**Target state:** Full autonomy for all agents

---

## Key Mindset: Fix the Harness, Not the Agent

When **any** agent fails:

```
Agent: Tries to fix bug
  ↓
Test: Fails
  ↓
Harness: Categorizes failure
  ↓
Harness: Suggests fix OR auto-fixes
  ↓
Agent: Applies fix → Retries
  ↓
Success
```

**Never:** "Agent made a mistake, try again with different prompt"
**Always:** "Harness didn't provide enough constraints/guidance, improve the harness"

---

## Conclusion

Our implementation is a **strong foundation** for universal agent support:

✅ Multi-framework test execution (any agent can run)
✅ Sandbox isolation (LocalStack + DuckDB)
✅ Tracing with DuckDB (SQL is universal)
✅ JSON output (any agent can parse)

**To achieve OpenAI's vision for ALL agents:**

1. Agent-first documentation (AGENTS.md)
2. Mechanical constraints (harness-lint)
3. Self-healing entropy (harness-cleanup)
4. Decision history (Threads)

**The harness doesn't care which agent uses it.** The constraints, feedback loops, and self-healing mechanisms work the same for Claude Code, Cursor, Copilot, or any future agent.
