import os
import json
import platform
import shutil
import subprocess
import sys


def get_config_dir():
    """Get platform-appropriate config directory."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "transcribe")
    return os.path.join(os.path.expanduser("~"), ".config", "transcribe")


def get_config_path():
    return os.path.join(get_config_dir(), "config.json")


def is_configured():
    """Check if the tool has been configured at least once."""
    return os.path.exists(get_config_path())


def _try_gh_token():
    """Try to get a GitHub token from the gh CLI."""
    if not shutil.which("gh"):
        return None
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def load_config():
    """Load config from file, with environment variable overrides."""
    path = get_config_path()
    config = {}
    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)

    # Environment variables override config file
    env_map = {
        "SPEECH_KEY": "speech_key",
        "SPEECH_REGION": "speech_region",
        "GITHUB_TOKEN": "github_token",
        "COPILOT_MODEL": "llm_model",
        "TRANSCRIBE_LANGUAGE": "language",
    }
    for env_var, config_key in env_map.items():
        val = os.environ.get(env_var)
        if val:
            config[config_key] = val

    # Always try fresh gh auth token — Copilot API requires OAuth, not PATs.
    # OAuth tokens can rotate, so always get a fresh one when gh is available.
    gh_token = _try_gh_token()
    if gh_token:
        config["github_token"] = gh_token

    return config


def save_config(config):
    config_dir = get_config_dir()
    os.makedirs(config_dir, exist_ok=True)
    path = get_config_path()
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
    # Restrict file permissions (config contains secrets)
    if platform.system() != "Windows":
        os.chmod(path, 0o600)


def _mask(value):
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "..." + value[-4:]


def configure_interactive():
    """Interactive configuration wizard."""
    config = load_config()

    print("Transcribe Tool Configuration")
    print("=" * 40)
    print()

    # --- Azure Speech ---
    print("Azure Speech Service (for transcription):")
    config["speech_key"] = (
        input(f"  Speech Key [{_mask(config.get('speech_key', ''))}]: ").strip()
        or config.get("speech_key", "")
    )
    config["speech_region"] = (
        input(f"  Speech Region [{config.get('speech_region', 'westeurope')}]: ").strip()
        or config.get("speech_region", "westeurope")
    )

    # --- GitHub Token ---
    print()
    gh_token = _try_gh_token()
    current_token = config.get("github_token", "")
    if gh_token:
        print("GitHub Copilot Token (for LLM summarization):")
        print(f"  Detected from `gh auth token`: {_mask(gh_token)}")
        use_gh = input("  Use this token? [Y/n]: ").strip().lower()
        if use_gh != "n":
            config["github_token"] = gh_token
            config["github_token_source"] = "gh_cli"
        else:
            config["github_token"] = (
                input(f"  GitHub Token []: ").strip()
            )
            config["github_token_source"] = "manual"
    else:
        print("GitHub Copilot Token (for LLM summarization):")
        print("  Requires `gh` CLI: https://cli.github.com/")
        print("  Install it, then run: gh auth login")
        print("  (The Copilot API requires a gh OAuth token, not a PAT)")
        config["github_token"] = (
            input(f"  GitHub Token [{_mask(current_token)}]: ").strip()
            or current_token
        )

    # --- Model & Language ---
    print()
    models = [
        ("claude-opus-4.6", "Anthropic — best quality, recommended"),
        ("claude-sonnet-4.6", "Anthropic — fast, great balance"),
        ("claude-sonnet-4", "Anthropic — efficient"),
        ("gpt-5.4", "OpenAI — latest flagship"),
        ("gpt-5.2", "OpenAI — strong all-rounder"),
        ("gpt-4.1", "OpenAI — free tier (0 premium)"),
        ("gpt-5-mini", "OpenAI — lightweight, free tier"),
        ("gemini-2.5-pro", "Google — multimodal"),
    ]
    current_model = config.get("llm_model", "claude-opus-4.6")
    print("  LLM Model for summarization (via Copilot):")
    for i, (name, desc) in enumerate(models, 1):
        marker = " <-- current" if name == current_model else ""
        print(f"    {i}. {name:15s} {desc}{marker}")
    custom_idx = len(models) + 1
    print(f"    {custom_idx}. Other (type model name manually)")
    choice = input(f"  Select [1-{custom_idx}] or Enter for current ({current_model}): ").strip()
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(models):
            config["llm_model"] = models[idx - 1][0]
        elif idx == custom_idx:
            custom = input("  Model name: ").strip()
            if custom:
                config["llm_model"] = custom
            else:
                config["llm_model"] = current_model
    else:
        config["llm_model"] = current_model

    config["language"] = (
        input(f"  Default language [{config.get('language', 'nl-NL')}]: ").strip()
        or config.get("language", "nl-NL")
    )

    save_config(config)
    print(f"\nConfiguration saved to: {get_config_path()}")


def get_required(config, key, description):
    """Get a required config value or exit with helpful message."""
    value = config.get(key)
    if not value:
        print(f"Error: {description} not configured.")
        print(f"Run 'transcribe --configure' to set it up,")
        print(f"or set the corresponding environment variable.")
        sys.exit(1)
    return value
