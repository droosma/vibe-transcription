import os
import shutil
import subprocess
import tempfile


def get_ffmpeg_exe():
    """Find ffmpeg executable: imageio-ffmpeg package, then PATH."""
    # 1. Try the imageio-ffmpeg bundled binary
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe:
            return exe
    except Exception:
        pass

    # 2. Check PATH
    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        return path_ffmpeg

    raise FileNotFoundError(
        "FFmpeg not found. Install it via:\n"
        "  pip install imageio-ffmpeg\n"
        "  or add ffmpeg to your PATH"
    )


def convert_to_wav(audio_file):
    """Convert audio to 16kHz mono WAV for Azure Speech. Returns path to temp WAV file."""
    ffmpeg_exe = get_ffmpeg_exe()

    # Use a named temp file (won't auto-delete, caller is responsible)
    fd, output_file = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    cmd = [
        ffmpeg_exe,
        "-y",
        "-i", audio_file,
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        output_file,
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        os.unlink(output_file)
        stderr = e.stderr.decode() if e.stderr else "Unknown error"
        raise RuntimeError(f"FFmpeg conversion failed: {stderr}")

    size = os.path.getsize(output_file)
    if size < 1000:
        os.unlink(output_file)
        raise RuntimeError("Audio conversion produced an empty or invalid file")

    print(f"Audio converted ({size / (1024 * 1024):.1f} MB WAV)")
    return output_file
