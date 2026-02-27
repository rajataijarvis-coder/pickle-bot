# tests/events/test_delivery.py
from picklebot.events.delivery import chunk_message


def test_chunk_message_under_limit():
    result = chunk_message("Hello world", limit=100)
    assert result == ["Hello world"]


def test_chunk_message_exact_limit():
    message = "x" * 100
    result = chunk_message(message, limit=100)
    assert result == [message]


def test_chunk_message_splits_at_paragraph():
    message = "Para one\n\nPara two\n\nPara three"
    result = chunk_message(message, limit=15)
    # "Para one" = 8 chars
    # "Para two" = 8 chars
    # "Para three" = 10 chars
    assert len(result) == 3
    assert "Para one" in result[0]
    assert "Para two" in result[1]


def test_chunk_message_hard_split():
    message = "A" * 50  # Single long "paragraph"
    result = chunk_message(message, limit=20)
    assert len(result) == 3
    assert len(result[0]) == 20
    assert len(result[1]) == 20
    assert len(result[2]) == 10


def test_chunk_message_mixed():
    message = "Short\n\n" + "B" * 50 + "\n\nEnd"
    result = chunk_message(message, limit=20)
    # "Short" = 5 chars - chunk 1
    # 50 B's - chunks 2,3,4 (20+20+10)
    # "End" = 3 chars - chunk 5
    assert len(result) >= 3


def test_platform_limits():
    from picklebot.events.delivery import PLATFORM_LIMITS

    assert PLATFORM_LIMITS["telegram"] == 4096
    assert PLATFORM_LIMITS["discord"] == 2000
    assert PLATFORM_LIMITS["cli"] == float("inf")
