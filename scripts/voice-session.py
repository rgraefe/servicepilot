#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

from conversation.voice_contract import (
    iter_audio_chunks,
    load_voice_profile,
    read_wav,
    validate_session_id,
    wav_duration_seconds,
    write_linear16_wav,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream WAV turns through one ServicePilot Dialogflow CX session."
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--session-id", default=f"voice-{uuid.uuid4().hex[:24]}")
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("conversation/voice-profile.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/voice"))
    parser.add_argument(
        "--no-realtime",
        action="store_true",
        help="Send chunks without wall-clock pacing; useful only for fast test fixtures.",
    )
    parser.add_argument(
        "--barge-in-before",
        action="append",
        type=int,
        default=[],
        metavar="TURN",
        help="Mark a one-based turn as interrupting response playback from the prior turn.",
    )
    return parser.parse_args()


def credentials_from_environment(quota_project_id: str):
    token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    if not token:
        return None
    from google.oauth2.credentials import Credentials

    return Credentials(token=token, quota_project_id=quota_project_id)


def create_client(region: str, project: str):
    from google.cloud import dialogflowcx_v3

    return dialogflowcx_v3.SessionsClient(
        credentials=credentials_from_environment(project),
        client_options={"api_endpoint": f"{region}-dialogflow.googleapis.com"},
    )


def make_requests(
    *,
    session: str,
    profile: dict,
    chunks: list[bytes],
    realtime: bool,
    barge_in_total_duration_ms: int | None = None,
) -> Iterator[object]:
    from google.cloud import dialogflowcx_v3
    from google.protobuf.duration_pb2 import Duration

    barge_in_config = None
    if barge_in_total_duration_ms is not None:
        total_duration = Duration()
        total_duration.FromMilliseconds(barge_in_total_duration_ms)
        barge_in_config = dialogflowcx_v3.BargeInConfig(
            no_barge_in_duration=Duration(), total_duration=total_duration
        )

    input_config = dialogflowcx_v3.InputAudioConfig(
        audio_encoding=dialogflowcx_v3.AudioEncoding.AUDIO_ENCODING_LINEAR_16,
        sample_rate_hertz=profile["input"]["sample_rate_hertz"],
        single_utterance=True,
        barge_in_config=barge_in_config,
    )
    output_config = dialogflowcx_v3.OutputAudioConfig(
        audio_encoding=(
            dialogflowcx_v3.OutputAudioEncoding.OUTPUT_AUDIO_ENCODING_LINEAR_16
        ),
        sample_rate_hertz=profile["output"]["sample_rate_hertz"],
    )
    yield dialogflowcx_v3.StreamingDetectIntentRequest(
        session=session,
        query_input=dialogflowcx_v3.QueryInput(
            language_code=profile["language_code"],
            audio=dialogflowcx_v3.AudioInput(config=input_config),
        ),
        output_audio_config=output_config,
        enable_partial_response=profile["client_policy"]["enable_partial_response"],
    )
    delay = profile["input"]["chunk_duration_ms"] / 1000
    for chunk in chunks:
        yield dialogflowcx_v3.StreamingDetectIntentRequest(
            query_input=dialogflowcx_v3.QueryInput(
                audio=dialogflowcx_v3.AudioInput(audio=chunk)
            )
        )
        if realtime:
            time.sleep(delay)


def response_messages(query_result) -> list[str]:
    texts: list[str] = []
    for message in query_result.response_messages:
        if message.text and message.text.text:
            texts.extend(message.text.text)
    return texts


def run_turn(
    client,
    session: str,
    profile: dict,
    source: Path,
    realtime: bool,
    barge_in_total_duration_ms: int | None,
) -> dict:
    audio = read_wav(source, profile)
    chunks = list(
        iter_audio_chunks(audio, profile["input"]["chunk_duration_ms"])
    )
    started = time.monotonic()
    responses = client.streaming_detect_intent(
        requests=make_requests(
            session=session,
            profile=profile,
            chunks=chunks,
            realtime=realtime,
            barge_in_total_duration_ms=barge_in_total_duration_ms,
        )
    )
    transcripts: list[dict] = []
    final_response = None
    for response in responses:
        if response.recognition_result:
            transcripts.append(
                {
                    "transcript": response.recognition_result.transcript,
                    "is_final": response.recognition_result.is_final,
                    "confidence": response.recognition_result.confidence,
                }
            )
        if response.detect_intent_response:
            final_response = response.detect_intent_response
    elapsed_ms = round((time.monotonic() - started) * 1000)
    if final_response is None:
        raise RuntimeError("Dialogflow returned no detect-intent response.")
    query_result = final_response.query_result
    return {
        "source": str(source),
        "input_duration_seconds": round(wav_duration_seconds(audio), 3),
        "elapsed_ms": elapsed_ms,
        "recognition": transcripts,
        "response_text": response_messages(query_result),
        "match_type": str(query_result.match.match_type) if query_result.match else None,
        "barge_in": barge_in_total_duration_ms is not None,
        "output_audio": bytes(final_response.output_audio),
    }


def main() -> int:
    args = parse_args()
    profile = load_voice_profile(args.profile)
    session_id = validate_session_id(args.session_id)
    session = (
        f"projects/{args.project}/locations/{args.region}/agents/{args.agent_id}"
        f"/sessions/{session_id}"
    )
    client = create_client(args.region, args.project)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    prior_output_duration_ms: int | None = None
    for turn_number, source in enumerate(args.input, start=1):
        is_barge_in = turn_number in args.barge_in_before
        if is_barge_in and prior_output_duration_ms is None:
            raise ValueError(
                f"Turn {turn_number} cannot barge in because the prior turn has no audio."
            )
        result = run_turn(
            client,
            session,
            profile,
            source,
            realtime=profile["input"]["realtime_pacing"] and not args.no_realtime,
            barge_in_total_duration_ms=(
                prior_output_duration_ms if is_barge_in else None
            ),
        )
        result["turn"] = turn_number
        output_path = args.output_dir / f"turn-{turn_number:02d}.wav"
        output_audio = result.pop("output_audio")
        prior_output_duration_ms = None
        if output_audio:
            write_linear16_wav(
                output_path,
                output_audio,
                profile["output"]["sample_rate_hertz"],
            )
            result["output_wav"] = str(output_path)
            prior_output_duration_ms = round(
                len(output_audio)
                / (profile["output"]["sample_rate_hertz"] * 2)
                * 1000
            )
        else:
            result["output_wav"] = None
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))
    summary_path = args.output_dir / "session.json"
    summary_path.write_text(
        json.dumps(
            {"session_id": session_id, "turns": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Session summary: {summary_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
