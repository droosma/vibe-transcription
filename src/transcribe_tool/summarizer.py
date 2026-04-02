import os
import re
from openai import OpenAI

# Rough estimate: 1 token ≈ 4 chars for mixed Dutch/English text.
# We leave room for the system prompt (~2000 tokens) and response.
_CHARS_PER_TOKEN = 4
_MAX_CHUNK_TOKENS = 100_000
_MAX_CHUNK_CHARS = _MAX_CHUNK_TOKENS * _CHARS_PER_TOKEN


def _load_prompt():
    """Load the summarization prompt template from the bundled prompt.md."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompt.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def _get_client(github_token):
    return OpenAI(
        base_url="https://api.githubcopilot.com",
        api_key=github_token,
    )


def _split_transcript(transcript, max_chars=_MAX_CHUNK_CHARS):
    """Split transcript into chunks at line boundaries."""
    if len(transcript) <= max_chars:
        return [transcript]

    lines = transcript.split("\n")
    chunks = []
    current = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > max_chars and current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    return chunks


def _summarize_single(client, prompt, transcript, model, subject=None):
    """Summarize a single transcript chunk."""
    user_content = ""
    if subject:
        user_content += f"**Subject/Agenda**: {subject}\n\n"
    user_content += f"## Transcript\n\n{transcript}"

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content


def _merge_summaries(client, summaries, model, subject=None):
    """Merge multiple partial summaries into one final summary."""
    combined = "\n\n---\n\n".join(
        f"## Partial Summary {i + 1}\n\n{s}" for i, s in enumerate(summaries)
    )

    system = (
        "You are an expert meeting analyst. You will receive multiple partial summaries of the same meeting "
        "(the transcript was too long to process at once). Merge them into a single cohesive summary. "
        "Deduplicate attendees, decisions, action items, and discussion points. "
        "Combine all sections following the same Markdown structure as the partial summaries. "
        "Preserve all detail — do not drop items that only appear in one partial summary. "
        "Return only the merged summary, no commentary."
    )
    user_content = ""
    if subject:
        user_content += f"**Subject/Agenda**: {subject}\n\n"
    user_content += combined

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content


def summarize(transcript, github_token, model="claude-opus-4.6", subject=None):
    """Summarize a transcript using GitHub Models API. Chunks long transcripts automatically."""
    client = _get_client(github_token)
    prompt = _load_prompt()
    chunks = _split_transcript(transcript)

    if len(chunks) == 1:
        return _summarize_single(client, prompt, transcript, model, subject)

    print(f"  Transcript is large — processing in {len(chunks)} chunks...")
    summaries = []
    for i, chunk in enumerate(chunks):
        print(f"  Summarizing chunk {i + 1}/{len(chunks)}...")
        summaries.append(_summarize_single(client, prompt, chunk, model, subject))

    print("  Merging partial summaries...")
    return _merge_summaries(client, summaries, model, subject)


def extract_clarification_questions(summary):
    """Extract clarification questions from the summary. Returns (questions, full_summary)."""
    # Match "## Clarification Questions" or "**Clarification Questions**" sections
    pattern = r'(?:^|\n)(?:##?\s*\*{0,2}|(?:\*{2}))Clarification Questions\*{0,2}\s*\n(.*?)(?=\n##?\s|\n\*{2}[A-Z]|\Z)'
    match = re.search(pattern, summary, re.DOTALL | re.IGNORECASE)
    if not match:
        return [], summary

    section_text = match.group(1).strip()
    if not section_text or "no clarification" in section_text.lower():
        return [], summary

    # Parse numbered questions (handles multi-line questions)
    questions = re.findall(r'\d+\.\s*(.+?)(?=\n\d+\.|\Z)', section_text, re.DOTALL)
    questions = [q.strip() for q in questions if q.strip()]

    return questions, summary


def integrate_answers(summary, qa_pairs, github_token, model="claude-opus-4.6"):
    """Send clarification answers back to the LLM to update the summary."""
    client = _get_client(github_token)

    answers_text = "\n".join(
        f"{i + 1}. Q: {q}\n   A: {a}" for i, (q, a) in enumerate(qa_pairs)
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a meeting summary editor. You will receive a meeting summary that contains "
                    "a 'Clarification Questions' section, along with answers to those questions. "
                    "Integrate each answer into the relevant sections of the summary, improving accuracy "
                    "and detail. Then remove the 'Clarification Questions' section entirely since all "
                    "questions are now resolved. Return the complete updated summary in the same Markdown format. "
                    "Do not add commentary — return only the updated summary."
                ),
            },
            {
                "role": "user",
                "content": f"## Current Summary\n\n{summary}\n\n## Answers to Clarification Questions\n\n{answers_text}",
            },
        ],
        temperature=0.2,
    )

    return response.choices[0].message.content
