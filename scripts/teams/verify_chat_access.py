"""Check that the PMO Intelligence Graph app can read a group chat it has been added to.

Signs in app-only with the certificate (.pfx) and calls Graph for one chat. Prints status codes
and message metadata only (time, type, author name), never message bodies.

Usage:
    uv run --with msal --with requests python scripts/teams/verify_chat_access.py \
        --tenant-id <tenant> --app-id <graph app id> --chat-id "19:...@thread.v2" \
        --pfx "%USERPROFILE%/pmo-intelligence-secrets/pmo-intelligence-graph.pfx"
"""

import argparse
import getpass
import sys

import msal
import requests

GRAPH = "https://graph.microsoft.com"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--app-id", required=True, help="Graph app (client) ID")
    parser.add_argument("--chat-id", required=True, help="Chat thread ID, e.g. 19:...@thread.v2")
    parser.add_argument("--pfx", required=True, help="Path to pmo-intelligence-graph.pfx")
    parser.add_argument("--pfx-password-file", help="File holding the .pfx password (otherwise prompted)")
    args = parser.parse_args()

    if args.pfx_password_file:
        with open(args.pfx_password_file, encoding="utf-8") as f:
            passphrase = f.read().strip()
    else:
        passphrase = getpass.getpass("PFX password: ")

    app = msal.ConfidentialClientApplication(
        args.app_id,
        authority=f"https://login.microsoftonline.com/{args.tenant_id}",
        client_credential={"private_key_pfx_path": args.pfx, "passphrase": passphrase},
    )
    token = app.acquire_token_for_client(scopes=[f"{GRAPH}/.default"])
    if "access_token" not in token:
        sys.exit(f"Token request failed: {token.get('error')}: {token.get('error_description')}")
    print("1. App-only token: OK")
    headers = {"Authorization": f"Bearer {token['access_token']}"}

    grants = requests.get(f"{GRAPH}/beta/chats/{args.chat_id}/permissionGrants", headers=headers, timeout=30)
    if grants.ok:
        mine = [g for g in grants.json().get("value", []) if g.get("clientAppId") == args.app_id]
        names = sorted(g.get("permission") for g in mine)
        print(f"2. RSC grants for this app in the chat: {names or 'none'}")
    else:
        print(f"2. RSC grant lookup: HTTP {grants.status_code} (informational only)")

    resp = requests.get(
        f"{GRAPH}/v1.0/chats/{args.chat_id}/messages", params={"$top": 5}, headers=headers, timeout=30
    )
    if not resp.ok:
        detail = resp.json().get("error", {}).get("message", resp.text[:300])
        sys.exit(f"3. Read messages: FAILED, HTTP {resp.status_code}: {detail}")

    messages = resp.json().get("value", [])
    print(f"3. Read messages: OK, {len(messages)} most recent message(s)")
    for m in messages:
        user = ((m.get("from") or {}).get("user") or {}).get("displayName") or "-"
        print(f"   {m.get('createdDateTime')}  {m.get('messageType'):<20} {user}")
    print("\nThe app can read this chat. Send the results table in TEAMS-GRAPH-SETUP.md section 5.")


if __name__ == "__main__":
    main()
