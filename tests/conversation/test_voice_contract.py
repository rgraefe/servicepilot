import json
import importlib.util
import wave
from pathlib import Path

import pytest

from conversation.voice_contract import (
    VoiceContractError,
    iter_audio_chunks,
    load_voice_profile,
    read_wav,
    validate_session_id,
    write_linear16_wav,
)


PROFILE_PATH = Path("conversation/voice-profile.json")
SCENARIOS_PATH = Path("conversation/voice-scenarios.json")


def load_voice_client_module():
    spec = importlib.util.spec_from_file_location(
        "servicepilot_voice_session", "scripts/voice-session.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_voice_profile_has_safe_german_streaming_defaults() -> None:
    profile = load_voice_profile(PROFILE_PATH)

    assert profile["input"] == {
        "encoding": "AUDIO_ENCODING_LINEAR_16",
        "sample_rate_hertz": 16000,
        "channels": 1,
        "chunk_duration_ms": 100,
        "realtime_pacing": True,
    }
    assert profile["recognition"]["enable_speech_adaptation"] is True
    assert profile["recognition"]["model"] == "latest_short"
    assert profile["recognition"]["no_speech_timeout_seconds"] >= 5
    assert profile["recognition"]["use_timeout_based_endpointing"] is False
    assert profile["output"]["sample_rate_hertz"] == 24000
    assert profile["client_policy"]["allow_barge_in"] is True
    assert profile["client_policy"]["confirm_critical_identifiers"] is True
    assert profile["privacy"] == {
        "enable_stackdriver_logging": True,
        "enable_interaction_logging": False,
        "audio_export_enabled": False,
    }


def test_phase_nine_scenarios_cover_required_voice_risks() -> None:
    scenarios = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))["scenarios"]
    categories = {scenario["category"] for scenario in scenarios}

    assert {
        "normal_speech",
        "slow_speech",
        "pauses",
        "corrections",
        "interruptions",
        "customer_ids",
        "serial_numbers",
        "backend_latency",
    } <= categories
    assert all(scenario["utterances"] and scenario["expected"] for scenario in scenarios)


def test_wav_contract_chunks_linear16_audio(tmp_path: Path) -> None:
    profile = load_voice_profile(PROFILE_PATH)
    source = tmp_path / "input.wav"
    frames = b"\x00\x00" * 16000
    write_linear16_wav(source, frames, 16000)

    audio = read_wav(source, profile)
    chunks = list(iter_audio_chunks(audio, 100))

    assert len(chunks) == 10
    assert b"".join(chunks) == frames


def test_wav_contract_rejects_wrong_sample_rate(tmp_path: Path) -> None:
    source = tmp_path / "wrong.wav"
    with wave.open(str(source), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00\x00" * 8000)

    with pytest.raises(VoiceContractError, match="16000 Hz"):
        read_wav(source, load_voice_profile(PROFILE_PATH))


@pytest.mark.parametrize("session_id", ["voice-123", "abc_DEF", "a" * 36])
def test_valid_session_ids(session_id: str) -> None:
    assert validate_session_id(session_id) == session_id


@pytest.mark.parametrize("session_id", ["", "a" * 37, "has space", "path/slash"])
def test_invalid_session_ids(session_id: str) -> None:
    with pytest.raises(VoiceContractError):
        validate_session_id(session_id)


def test_streaming_request_carries_audio_and_barge_in_contract() -> None:
    module = load_voice_client_module()
    profile = load_voice_profile(PROFILE_PATH)

    requests = list(
        module.make_requests(
            session="projects/p/locations/europe-west3/agents/a/sessions/voice-1",
            profile=profile,
            chunks=[b"\x00\x00"],
            realtime=False,
            barge_in_total_duration_ms=1750,
        )
    )

    assert requests[0].query_input.language_code == "de"
    input_config = requests[0].query_input.audio.config
    assert input_config.sample_rate_hertz == 16000
    assert input_config.single_utterance is True
    duration = input_config.barge_in_config.total_duration
    assert duration.total_seconds() == 1.75
    assert requests[0].enable_partial_response is True
    assert requests[1].query_input.audio.audio == b"\x00\x00"
