#!/usr/bin/env python3
"""GitHub Actions script: Auto-format PR title based on commit history using GPT-5.6-Luna."""

import json
import os
import sys
import urllib.request
import urllib.error


def fetch_pr_commits(repo: str, pr_number: str, github_token: str) -> list[str]:
    """Fetch commit messages from GitHub PR API."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/commits?per_page=100"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {github_token}",
            "User-Agent": "PR-Title-Auto-Formatter",
        },
    )
    with urllib.request.urlopen(req) as resp:
        commits_data = json.loads(resp.read().decode("utf-8"))

    commit_messages = []
    for item in commits_data:
        msg = item.get("commit", {}).get("message", "").strip()
        if msg:
            # Take the first line (subject) of each commit message
            subject = msg.splitlines()[0]
            commit_messages.append(subject)
    return commit_messages


def generate_pr_title_with_llm(
    commits: list[str],
    current_title: str,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-5.6-luna",
) -> str:
    """Call GPT-5.6-Luna (OpenAI compatible API) to generate a concise conventional PR title."""
    system_prompt = (
        "You are an expert Git release engineer and code reviewer.\n"
        "Your task is to generate a concise, standardized Conventional Commit PR title based on a list of Git commit messages.\n\n"
        "Rules:\n"
        "1. Follow the Conventional Commits format: `<type>(<optional-scope>): <imperative summary>` or `<type>: <imperative summary>`\n"
        "2. Valid types: feat, fix, refactor, chore, docs, test, perf, ci, style\n"
        "3. Keep the summary under 70 characters, clear, active voice, in English (e.g. 'feat: add BI dashboard workspace and interactive cards').\n"
        "4. Do NOT include issue numbers, brackets, markdown fences, quotes, or trailing periods.\n"
        "5. Output ONLY the single line title string."
    )

    commits_text = "\n".join(f"- {c}" for c in commits)
    user_prompt = (
        f"Current PR Title: {current_title}\n\n"
        f"Commit Messages ({len(commits)} commits):\n{commits_text}\n\n"
        "Generate the best Conventional PR title:"
    )

    endpoint = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 100,
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "PR-Title-Auto-Formatter",
        },
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            title = data["choices"][0]["message"]["content"].strip()
            # Clean any surrounding quotes or markdown
            title = title.strip('`"\'').splitlines()[0].strip()
            return title
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="ignore")
        print(f"LLM API Error {err.code}: {body}", file=sys.stderr)
        raise


def update_pr_title(repo: str, pr_number: str, new_title: str, github_token: str) -> None:
    """Update PR title via GitHub REST API."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    req = urllib.request.Request(
        url,
        data=json.dumps({"title": new_title}).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {github_token}",
            "Content-Type": "application/json",
            "User-Agent": "PR-Title-Auto-Formatter",
        },
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"Successfully updated PR #{pr_number} title (HTTP {resp.status})")


def main() -> None:
    github_token = os.environ.get("GITHUB_TOKEN")
    api_key = os.environ.get("LUNA_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("LUNA_BASE_URL") or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("LUNA_MODEL", "gpt-5.6-luna")
    repo = os.environ.get("GITHUB_REPOSITORY")
    pr_number = os.environ.get("PR_NUMBER")
    current_title = os.environ.get("CURRENT_PR_TITLE", "")

    if not github_token:
        print("Error: GITHUB_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)

    if not api_key:
        print("Warning: LUNA_API_KEY / OPENAI_API_KEY is not configured in GitHub Secrets. Skipping auto-formatting.")
        sys.exit(0)

    if not repo or not pr_number:
        print("Error: GITHUB_REPOSITORY or PR_NUMBER is missing.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching commits for PR #{pr_number} in {repo}...")
    commits = fetch_pr_commits(repo, pr_number, github_token)

    if not commits:
        print("No commits found in PR. Skipping title update.")
        sys.exit(0)

    print(f"Found {len(commits)} commits. Generating standardized title using {model}...")
    try:
        new_title = generate_pr_title_with_llm(
            commits=commits,
            current_title=current_title,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
    except Exception as exc:
        print(f"Failed to generate title with {model}: {exc}", file=sys.stderr)
        sys.exit(0)  # Don't fail the CI job, just gracefully skip

    if not new_title:
        print("Generated title is empty. Skipping update.")
        sys.exit(0)

    print(f"Current Title: '{current_title}'")
    print(f"New Title:     '{new_title}'")

    if new_title == current_title:
        print("PR title is already up-to-date and correctly formatted.")
        return

    update_pr_title(repo, pr_number, new_title, github_token)
    print(f"🎉 PR #{pr_number} title updated to: {new_title}")


if __name__ == "__main__":
    main()
