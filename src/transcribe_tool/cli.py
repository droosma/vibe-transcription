import os
import sys
import argparse


def _error(message):
    """Print a user-friendly error and exit."""
    print(f"\nError: {message}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="transcribe",
        description="Transcribe and summarize meeting audio files.",
    )
    parser.add_argument("audio_file", nargs="?", help="Path to audio file (or transcript with --skip-transcribe)")
    parser.add_argument("--configure", action="store_true", help="Configure API keys and settings")
    parser.add_argument("--subject", "-s", help="Meeting subject/agenda for better summary context")
    parser.add_argument("--language", "-l", help="Transcription language (default: from config, or nl-NL)")
    parser.add_argument("--skip-transcribe", action="store_true", help="Skip transcription — use existing .txt transcript")
    parser.add_argument("--skip-summary", action="store_true", help="Only transcribe, don't summarize")
    parser.add_argument("--no-questions", action="store_true", help="Skip interactive clarification questions")

    args = parser.parse_args()

    try:
        _run(args)
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        sys.exit(130)
    except Exception as e:
        _error(str(e))


def _run(args):
    if args.configure:
        from transcribe_tool.config import configure_interactive
        configure_interactive()
        return

    if not args.audio_file:
        _error("No audio file specified. Run 'transcribe --help' for usage.")

    input_file = os.path.abspath(args.audio_file)
    if not os.path.exists(input_file):
        _error(f"File not found: {input_file}")

    from transcribe_tool.config import load_config, get_required, is_configured, configure_interactive

    # First-run: auto-launch configure if no config exists
    if not is_configured():
        print("Welcome! First-time setup required.\n")
        configure_interactive()
        print()

    config = load_config()

    output_dir = os.path.dirname(input_file)
    base_name = os.path.basename(input_file)
    stem = os.path.splitext(base_name)[0]

    # If --skip-transcribe, the input IS the transcript
    if args.skip_transcribe:
        transcript_path = input_file
        # Derive summary name from the transcript filename (strip .txt if present)
        if base_name.endswith(".txt"):
            summary_stem = base_name[:-4]
            # Strip further extension if it's like "file.m4a.txt"
            summary_stem = os.path.splitext(summary_stem)[0]
        else:
            summary_stem = stem
    else:
        transcript_path = os.path.join(output_dir, f"{base_name}.txt")
        summary_stem = stem

    summary_path = os.path.join(output_dir, f"{summary_stem}_summary.md")

    # === Step 1: Transcribe ===
    if args.skip_transcribe:
        with open(transcript_path, "r", encoding="utf-8") as f:
            transcript = f.read()
        print(f"Using existing transcript: {transcript_path}")
    else:
        speech_key = get_required(config, "speech_key", "Azure Speech Key")
        speech_region = get_required(config, "speech_region", "Azure Speech Region")
        language = args.language or config.get("language", "nl-NL")

        from transcribe_tool.audio import convert_to_wav
        from transcribe_tool.transcriber import transcribe

        print(f"Converting audio: {base_name}")
        try:
            wav_file = convert_to_wav(input_file)
        except FileNotFoundError:
            _error(
                "FFmpeg not found. It's required for audio conversion.\n"
                "  Install via: pip install imageio-ffmpeg\n"
                "  Or add ffmpeg to your PATH."
            )

        try:
            transcript = transcribe(wav_file, speech_key, speech_region, language)
        except RuntimeError as e:
            if "401" in str(e) or "Unauthorized" in str(e):
                _error(
                    "Azure Speech authentication failed. Check your Speech Key and Region.\n"
                    "  Run 'transcribe --configure' to update."
                )
            raise
        finally:
            # Clean up temp WAV
            try:
                os.remove(wav_file)
            except OSError:
                pass

        # Save transcript next to the audio file
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript)
        print(f"Transcript saved: {transcript_path}")

    if args.skip_summary:
        return

    # === Step 2: Summarize ===
    github_token = get_required(config, "github_token", "GitHub Token")
    model = config.get("llm_model", "claude-opus-4.6")

    from transcribe_tool.summarizer import summarize, extract_clarification_questions, integrate_answers

    print("Generating summary...")
    try:
        summary = summarize(transcript, github_token, model, subject=args.subject)
    except Exception as e:
        err = str(e)
        if "401" in err or "Unauthorized" in err or "Personal Access Tokens are not supported" in err:
            _error(
                "Copilot API authentication failed.\n"
                "  The Copilot API requires a `gh` CLI OAuth token (not a PAT).\n"
                "  1. Install gh CLI: https://cli.github.com/\n"
                "  2. Run: gh auth login\n"
                "  3. Run: transcribe --configure"
            )
        if "413" in err or "tokens_limit" in err or "too large" in err.lower():
            _error(
                "Transcript too large for the API.\n"
                "  Try a model with a larger context window, or the tool will\n"
                "  auto-chunk on next run."
            )
        if "429" in err or "rate" in err.lower():
            _error(
                "Rate limit reached on Copilot API. Wait a minute and try again.\n"
                "  Tip: Use --skip-transcribe to avoid re-transcribing."
            )
        raise

    # === Step 3: Interactive clarification questions ===
    if not args.no_questions:
        questions, _ = extract_clarification_questions(summary)
        if questions:
            print(f"\n{'=' * 60}")
            print(f"The summary has {len(questions)} clarification question(s).")
            print(f"Answer to improve accuracy, or press Enter to skip each one.")
            print(f"{'=' * 60}\n")

            qa_pairs = []
            for i, q in enumerate(questions, 1):
                print(f"  {i}. {q}")
                try:
                    answer = input("     Answer: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n\nSkipping remaining questions.")
                    break
                if answer:
                    qa_pairs.append((q, answer))
                print()

            if qa_pairs:
                print("Integrating answers into summary...")
                try:
                    summary = integrate_answers(summary, qa_pairs, github_token, model)
                except Exception as e:
                    print(f"\nWarning: Could not integrate answers: {e}")
                    print("Saving summary without integrated answers.")

    # === Save summary ===
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    print(f"\nSummary saved: {summary_path}")


if __name__ == "__main__":
    main()
