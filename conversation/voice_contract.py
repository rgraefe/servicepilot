from __future__ import annotations

import json
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,36}$")


class VoiceContractError(ValueError):
    """Raised when audio or session input violates the voice transport contract."""


@dataclass(frozen=True)
class WavAudio:
    sample_rate_hertz: int
    channels: int
    sample_width_bytes: int
    frames: bytes


def load_voice_profile(path: str | Path) -> dict:
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    if profile.get("schema_version") != 1:
        raise VoiceContractError("Unsupported voice profile schema version.")
    if profile.get("language_code") != "de":
        raise VoiceContractError("The ServicePilot voice profile must use language 'de'.")
    return profile


def validate_session_id(session_id: str) -> str:
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise VoiceContractError(
            "Session ID must contain 1-36 letters, digits, underscores, or hyphens."
        )
    return session_id


def read_wav(path: str | Path, profile: dict) -> WavAudio:
    with wave.open(str(path), "rb") as wav_file:
        audio = WavAudio(
            sample_rate_hertz=wav_file.getframerate(),
            channels=wav_file.getnchannels(),
            sample_width_bytes=wav_file.getsampwidth(),
            frames=wav_file.readframes(wav_file.getnframes()),
        )
    expected = profile["input"]
    if audio.sample_rate_hertz != expected["sample_rate_hertz"]:
        raise VoiceContractError(
            f"WAV sample rate must be {expected['sample_rate_hertz']} Hz."
        )
    if audio.channels != expected["channels"]:
        raise VoiceContractError(f"WAV must contain {expected['channels']} channel.")
    if audio.sample_width_bytes != 2:
        raise VoiceContractError("WAV must contain 16-bit PCM samples.")
    if not audio.frames:
        raise VoiceContractError("WAV input must not be empty.")
    return audio


def iter_audio_chunks(audio: WavAudio, chunk_duration_ms: int) -> Iterator[bytes]:
    if chunk_duration_ms < 20 or chunk_duration_ms > 1000:
        raise VoiceContractError("Chunk duration must be between 20 and 1000 ms.")
    bytes_per_second = (
        audio.sample_rate_hertz * audio.channels * audio.sample_width_bytes
    )
    chunk_size = max(
        audio.channels * audio.sample_width_bytes,
        bytes_per_second * chunk_duration_ms // 1000,
    )
    frame_size = audio.channels * audio.sample_width_bytes
    chunk_size -= chunk_size % frame_size
    for offset in range(0, len(audio.frames), chunk_size):
        yield audio.frames[offset : offset + chunk_size]


def write_linear16_wav(
    destination: str | Path, audio: bytes, sample_rate_hertz: int
) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hertz)
        wav_file.writeframes(audio)


def wav_duration_seconds(audio: WavAudio) -> float:
    bytes_per_second = (
        audio.sample_rate_hertz * audio.channels * audio.sample_width_bytes
    )
    return len(audio.frames) / bytes_per_second
