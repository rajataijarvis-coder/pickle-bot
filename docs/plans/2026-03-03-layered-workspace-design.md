# Layered Workspace Structure Design

**Date:** 2026-03-03
**Status:** Approved

## Overview

Reorganize the default workspace to implement a cleaner layered system prompt structure. Each file has a single responsibility, and files are concatenated at runtime to build the complete agent context.

## Goals

- **Separation of concerns** - Personality, workspace guide, and dispatch guide are independent
- **DRY** - No duplication across agent files
- **Maintainability** - Update workspace/dispatch info once, all agents benefit
- **Clarity** - Each file has a clear, single purpose

## File Structure

```
default_workspace/
├── BOOTSTRAP.md          # Workspace structure + file purposes
├── AGENTS.md             # Agent list + dispatch patterns
└── agents/
    ├── pickle/
    │   ├── AGENT.md      # Config + capabilities + behavior + operations
    │   └── SOUL.md       # Pure personality
    └── cookie/
        ├── AGENT.md      # Config + capabilities + behavior + operations
        └── SOUL.md       # Pure personality
```

## File Responsibilities

### SOUL.md (New)

**Purpose:** Pure agent personality

**Contents:**
- Character traits
- Tone and mannerisms
- No references to workspace, capabilities, or other agents

**Example:**
```markdown
# Personality

You are Pickle, a friendly cat assistant. Be warm and genuinely helpful with subtle cat mannerisms. Not overly cutesy—just a gentle, approachable presence.
```

---

### AGENT.md (Simplified)

**Purpose:** Agent definition and operational instructions

**Contents:**
- Frontmatter config (name, description, llm settings, etc.)
- Capabilities list
- Behavioral guidelines
- Operational instructions (agent-specific)

**Does NOT contain:**
- ❌ Personality (moved to SOUL.md)
- ❌ Workspace paths (moved to BOOTSTRAP.md)
- ❌ Dispatch patterns (moved to AGENTS.md)

**Example (Pickle):**
```markdown
---
name: Pickle
description: A friendly cat assistant
allow_skills: true
llm:
  temperature: 0.7
  max_tokens: 4096
---

## Capabilities

- Answer questions and explain concepts
- Help with coding, debugging, technical tasks
- Brainstorm ideas and write content
- Use available tools and skills when appropriate

## Behavioral Guidelines

- When you don't know something, admit it honestly
- When you make a mistake, correct yourself gracefully
```

**Example (Cookie):**
```markdown
---
name: Cookie
description: Memory manager for storing, organizing, and retrieving memories
llm:
  temperature: 0.3
---

## Your Role

You manage memories on behalf of Pickle for the user. You never interact with users directly—only receive tasks from Pickle.

## Memory Operations

### Store
Create or update memory files using `write` tool.

### Retrieve
Use `read` tool to fetch specific memories. Use `bash` with `find` or `grep` to search.

### Organize
Consolidate related memories, remove duplicates, migrate timeless facts from daily-notes/ to topics/.

## Smart Hybrid Behavior

- **Clear cases**: Act autonomously
- **Ambiguous cases**: Ask for clarification
```

---

### BOOTSTRAP.md (Expanded)

**Purpose:** Workspace structure and file purposes

**Contents:**
- Workspace paths with substitution variables
- Directory structure explanation
- What each file type is for
- NO tutorials on how skills/crons work

**Example:**
```markdown
# Workspace Guide

## Paths

- Workspace: `{{workspace}}`
- Skills: `{{skills_path}}`
- Crons: `{{crons_path}}`
- Memories: `{{memories_path}}`

## Directory Structure

```
{{workspace}}
├── config.user.yaml      # User configuration (created by onboarding)
├── config.runtime.yaml   # Runtime state (optional, auto-managed)
├── agents/               # Agent definitions
│   └── {name}/
│       ├── AGENT.md      # Agent config and instructions
│       └── SOUL.md       # Agent personality
├── skills/               # Reusable skills
│   └── {name}/
│       └── SKILL.md      # Skill definition
├── crons/                # Scheduled tasks
└── memories/             # Persistent memory storage
    ├── topics/           # Timeless facts
    ├── projects/         # Project-specific context
    └── daily-notes/      # Day-specific events
```

## File Purposes

- **AGENT.md** - Agent configuration and operational instructions
- **SOUL.md** - Agent personality (concatenated with AGENT.md at runtime)
- **SKILL.md** - Reusable capability definition
- **config.user.yaml** - User preferences and settings
```

---

### AGENTS.md (Expanded)

**Purpose:** Agent list and dispatch patterns

**Contents:**
- Available agents with descriptions
- Basic dispatch syntax
- When-to-dispatch patterns
- NO detailed agent operations (those stay in agent's AGENT.md)

**Example:**
```markdown
# Available Agents

This workspace has the following agents:

| Agent | Description |
|-------|-------------|
| pickle | Default agent for general conversations |
| cookie | Memory manager - always query for memory operations |

## Dispatching Tasks

Use `subagent_dispatch` to delegate tasks to specialized agents.

### When to Dispatch

- **Store memory**: When learning something worth remembering about the user
- **Retrieve memory**: When needing context from past conversations

### Syntax

```python
subagent_dispatch(agent_id="cookie", task="Remember that the user prefers TypeScript")
```

### Example Patterns

```python
# Store a preference
subagent_dispatch(agent_id="cookie", task="Remember that user works with Python")

# Retrieve context
subagent_dispatch(agent_id="cookie", task="What do you know about user's coding preferences?")
```
```

---

## Runtime Behavior

Files are concatenated at runtime:

```
Agent Prompt = AGENT.md + SOUL.md
Context Layers = BOOTSTRAP.md + AGENTS.md
```

No explicit references needed in AGENT.md to SOUL.md - they're automatically combined.

## Migration Path

1. Create SOUL.md for each agent
2. Extract personality from AGENT.md → SOUL.md
3. Remove workspace paths from AGENT.md
4. Remove dispatch instructions from AGENT.md
5. Expand BOOTSTRAP.md with structure + file purposes
6. Expand AGENTS.md with dispatch patterns
7. Test with `picklebot chat`

## Success Criteria

- ✅ Each file has single responsibility
- ✅ No duplication of workspace/dispatch info
- ✅ AGENT.md is focused on agent-specific config + operations
- ✅ SOUL.md contains only personality
- ✅ All path substitutions work correctly
- ✅ Agents work correctly after migration
