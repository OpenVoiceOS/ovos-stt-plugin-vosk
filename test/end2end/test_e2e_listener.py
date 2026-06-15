"""E2E listener tests for ovos-stt-plugin-vosk.

Tests:
1. Direct transcription via VoskKaldiSTT.execute()
2. Full listener pipeline via ovoscope get_mini_listener()

Fixture: test/fixtures/command.wav — 16 kHz mono, speech "what time is it in london"
The Vosk small-en model is downloaded once and cached under XDG_DATA_HOME/vosk.
"""
import importlib.util
import os
from pathlib import Path

import pytest

pytest.importorskip("ovoscope", reason="ovoscope not installed")
pytest.importorskip("vosk", reason="vosk not installed")

from ovos_plugin_manager.utils.audio import AudioData
from ovos_stt_plugin_vosk import VoskKaldiSTT
from ovoscope.listener import get_mini_listener

FIXTURE = Path(__file__).parent / "fixtures" / "command.wav"

# The MiniListener pipeline needs ovos-dinkum-listener at runtime; skip the
# pipeline test where it is unavailable (the dedicated ovoscope workflow
# installs the test extras and exercises it for real).
requires_dinkum = pytest.mark.skipif(
    importlib.util.find_spec("ovos_dinkum_listener") is None,
    reason="ovos-dinkum-listener not installed",
)

# Expected tokens from "what time is it in london"
EXPECTED_TOKENS = {"what", "time", "is", "it", "in", "london"}


@pytest.fixture(scope="module")
def stt():
    """Real VoskKaldiSTT with the small English model."""
    instance = VoskKaldiSTT(config={"lang": "en"})
    return instance


@pytest.fixture(scope="module")
def audio_data():
    """Load fixture WAV as AudioData."""
    return AudioData.from_file(str(FIXTURE))


def test_direct_transcription(stt, audio_data):
    """VoskKaldiSTT.execute() returns a non-empty transcript for the fixture."""
    transcript = stt.execute(audio_data, language="en")
    assert isinstance(transcript, str), "transcript must be a str"
    assert transcript.strip(), "transcript must be non-empty"

    lower = transcript.lower()
    matched = EXPECTED_TOKENS & set(lower.split())
    # small model may not be perfect; require at least one recognizable token
    assert matched, (
        f"Expected at least one of {EXPECTED_TOKENS} in transcript, got: {transcript!r}"
    )
    # expose the transcript so the test report shows what vosk produced
    print(f"\n[vosk transcript] {transcript!r}  (matched tokens: {matched})")


@requires_dinkum
def test_listener_pipeline(stt):
    """get_mini_listener() feeds the fixture WAV and emits recognizer_loop:utterance."""
    listener = get_mini_listener(stt_instance=stt)
    try:
        msgs = listener.listen(str(FIXTURE), language="en")
    finally:
        listener.shutdown()

    utterance_msgs = [m for m in msgs if m.msg_type == "recognizer_loop:utterance"]
    assert utterance_msgs, "No recognizer_loop:utterance message emitted"

    utterances = utterance_msgs[0].data.get("utterances", [])
    assert utterances, "utterances list is empty"
    assert utterances[0].strip(), "utterance is blank"

    lower = utterances[0].lower()
    matched = EXPECTED_TOKENS & set(lower.split())
    assert matched, (
        f"Expected at least one of {EXPECTED_TOKENS} in utterance, got: {utterances[0]!r}"
    )
    print(f"\n[listener utterance] {utterances[0]!r}  (matched tokens: {matched})")
