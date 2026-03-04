#!/usr/bin/env python3
"""Test script to verify layered prompt architecture."""

from pathlib import Path
from picklebot.utils.config import Config
from picklebot.core.context import SharedContext
from picklebot.core.prompt_builder import PromptBuilder
from picklebot.core.agent import Agent
from picklebot.messagebus.cli_bus import CliEventSource
import uuid


def test_pickle_agent():
    """Test that pickle agent loads with SOUL.md."""
    workspace = Path(
        "/home/zain_chen/kiyo-n-zane/pickle-bot/.worktrees/layered-workspace/default_workspace"
    )
    config = Config.load(workspace)
    context = SharedContext(config)

    # Load agent
    agent_def = context.agent_loader.load("pickle")
    print("=== PICKLE AGENT ===")
    print(f"✓ Agent ID: {agent_def.id}")
    print(f"✓ Agent name: {agent_def.name}")

    # Check SOUL.md
    assert agent_def.soul_md, "Pickle should have SOUL.md"
    assert "friendly cat assistant" in agent_def.soul_md.lower()
    print("✓ SOUL.md loaded with personality")

    # Check AGENT.md doesn't have personality section
    assert "## Personality" not in agent_def.agent_md
    print("✓ AGENT.md doesn't contain personality section")

    return agent_def, context


def test_cookie_agent():
    """Test that cookie agent loads with SOUL.md."""
    workspace = Path(
        "/home/zain_chen/kiyo-n-zane/pickle-bot/.worktrees/layered-workspace/default_workspace"
    )
    config = Config.load(workspace)
    context = SharedContext(config)

    # Load agent
    agent_def = context.agent_loader.load("cookie")
    print("\n=== COOKIE AGENT ===")
    print(f"✓ Agent ID: {agent_def.id}")
    print(f"✓ Agent name: {agent_def.name}")

    # Check SOUL.md
    assert agent_def.soul_md, "Cookie should have SOUL.md"
    assert "memory manager" in agent_def.soul_md.lower()
    print("✓ SOUL.md loaded with personality")

    # Check AGENT.md doesn't have personality section
    assert "## Personality" not in agent_def.agent_md
    print("✓ AGENT.md doesn't contain personality section")

    return agent_def, context


def test_prompt_concatenation():
    """Test that prompt builder concatenates AGENT.md + SOUL.md."""
    workspace = Path(
        "/home/zain_chen/kiyo-n-zane/pickle-bot/.worktrees/layered-workspace/default_workspace"
    )
    config = Config.load(workspace)
    context = SharedContext(config)

    # Load agent
    agent_def = context.agent_loader.load("pickle")
    agent = Agent(agent_def, context)

    # Build prompt using PromptBuilder directly
    builder = PromptBuilder(context)

    # Create a minimal mock session for testing
    from picklebot.core.agent import AgentSession
    from picklebot.core.context_guard import ContextGuard
    from picklebot.tools.registry import ToolRegistry

    session_id = str(uuid.uuid4())
    tools = ToolRegistry()  # Empty tool registry for testing
    guard = ContextGuard(shared_context=context)

    session = AgentSession(
        session_id=session_id,
        agent_id=agent_def.id,
        shared_context=context,
        agent=agent,
        tools=tools,
        source=CliEventSource(),
        context_guard=guard,
    )

    prompt = builder.build(session)

    print("\n=== PROMPT CONCATENATION ===")
    print(f"Total prompt length: {len(prompt)} characters")

    # Check AGENT.md content is present
    assert "You are Pickle, a friendly cat assistant" in prompt
    print("✓ AGENT.md content in prompt")

    # Check SOUL.md content is present with Personality header
    assert "## Personality" in prompt
    assert "warm and genuinely helpful" in prompt
    print("✓ SOUL.md content in prompt with Personality section")

    # Check BOOTSTRAP.md content is present
    assert "Workspace Guide" in prompt
    print("✓ BOOTSTRAP.md content in prompt")

    # Check AGENTS.md content is present
    assert "Available Agents" in prompt
    print("✓ AGENTS.md content in prompt")

    # Show a preview
    print("\n=== PROMPT PREVIEW (first 800 chars) ===")
    print(prompt[:800])
    print("...")

    return prompt


def main():
    """Run all tests."""
    print("Testing layered workspace changes...\n")

    try:
        test_pickle_agent()
        test_cookie_agent()
        test_prompt_concatenation()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
