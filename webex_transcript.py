#!/usr/bin/env python3
import sys
import os
import requests
from dotenv import load_dotenv

load_dotenv()

WEBEX_TOKEN_URL = "https://webexapis.com/v1/access_token"
WEBEX_TRANSCRIPTS_URL = "https://webexapis.com/v1/meetingTranscripts"


def get_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(WEBEX_TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "meeting:transcripts_read",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def list_transcripts(token: str, meeting_id: str = None) -> list:
    params = {"meetingId": meeting_id} if meeting_id else {}
    resp = requests.get(
        WEBEX_TRANSCRIPTS_URL,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
    )
    print(f"API status: {resp.status_code}  response: {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json().get("items", [])


def download_transcript(token: str, download_url: str) -> str:
    resp = requests.get(download_url, headers={"Authorization": f"Bearer {token}"})
    resp.raise_for_status()
    return resp.text


def vtt_to_text(vtt: str) -> str:
    lines = []
    for line in vtt.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.startswith("NOTE"):
            continue
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    meeting_id = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    raw_vtt = "--vtt" in sys.argv

    if not meeting_id:
        print("No meeting ID given — listing all available transcripts...")

    # Personal access token takes priority (get it from developer.webex.com)
    token = os.environ.get("WEBEX_TOKEN")
    if token:
        print("Using personal access token.")
    else:
        client_id = os.environ.get("WEBEX_CLIENT_ID")
        client_secret = os.environ.get("WEBEX_CLIENT_SECRET")
        if not client_id or not client_secret:
            print("Error: set WEBEX_TOKEN (personal) or WEBEX_CLIENT_ID + WEBEX_CLIENT_SECRET (service app) in .env")
            sys.exit(1)
        print("Authenticating with service app credentials...")
        token = get_token(client_id, client_secret)

    if meeting_id:
        print(f"Fetching transcripts for meeting {meeting_id}...")
    items = list_transcripts(token, meeting_id)

    if not items:
        print("No transcripts found. Make sure CC was enabled during the meeting and it has ended.")
        sys.exit(0)

    print(f"Found {len(items)} transcript(s).\n")
    for i, item in enumerate(items):
        print(f"[{i}] {item.get('topic', 'N/A')}  —  {item.get('meetingStartTime', 'N/A')}")

    index = 0
    if len(items) > 1:
        index = int(input("\nWhich transcript? Enter index: "))

    content = download_transcript(token, items[index]["downloadUrl"])

    if raw_vtt:
        print(content)
    else:
        print("\n--- Transcript ---")
        print(vtt_to_text(content))
