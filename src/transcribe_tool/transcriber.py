import time
import azure.cognitiveservices.speech as speechsdk


def transcribe(wav_file, speech_key, speech_region, language="nl-NL"):
    """Transcribe audio with speaker diarization using Azure ConversationTranscriber."""
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_recognition_language = language

    audio_config = speechsdk.audio.AudioConfig(filename=wav_file)
    transcriber = speechsdk.transcription.ConversationTranscriber(
        speech_config=speech_config,
        audio_config=audio_config,
    )

    done = False
    results = []
    error_details = None

    def transcribed_cb(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            speaker = evt.result.speaker_id or "Unknown"
            results.append(f"[{speaker}]: {evt.result.text}")
            print(".", end="", flush=True)

    def canceled_cb(evt):
        nonlocal done, error_details
        if evt.reason == speechsdk.CancellationReason.Error:
            error_details = evt.error_details
        done = True

    def stopped_cb(evt):
        nonlocal done
        done = True

    transcriber.transcribed.connect(transcribed_cb)
    transcriber.canceled.connect(canceled_cb)
    transcriber.session_stopped.connect(stopped_cb)

    print("Transcribing", end="", flush=True)
    transcriber.start_transcribing_async().get()

    while not done:
        time.sleep(0.5)

    transcriber.stop_transcribing_async().get()
    print()

    if error_details:
        raise RuntimeError(f"Transcription failed: {error_details}")

    if not results:
        raise RuntimeError("Transcription produced no output. Check audio quality and language setting.")

    return "\n".join(results)
