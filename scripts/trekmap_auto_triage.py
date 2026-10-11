"""Non-destructive GitHub Actions triage after a failed TrekMap health workflow.

Retry cold-starting Render, report persistent problems through one reusable
GitHub issue, and leave actual code fixes to validated PRs. Never touch Neon,
Render environment variables, subscription plans or public routing quotas.
"""
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://trekmap-france.onrender.com"
API = "https://api.github.com"
HEALTH_WORKFLOWS = {"TrekMap production smoke", "TrekMap nightly health"}
BENCHMARK = "TrekBrain serial production suite"
TITLE_PREFIX = "[TrekMap auto-triage] "


def fetch(url, token="", timeout=24):
    headers = {
        "Accept": "application/vnd.github+json" if token else "application/json",
        "User-Agent": "TrekMap-auto-triage/1.0",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    with urlopen(Request(url, headers=headers), timeout=timeout) as response:
        return json.load(response)


def post(url, payload, token):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "TrekMap-auto-triage/1.0",
    }
    request = Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST",
    )
    with urlopen(request, timeout=24) as response:
        return json.load(response)


def validate(path, payload, expected_sha=""):
    if path == "/health/ready":
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise ValueError("Database not ready")
    if path == "/treks" and not isinstance(payload, list):
        raise ValueError("Public treks must be a list")
    if path == "/ai/status":
        if not isinstance(payload, dict) or payload.get("release_channel") != "v9-stable":
            raise ValueError("TrekBrain stable channel unavailable")
        if payload.get("stability_gate") != "required":
            raise ValueError("TrekBrain gate unavailable")
        if expected_sha and str(payload.get("build_commit") or "").lower() != expected_sha.lower():
            raise ValueError("Deployed commit does not match")


def probe(expected_sha, attempts=4, sleep=time.sleep):
    """Warm free Render; no actual TrekBrain planning or external ORS calls."""
    for index in range(attempts):
        if index:
            sleep(12 if index == 1 else 20)
        try:
            for path in ("/health/ready", "/treks", "/ai/status"):
                validate(path, fetch(BASE + path), expected_sha)
            print("Production recovered after", index + 1, "probe(s)")
            return True
        except (HTTPError, URLError, ValueError, OSError, TimeoutError) as exc:
            print("Probe", index + 1, "failed:", type(exc).__name__)
    return False


def should_report(workflow, recovered):
    # Benchmarks can be structurally broken while /health/ready is green.
    return workflow == BENCHMARK or (workflow in HEALTH_WORKFLOWS and not recovered)


def main():
    filepath = os.environ.get("GITHUB_EVENT_PATH")
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    if not filepath or not repo or not token:
        print("No trusted Actions context; nothing written")
        return 1
    with open(filepath, encoding="utf-8") as stream:
        run = (json.load(stream).get("workflow_run") or {})
    workflow = str(run.get("name") or "")
    if (run.get("conclusion") != "failure" or
            run.get("head_branch") != "main" or
            workflow not in HEALTH_WORKFLOWS | {BENCHMARK}):
        print("Ignoring unrelated workflow run")
        return 0
    sha = str(run.get("head_sha") or "").lower()
    if len(sha) != 40:
        print("Missing commit hash; refusing to write")
        return 1
    current = fetch(f"{API}/repos/{repo}/commits/main", token)
    if str(current.get("sha") or "").lower() != sha:
        print("Obsolete workflow failure; newer main commit exists")
        return 0
    recovered = probe(sha)
    if not should_report(workflow, recovered):
        print("Transient Render issue resolved; no repair needed")
        return 0
    link = str(run.get("html_url") or "")
    if not link.startswith(f"https://github.com/{repo}/actions/runs/"):
        print("Untrusted workflow link; refusing to write")
        return 1
    body = (
        "Automatic non-destructive triage of a verified GitHub Actions failure.\n\n"
        f"- Workflow: {workflow}\n"
        f"- Run: {link}\n"
        f"- Commit: {sha}\n"
        f"- Render APIs after bounded cold-start retries: "
        f"{'healthy' if recovered else 'not confirmed healthy'}\n\n"
        "If this was a route-quality benchmark, a green /health/ready does not "
        "resolve the routing failure. Investigate reproducibility and provider "
        "quotas first. The TrekMap hourly maintenance task can prepare a tested "
        "pull request. Never weaken route safety, change Neon data, or deploy "
        "an untested fix automatically."
    )
    title = TITLE_PREFIX + workflow
    issues = fetch(f"{API}/repos/{repo}/issues?state=open&per_page=100", token)
    match = next(
        (item for item in issues
         if item.get("title") == title and "pull_request" not in item),
        None,
    )
    if match:
        number = int(match["number"])
        comments = fetch(f"{API}/repos/{repo}/issues/{number}/comments?per_page=100", token)
        if not any(link in str(item.get("body") or "") for item in comments):
            post(f"{API}/repos/{repo}/issues/{number}/comments", {"body": body}, token)
        print("Existing issue updated:", number)
    else:
        created = post(f"{API}/repos/{repo}/issues", {"title": title, "body": body}, token)
        print("Incident issue created:", created.get("number"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
