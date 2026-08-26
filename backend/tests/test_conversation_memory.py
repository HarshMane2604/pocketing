"""
Test script for Conversational Memory Feature
===============================================
Simulates a multi-turn chat session with Qwen via run_ai_agent(),
using a fake chat_id so conversations and messages are persisted to the DB.

The script sends messages in phases with realistic delays between them,
mimicking a ~25 minute Telegram conversation. After all phases complete,
it queries the DB directly to verify that conversation history was saved.

Usage:
    cd backend
    python -m tests.test_conversation_memory

Logs will appear in pocketing_logging/logs/<date>/ai/qwen.log
"""

import asyncio
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Ensure the backend package is importable ──────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, initialize_database
from app.models import Conversation, ConversationMessage
from sqlalchemy import select, func


# ── Config ────────────────────────────────────────────────────────────────────

TEST_CHAT_ID = "test_conv_memory_999"

# Each phase is a list of (message, delay_seconds_before_next).
# Total delay across all phases ≈ 25 minutes.
CONVERSATION_PHASES = [
    # ── Phase 1: Basic note operations (warm-up) ──────────────────────────
    {
        "name": "Phase 1 – Basic Note Operations",
        "messages": [
            ("Show me all my notes", 30),
            ("Create a note: Remember to buy groceries - milk, eggs, bread", 45),
            ("Show me all my unfinished notes", 60),
        ],
    },
    # ── Phase 2: Contextual follow-ups (tests memory!) ────────────────────
    {
        "name": "Phase 2 – Contextual Follow-ups",
        "messages": [
            ("Find my grocery note", 40),
            # The next message uses "it" — Qwen must resolve from history
            ("Add butter and cheese to it", 50),
            ("Mark it as done", 60),
            ("Show me the note you just updated", 45),
        ],
    },
    # ── Phase 3: Multi-step research (longer delay = thinking time) ───────
    {
        "name": "Phase 3 – Multi-step Research",
        "messages": [
            ("Create a note: Learn about Redis pub/sub for the backend project", 90),
            ("Find all notes related to backend", 60),
            ("How many notes do I have in total?", 45),
        ],
    },
    # ── Phase 4: Idle gap then resume (tests 30-min timeout boundary) ─────
    {
        "name": "Phase 4 – Resume After Idle",
        "delay_before_phase": 120,  # 2 min idle gap
        "messages": [
            # Still within 30-min window — should reuse same conversation
            ("What was the last note I created?", 60),
            ("Search for notes about groceries", 50),
            ("Delete the grocery note", 90),
        ],
    },
    # ── Phase 5: Edge cases ───────────────────────────────────────────────
    {
        "name": "Phase 5 – Edge Cases & Stress",
        "messages": [
            ("Create a note: " + "A" * 200 + " — end of long note", 45),
            ("Find it and read it back to me", 60),
            ("Create a note: Meeting at 3pm with @harsh about deployment", 40),
            ("Show all pinned notes", 50),
            ("What notes did we work on today?", 60),
        ],
    },
    # ── Phase 6: Final verification turns ─────────────────────────────────
    {
        "name": "Phase 6 – Final Verification",
        "delay_before_phase": 90,
        "messages": [
            ("Summarize everything we've done in this conversation", 30),
            ("How many notes exist now?", 0),
        ],
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _elapsed(start: float) -> str:
    mins, secs = divmod(int(time.time() - start), 60)
    return f"{mins:02d}:{secs:02d}"


def _separator(char="═", width=70):
    print(char * width)


async def _db_summary():
    """Query the DB and print conversation/message stats."""
    async with SessionLocal() as session:
        # Count conversations for our test chat
        conv_count = await session.execute(
            select(func.count(Conversation.id))
            .where(Conversation.chat_id == TEST_CHAT_ID)
        )
        n_convs = conv_count.scalar()

        # Get the conversation IDs
        conv_result = await session.execute(
            select(Conversation)
            .where(Conversation.chat_id == TEST_CHAT_ID)
            .order_by(Conversation.created_at)
        )
        convs = conv_result.scalars().all()

        print(f"\n{'─' * 70}")
        print(f"  DB SUMMARY for chat_id = {TEST_CHAT_ID}")
        print(f"{'─' * 70}")
        print(f"  Total conversations: {n_convs}")

        for conv in convs:
            msg_count = await session.execute(
                select(func.count(ConversationMessage.id))
                .where(ConversationMessage.conversation_id == conv.id)
            )
            n_msgs = msg_count.scalar()

            role_counts = {}
            role_result = await session.execute(
                select(ConversationMessage.role, func.count(ConversationMessage.id))
                .where(ConversationMessage.conversation_id == conv.id)
                .group_by(ConversationMessage.role)
            )
            for role, count in role_result.all():
                role_counts[role] = count

            print(f"\n  Conversation #{conv.id}")
            print(f"    Created:    {conv.created_at}")
            print(f"    Last active: {conv.last_activate_at}")
            print(f"    Messages:   {n_msgs}")
            print(f"    Breakdown:  {json.dumps(role_counts)}")

            # Show the first and last few messages
            msgs = await session.execute(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == conv.id)
                .order_by(ConversationMessage.created_at)
            )
            all_msgs = msgs.scalars().all()

            if all_msgs:
                print(f"    ┌─ First message: [{all_msgs[0].role}] {all_msgs[0].content[:80]}...")
                print(f"    └─ Last message:  [{all_msgs[-1].role}] {all_msgs[-1].content[:80]}...")

        print(f"{'─' * 70}\n")


# ── Main test runner ──────────────────────────────────────────────────────────

async def run_test():
    from mcp_pocketing.ai_client import run_ai_agent

    print()
    _separator()
    print("  CONVERSATION MEMORY TEST")
    print(f"  Chat ID:    {TEST_CHAT_ID}")
    print(f"  Started at: {datetime.now().strftime('%H:%M:%S')}")
    print(f"  Phases:     {len(CONVERSATION_PHASES)}")
    total_msgs = sum(len(p["messages"]) for p in CONVERSATION_PHASES)
    print(f"  Messages:   {total_msgs}")
    _separator()

    global_start = time.time()
    turn_number = 0

    for phase_idx, phase in enumerate(CONVERSATION_PHASES, 1):
        # Optional idle gap before the phase
        idle = phase.get("delay_before_phase", 0)
        if idle:
            print(f"\n  ⏸  Idle gap: {idle}s (simulating user away)...")
            await asyncio.sleep(idle)

        print(f"\n{'━' * 70}")
        print(f"  {phase['name']}  [{_elapsed(global_start)}]")
        print(f"{'━' * 70}")

        for msg_idx, (message, delay) in enumerate(phase["messages"]):
            turn_number += 1
            print(f"\n  ╭─ Turn {turn_number} [{_elapsed(global_start)}]")
            print(f"  │  USER: {message[:100]}{'...' if len(message) > 100 else ''}")

            turn_start = time.time()
            try:
                response = await run_ai_agent(message, chat_id=TEST_CHAT_ID)
            except Exception as e:
                response = f"💥 ERROR: {type(e).__name__}: {e}"

            turn_ms = int((time.time() - turn_start) * 1000)

            # Truncate long responses for display
            display = response[:300] + ("..." if len(response) > 300 else "")
            print(f"  │  AI:   {display}")
            print(f"  ╰─ ({turn_ms}ms)")

            # Wait before next message (simulates real user typing)
            if delay > 0:
                # Add ±20% jitter so it feels more natural
                jittered = delay * random.uniform(0.8, 1.2)
                print(f"       ⏳ waiting {jittered:.0f}s before next turn...")
                await asyncio.sleep(jittered)

    # ── Final report ──────────────────────────────────────────────────────────
    total_elapsed = time.time() - global_start
    mins, secs = divmod(int(total_elapsed), 60)

    print()
    _separator()
    print(f"  TEST COMPLETE  —  {turn_number} turns in {mins}m {secs}s")
    _separator()

    # Query DB to verify persistence
    await _db_summary()

    print("  ✅ Check the AI log for full details:")
    print("     pocketing_logging/logs/<date>/ai/qwen.log")
    print()


async def main():
    # Initialize DB (creates tables if needed)
    await initialize_database()
    await run_test()


if __name__ == "__main__":
    asyncio.run(main())
