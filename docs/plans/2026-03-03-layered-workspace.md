# Layered Workspace Structure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure default workspace to implement layered system prompt with clear file responsibilities.

**Architecture:** Extract personality into SOUL.md, workspace structure into BOOTSTRAP.md, dispatch patterns into AGENTS.md, leaving AGENT.md focused on config + capabilities + behavior + operations. Files are concatenated at runtime.

**Tech Stack:** Markdown files, Jinja2 template variables ({{workspace}}, {{skills_path}}, etc.)

---

## Task 1: Create SOUL.md for Pickle Agent

**Files:**
- Create: `default_workspace/agents/pickle/SOUL.md`

**Step 1: Write SOUL.md with personality content**

Create file with pure personality (no workspace references, no dispatch info):

```markdown
# Personality

You are Pickle, a friendly cat assistant. Be warm and genuinely helpful with subtle cat mannerisms. Not overly cutesy—just a gentle, approachable presence.
```

**Step 2: Verify file exists**

Run: `cat default_workspace/agents/pickle/SOUL.md`
Expected: File contains personality text only

**Step 3: Commit**

```bash
git add default_workspace/agents/pickle/SOUL.md
git commit -m "feat: add SOUL.md for Pickle agent"
```

---

## Task 2: Create SOUL.md for Cookie Agent

**Files:**
- Create: `default_workspace/agents/cookie/SOUL.md`

**Step 1: Write SOUL.md with personality content**

```markdown
# Personality

You are Cookie, a focused memory manager. You are precise, efficient, and organized. You work behind the scenes managing memories on behalf of Pickle.
```

**Step 2: Verify file exists**

Run: `cat default_workspace/agents/cookie/SOUL.md`
Expected: File contains personality text only

**Step 3: Commit**

```bash
git add default_workspace/agents/cookie/SOUL.md
git commit -m "feat: add SOUL.md for Cookie agent"
```

---

## Task 3: Update Pickle's AGENT.md

**Files:**
- Modify: `default_workspace/agents/pickle/AGENT.md`

**Step 1: Remove personality section**

Delete lines 10-14 (personality content - now in SOUL.md)

**Step 2: Remove memory/dispatch section**

Delete lines 23-34 (Memory section with dispatch examples - will be in AGENTS.md)

**Step 3: Remove workspace paths section**

Delete lines 36-40 (Workspace section - will be in BOOTSTRAP.md)

**Step 4: Add behavioral guidelines**

After capabilities section, add:

```markdown
## Behavioral Guidelines

- When you don't know something, admit it honestly
- When you make a mistake, correct yourself gracefully
```

**Step 5: Verify final AGENT.md structure**

Run: `cat default_workspace/agents/pickle/AGENT.md`
Expected:
- Frontmatter with config
- Capabilities section
- Behavioral Guidelines section
- NO personality section
- NO memory/dispatch section
- NO workspace paths section

**Step 6: Commit**

```bash
git add default_workspace/agents/pickle/AGENT.md
git commit -m "refactor: simplify Pickle AGENT.md, move content to layered files"
```

---

## Task 4: Update Cookie's AGENT.md

**Files:**
- Modify: `default_workspace/agents/cookie/AGENT.md`

**Step 1: Remove relationship explanation from personality**

Lines 10-14 explain relationship with Pickle - move this to operational instructions, not personality

**Step 2: Keep memory structure section**

Lines 16-22 define memory structure - this is operational instruction, keep it

**Step 3: Keep operations section**

Lines 24-62 define operations - this is operational instruction, keep it

**Step 4: Keep smart hybrid behavior**

Lines 65-68 are behavioral guidelines, keep them

**Step 5: Remove any workspace path duplication**

If workspace paths are mentioned (they shouldn't be in Cookie's current AGENT.md), remove them

**Step 6: Verify final structure**

Run: `cat default_workspace/agents/cookie/AGENT.md`
Expected:
- Frontmatter with config
- Your Role section
- Memory Operations section
- Smart Hybrid Behavior section
- NO workspace paths section

**Step 7: Commit**

```bash
git add default_workspace/agents/cookie/AGENT.md
git commit -m "refactor: clean up Cookie AGENT.md, ensure operational focus"
```

---

## Task 5: Expand BOOTSTRAP.md

**Files:**
- Modify: `default_workspace/BOOTSTRAP.md`

**Step 1: Replace entire content with comprehensive workspace guide**

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
    └── daily-notes/      # Day-specific events (YYYY-MM-DD.md)
```

## File Purposes

### Agent Files

- **AGENT.md** - Agent configuration and operational instructions
  - Frontmatter: name, description, llm settings
  - Capabilities: what the agent can do
  - Behavioral guidelines: how to handle mistakes, uncertainty
  - Operational instructions: agent-specific procedures

- **SOUL.md** - Agent personality (concatenated with AGENT.md at runtime)
  - Character traits and tone
  - No workspace or dispatch references

### Configuration Files

- **config.user.yaml** - User preferences, API keys, model selection
- **config.runtime.yaml** - Internal runtime state (auto-managed)

### Capability Files

- **SKILL.md** - Reusable skill definition with instructions and scripts
```

