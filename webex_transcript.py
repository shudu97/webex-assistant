#!/usr/bin/env python3
import sys
import os
import urllib.parse
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from dotenv import load_dotenv, set_key

load_dotenv()

WEBEX_TOKEN_URL = "https://webexapis.com/v1/access_token"
WEBEX_AUTH_URL = "https://webexapis.com/v1/authorize"
WEBEX_TRANSCRIPTS_URL = "https://webexapis.com/v1/meetingTranscripts"
WEBEX_CC_URL = "https://webexapis.com/v1/meetingClosedCaptions"
WEBEX_MEETINGS_URL = "https://webexapis.com/v1/meetings"
REDIRECT_URI = "http://127.0.0.1:8050/webex/callback"
SCOPES = "meeting:admin_closed_captions_read meeting:transcripts_read"

_auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Authorization complete. You can close this tab.")

    def log_message(self, *args):
        pass


def oauth_login(auth_url: str, client_id: str, client_secret: str) -> str:
    global _auth_code

    server = HTTPServer(("127.0.0.1", 8050), CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    print("Opening browser for authorization...")
    webbrowser.open(auth_url)
    thread.join(timeout=120)
    server.server_close()

    if not _auth_code:
        print("Error: did not receive authorization code.")
        sys.exit(1)

    resp = requests.post(WEBEX_TOKEN_URL, data={
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": _auth_code,
        "redirect_uri": REDIRECT_URI,
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def list_meetings(token: str) -> list:
    resp = requests.get(
        WEBEX_MEETINGS_URL,
        params={"meetingType": "meeting", "state": "ended"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def list_closed_captions(token: str, meeting_id: str, debug: bool = False) -> list:
    resp = requests.get(
        WEBEX_CC_URL,
        params={"meetingId": meeting_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    if debug:
        print(f"CC Status: {resp.status_code}  Response: {resp.text}")
    resp.raise_for_status()
    return resp.json().get("items", [])


def list_transcripts(token: str, meeting_id: str = None, debug: bool = False) -> list:
    params = {"meetingId": meeting_id} if meeting_id else {}
    resp = requests.get(
        WEBEX_TRANSCRIPTS_URL,
        params=params,
        headers={"Authorization": f"Bearer {token}"},
    )
    if debug:
        print(f"Transcripts Status: {resp.status_code}  Response: {resp.text}")
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
    do_auth = "--auth" in sys.argv
    raw_vtt = "--vtt" in sys.argv
    meeting_id = next((a for a in sys.argv[1:] if not a.startswith("--")), None)

    client_id = os.environ.get("WEBEX_CLIENT_ID")
    client_secret = os.environ.get("WEBEX_CLIENT_SECRET")

    if do_auth:
        auth_url = os.environ.get("WEBEX_OAUTH_URL")
        if not auth_url or not client_id or not client_secret:
            print("Error: WEBEX_OAUTH_URL, WEBEX_CLIENT_ID, and WEBEX_CLIENT_SECRET must be set in .env")
            sys.exit(1)
        token = oauth_login(auth_url, client_id, client_secret)
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        set_key(env_path, "WEBEX_TOKEN", token)
        print("Token saved to .env as WEBEX_TOKEN.")
        sys.exit(0)

    token = os.environ.get("WEBEX_TOKEN")
    if not token:
        if client_id and client_secret:
            print("Authenticating with service app credentials...")
            token = oauth_login(client_id, client_secret)
        else:
            print("Error: run with --auth first, or set WEBEX_TOKEN in .env")
            sys.exit(1)

    if not meeting_id:
        print("Listing all ended meetings...\n")
        meetings = list_meetings(token)
        if not meetings:
            print("No ended meetings found.")
            sys.exit(0)
        for m in meetings:
            print(f"  ID:    {m['id']}")
            print(f"  Topic: {m.get('title', 'N/A')}  —  {m.get('start', 'N/A')}")
            print()
        sys.exit(0)

    print("Checking all transcripts on account...")
    all_items = list_transcripts(token, debug=True)
    print(f"Total transcripts on account: {len(all_items)}")

    print(f"Fetching transcripts for meeting {meeting_id}...")
    items = list_transcripts(token, meeting_id, debug=True)

    if not items:
        print("No captions or transcripts found for this meeting.")
        sys.exit(0)

    print(f"\nFound {len(items)} item(s).\n")
    for i, item in enumerate(items):
        print(f"[{i}] {item.get('topic', 'N/A')}  —  {item.get('meetingStartTime', 'N/A')}")

    index = 0
    if len(items) > 1:
        index = int(input("\nWhich one? Enter index: "))

    content = download_transcript(token, items[index]["downloadUrl"])

    if raw_vtt:
        print(content)
    else:
        print("\n--- Transcript ---")
        print(vtt_to_text(content))
