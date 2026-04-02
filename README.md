# Meeting Transcribe

A CLI tool that transcribes meeting audio and produces structured summaries — end to end.

Uses **Azure Speech Services** (with speaker diarization) for transcription and the **GitHub Copilot API** for LLM-powered summarization (Claude, GPT, Gemini — your choice). Clarification questions are asked interactively and integrated into the final summary.

## Install

Requires Python 3.10+.

Install from GitHub:

```bash
pipx install git+https://github.com/droosma/vibe-transcription.git
```

Or clone and install locally:

```bash
git clone https://github.com/droosma/vibe-transcription.git
cd vibe-transcription
pipx install .
```

For development:

```bash
pip install -e .
```

> **No `pipx`?** Install it with `pip install pipx` then `pipx ensurepath`.

## Setup

On first run, the tool detects it's not configured and launches the setup wizard automatically. You can also run it manually:

```bash
transcribe --configure
```

### What you'll need

| Setting | Where to get it |
|---------|----------------|
| **Azure Speech Key** | [Azure Portal](https://portal.azure.com) → create a **Speech** resource (AI + Machine Learning) → Keys and Endpoint → copy Key 1 |
| **Azure Speech Region** | Same page — e.g. `westeurope`, `eastus` |
| **GitHub Copilot** | Install [`gh` CLI](https://cli.github.com/), then `gh auth login`. Your Copilot subscription provides access to Claude, GPT, Gemini models. |

The token is auto-detected from `gh auth token` at runtime — no need to manage tokens manually.

### Where config is stored

| OS | Path |
|----|------|
| Windows | `%APPDATA%\transcribe\config.json` |
| Linux/Mac | `~/.config/transcribe/config.json` |

All settings can be overridden via environment variables: `SPEECH_KEY`, `SPEECH_REGION`, `GITHUB_TOKEN`, `COPILOT_MODEL`, `TRANSCRIBE_LANGUAGE`.

## Usage

Full pipeline — transcribe audio, summarize, answer clarification questions:

```bash
transcribe path/to/meeting.m4a
```

With meeting context for a better summary:

```bash
transcribe meeting.m4a --subject "Bilateraal Duncan & Agent X"
```

Transcribe only (no summary):

```bash
transcribe meeting.m4a --skip-summary
```

Summarize an existing transcript:

```bash
transcribe existing-transcript.txt --skip-transcribe
```

Skip interactive questions (non-interactive mode):

```bash
transcribe meeting.m4a --no-questions
```

Override transcription language (default: nl-NL):

```bash
transcribe meeting.m4a --language en-US
```

## Output

Files are saved next to the input audio file:

- `meeting.m4a.txt` — raw transcript with speaker labels (`[Guest-1]`, `[Guest-2]`, ...)
- `meeting_summary.md` — structured Markdown summary

## What the summary includes

- **Attendees** and **people mentioned** (with roles)
- **Decisions & Choices** with rationale
- **Action items** with owner, deadline, and priority
- **Key discussion points**
- **Unresolved / parked topics**
- **Detected "talking to the AI" instructions** — participants can speak to the AI during the meeting
- **Transcript quality review** — flagged misheard words, garbled passages
- **Clarification questions** — asked interactively, answers integrated into the final summary
