# Voice channel

Phase 9 adds a German streaming voice channel to the existing Dialogflow CX
agent. It does not add voice-specific business endpoints or duplicate any
playbook, flow, authorization, validation, repository, or handover rule.

## Architecture

```text
16 kHz mono LINEAR16 WAV / telephony adapter later
                    |
                    v
      Dialogflow CX streamingDetectIntent
       partial STT + endpointing + barge-in
                    |
                    v
       unchanged playbooks, tools and flow
                    |
                    v
       24 kHz mono LINEAR16 response audio
```

`conversation/voice-profile.json` is the deployable transport profile.
`conversation/voice-scenarios.json` is the Phase 9 acceptance catalog.
`scripts/voice-session.py` is a file-based streaming reference client: every
`--input` is one 16-bit, mono, 16 kHz PCM WAV turn and all inputs share one CX
session. It writes synthesized 24 kHz PCM WAV responses and a JSON transcript to
the ignored `artifacts/voice` directory.

The client uses regional gRPC, real-time 100 ms chunks, partial recognition
results, single-utterance detection and Dialogflow output audio. For a turn
listed with `--barge-in-before`, it sends the preceding audio playback duration
in `BargeInConfig`. A real microphone/player adapter must stream the next input
while the prior response is playing and stop playback as soon as Dialogflow
detects the interrupting utterance. The reference client preserves response WAVs
as test evidence rather than playing them.

## Speech policy

- Default language is German (`de`).
- Speech adaptation is enabled and `latest_short` is selected for conversational
  utterances.
- Eight seconds without speech is tolerated. Timeout-based endpointing is kept
  off because it can cut slow speakers or mid-sentence pauses too aggressively.
- Smart endpointing is not enabled because the current Dialogflow CX option is
  limited to English (`en-US`).
- Responses use a slightly reduced speaking rate of `0.95`.
- Critical customer, ticket, device and serial identifiers are repeated in
  groups and confirmed before backend use. A spoken correction replaces the
  stale value.
- A barge-in cancels obsolete playback/proposals but never bypasses identity or
  write confirmation.
- Backend waiting language is neutral; a result is spoken only after the
  canonical tool response.
- Structured Cloud Logging remains enabled for operations, while interaction
  logging and audio export stay disabled to avoid retaining voice content by
  default. Enable content retention only after an explicit data protection and
  operational review.

## Deploy the voice settings

Preview first:

```powershell
./scripts/deploy-voice-agent.ps1 `
  -ProjectId servicepilot-development `
  -Region europe-west3 `
  -AgentId YOUR_AGENT_UUID `
  -WhatIf
```

Apply the profile, then redeploy the playbook catalog so the voice guardrails are
active:

```powershell
./scripts/deploy-voice-agent.ps1 -ProjectId servicepilot-development -Region europe-west3 -AgentId YOUR_AGENT_UUID
./scripts/deploy-conversational-agent.ps1 -ProjectId servicepilot-development -Region europe-west3 -AgentId YOUR_AGENT_UUID
```

Both scripts use the active `gcloud` account. They do not create keys or write an
access token to disk. The voice script patches only speech and logging settings.

## Run a complete voice session in Docker

Create or record each input WAV as 16-bit PCM, mono, 16 kHz. Obtain a short-lived
access token in the host shell and pass it only to the one-off container:

```powershell
$accessToken = gcloud auth print-access-token
docker compose run --rm `
  -e GOOGLE_OAUTH_ACCESS_TOKEN=$accessToken `
  api python scripts/voice-session.py `
  --project servicepilot-development `
  --region europe-west3 `
  --agent-id YOUR_AGENT_UUID `
  --input artifacts/voice/input-01.wav `
  --input artifacts/voice/input-02.wav
Remove-Variable accessToken
```

To classify the second turn as an interruption of the first response, append
`--barge-in-before 2`. Do not use `--no-realtime` for acceptance testing; it is
only a fast fixture/debug option. The session report contains transcripts,
response text, timings, match type and output filenames, but no token.

## Acceptance

Run the full automated contract suite in Docker:

```powershell
docker compose run --rm api pytest
```

Then record/run every scenario in `conversation/voice-scenarios.json`. At minimum
retain the ignored session JSON and response WAVs long enough to review:

- complete and final transcripts for normal, slow and paused speech;
- replacement plus confirmation of corrected customer IDs and serial numbers;
- stopped obsolete playback and no write on interruption;
- a short wait message with no invented result during backend latency;
- handover offer after two failed critical-identifier recognition attempts.

Production should call a named Dialogflow environment/version rather than the
draft agent. A later telephony/SIP adapter owns device audio capture, playback,
call termination and carrier integration; it reuses this transport contract and
the same agent business logic.