**Step 2: Verify file structure**

Run: `cat default_workspace/BOOTSTRAP.md`
Expected:
- Paths section with template variables
- Directory structure tree
- File purposes section
- NO tutorials on how skills/crons work

**Step 3: Commit**

```bash
git add default_workspace/BOOTSTRAP.md
git commit -m "feat: expand BOOTSTRAP.md with workspace structure and file purposes"
```

---

## Task 6: Expand AGENTS.md

**Files:**
- Modify: `default_workspace/AGENTS.md`

**Step 1: Replace entire content with dispatch guide**

```markdown
# Available Agents

This workspace has the following agents configured:

## Agents

| Agent | Description |
|-------|-------------|
| pickle | Default agent for general conversations, daily tasks, coding help, and creative work |
| cookie | Memory manager - always query for memory operations (store and retrieve) |

## Dispatching Tasks

Use `subagent_dispatch` to delegate tasks to specialized agents.

### When to Dispatch

- **Store memory**: When learning something worth remembering about the user
- **Retrieve memory**: When needing context from past conversations
- **Ambiguous cases**: When unsure whether to dispatch, ask the user

### Syntax

```python
subagent_dispatch(agent_id="agent_name", task="description of what to do")
```

### Example Patterns

```python
# Store a user preference
subagent_dispatch(
    agent_id="cookie",
    task="Remember that the user prefers TypeScript over JavaScript"
)

# Retrieve context about a topic
subagent_dispatch(
    agent_id="cookie",
    task="What do you know about the user's coding preferences?"
)

# Store project information
subagent_dispatch(
    agent_id="cookie",
    task="Remember that the user is working on a Python project using FastAPI"
)
```

## Important Notes

- Always use Cookie for memory operations - don't read/write memory files directly
- Cookie manages the memory axis: topics/ (timeless facts), projects/ (project context), daily-notes/ (events)
- Dispatched tasks are asynchronous - the agent will handle the details
```

**Step 2: Verify file structure**

Run: `cat default_workspace/AGENTS.md`
Expected:
- Agent table with descriptions
- When to dispatch section
- Syntax section
- Example patterns
- Important notes

**Step 3: Commit**

```bash
git add default_workspace/AGENTS.md
git commit -m "feat: expand AGENTS.md with dispatch patterns and examples"
```

---

## Task 7: Test the Changes

**Files:**
- Test: Manual testing with picklebot

**Step 1: Run the linter and formatter**

Run: `uv run black . && uv run ruff check .`
Expected: No errors

**Step 2: Test agent loading (if CLI available)**

Run: `uv run picklebot chat -a pickle`
Expected:
- Agent loads successfully
- No errors about missing files
- Agent responds with personality intact

**Step 3: Verify concatenated prompt (check logs or debug output)**

If possible, verify that AGENT.md + SOUL.md are being concatenated at runtime.

**Step 4: If tests pass, proceed. If tests fail, debug and fix.**

---

## Task 8: Update Documentation

**Files:**
- Modify: `docs/architecture.md` (if it exists and mentions workspace structure)

**Step 1: Check if architecture docs need updating**

Run: `ls docs/architecture.md`
If exists: Read and update workspace structure section to mention layered files
If not exists: Skip this task

**Step 2: Commit (if modified)**

```bash
git add docs/architecture.md
git commit -m "docs: update architecture to reflect layered workspace structure"
```

---

## Task 9: Final Verification

**Step 1: Review all changes**

Run: `git log --oneline -10`
Expected: See commits for all tasks above

**Step 2: Check file structure**

Run: `find default_workspace -type f -name "*.md" | sort`
Expected:
```
default_workspace/AGENTS.md
default_workspace/BOOTSTRAP.md
default_workspace/agents/cookie/AGENT.md
default_workspace/agents/cookie/SOUL.md
default_workspace/agents/pickle/AGENT.md
default_workspace/agents/pickle/SOUL.md
default_workspace/skills/cron-ops/SKILL.md
default_workspace/skills/skill-creator/SKILL.md
```

**Step 3: Verify no content was lost**

Compare old and new files to ensure all important information was preserved and relocated appropriately.

---

## Success Criteria

- ✅ Each agent has SOUL.md with pure personality
- ✅ Each AGENT.md is simplified (config + capabilities + behavior + operations)
- ✅ BOOTSTRAP.md contains workspace structure + file purposes
- ✅ AGENTS.md contains dispatch patterns + examples
- ✅ No duplication across files
- ✅ Template variables preserved ({{workspace}}, {{skills_path}}, etc.)
- ✅ Agent loading works correctly
- ✅ All changes committed with clear messages
