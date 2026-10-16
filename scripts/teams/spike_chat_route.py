"""Try the Teams chat route on the tenant, one step at a time (Sprint 4 spike).

Signs in app-only with the Graph app's certificate (.pfx), as verify_chat_access.py
does, and runs one step per command against a test chat. Prints ids, times, types and
status codes only, never message bodies.

Steps, in order:
    find           list an account's chats whose title starts with a prefix
                   (Chat.ReadBasic.All)
    install        add the Teams app to the chat with its RSC permissions
                   (TeamsAppInstallation.ReadWriteAndConsentSelfForChat.All); refused
                   with AppScopeIsNotAllowed while the app has no group-chat capability
    installed      show whether the app is installed in the chat and its RSC grants
    members        list the chat's members (Chat.ReadBasic.All, or RSC)
    messages       read the chat's latest messages (Chat.Read.All, or RSC)
    subscribe      subscribe to one chat's messages (--chat-id, Chat.Read.All), or to
                   every chat the app is installed in (--catalog-id,
                   Chat.Read.WhereInstalled); without resource data either way
    subscriptions  list this app's subscriptions
    unsubscribe    delete a subscription
    remove         remove the Teams app from the chat again

Usage (common options first, then the step), with SECRETS standing for
%USERPROFILE%/pmo-intelligence-secrets:
    uv run --with msal --with requests python scripts/teams/spike_chat_route.py
        --pfx "SECRETS/pmo-intelligence-graph.pfx"
        --pfx-password-file "SECRETS/pmo-intelligence-graph.pfx-password.txt"
        find --account you@InformationTechConsultants.com --prefix "PRJ ITC TEST"
"""

import argparse
import getpass
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import msal
import requests

GRAPH = "https://graph.microsoft.com"
TENANT_ID = "2b32b1fa-7899-482e-a6de-be99c0ff5516"
GRAPH_APP_ID = "d3b0556f-bcf2-4a5a-8d05-37f40aaa03b3"
# The RSC permissions the manifest declares (teams-app/manifest.template.json); the
# install must consent to exactly these.
RSC_PERMISSIONS = ["ChatMessage.Read.Chat", "ChatMember.Read.Chat"]
TIMEOUT = 30

Json = dict[str, Any]


def token(args: argparse.Namespace) -> str:
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
    result = app.acquire_token_for_client(scopes=[f"{GRAPH}/.default"])
    if "access_token" not in result:
        error = f"{result.get('error')}: {result.get('error_description')}"
        sys.exit(f"Token request failed: {error}")
    return str(result["access_token"])


def fail(step: str, resp: requests.Response) -> None:
    try:
        error = resp.json().get("error", {})
        detail = f"{error.get('code')}: {error.get('message')}"
    except ValueError:
        detail = resp.text[:300]
    # Graph's terse codes ("BadRequest") hide the cause in the body; show all of it.
    sys.exit(f"{step}: FAILED, HTTP {resp.status_code}: {detail}\n{resp.text[:2000]}")


def get_all(
    session: requests.Session, url: str, params: Json | None = None
) -> list[Json]:
    items: list[Json] = []
    next_url: str | None = url
    while next_url:
        resp = session.get(next_url, params=params, timeout=TIMEOUT)
        if not resp.ok:
            fail(f"GET {url}", resp)
        body = resp.json()
        items.extend(body.get("value", []))
        next_url = body.get("@odata.nextLink")
        params = None  # the next link carries them
    return items


def app_installations(
    session: requests.Session, args: argparse.Namespace
) -> list[Json]:
    return get_all(
        session,
        f"{GRAPH}/v1.0/chats/{args.chat_id}/installedApps",
        {"$expand": "teamsApp", "$filter": f"teamsApp/id eq '{args.catalog_id}'"},
    )


def find(session: requests.Session, args: argparse.Namespace) -> None:
    chats = get_all(session, f"{GRAPH}/v1.0/users/{args.account}/chats", {"$top": 50})
    prefix = args.prefix.casefold()
    found = [
        c for c in chats if (c.get("topic") or "").strip().casefold().startswith(prefix)
    ]
    print(f"find: {len(chats)} chats for {args.account}; {len(found)} match the prefix")
    for c in found:
        print(f"   {c['id']}  {c.get('chatType'):<10} {c.get('topic')}")


def install(session: requests.Session, args: argparse.Namespace) -> None:
    body = {
        "teamsApp@odata.bind": f"{GRAPH}/v1.0/appCatalogs/teamsApps/{args.catalog_id}",
        "consentedPermissionSet": {
            "resourceSpecificPermissions": [
                {"permissionValue": p, "permissionType": "Application"}
                for p in RSC_PERMISSIONS
            ]
        },
    }
    url = f"{GRAPH}/v1.0/chats/{args.chat_id}/installedApps"
    resp = session.post(url, json=body, timeout=TIMEOUT)
    if resp.status_code == 409:
        print("install: already installed (HTTP 409)")
        return
    if not resp.ok:
        fail("install", resp)
    print(f"install: OK, HTTP {resp.status_code}")


def installed(session: requests.Session, args: argparse.Namespace) -> None:
    apps = app_installations(session, args)
    print(f"installed: {len(apps)} installation(s) of the app in the chat")
    for a in apps:
        name = (a.get("teamsApp") or {}).get("displayName")
        print(f"   installation {a['id']}  {name}")
    url = f"{GRAPH}/v1.0/chats/{args.chat_id}/permissionGrants"
    resp = session.get(url, timeout=TIMEOUT)
    if resp.ok:
        grants = resp.json().get("value", [])
        names = sorted(
            g.get("permission") for g in grants if g.get("clientAppId") == args.app_id
        )
        print(f"   RSC grants for this app: {names or 'none'}")
    else:
        print(f"   RSC grant lookup: HTTP {resp.status_code} (informational only)")


def members(session: requests.Session, args: argparse.Namespace) -> None:
    people = get_all(session, f"{GRAPH}/v1.0/chats/{args.chat_id}/members")
    print(f"members: OK, {len(people)} member(s)")
    for m in people:
        print(f"   {m.get('userId')}  {m.get('displayName')}  roles={m.get('roles')}")


def messages(session: requests.Session, args: argparse.Namespace) -> None:
    resp = session.get(
        f"{GRAPH}/v1.0/chats/{args.chat_id}/messages",
        params={"$top": args.top, "$orderby": "createdDateTime desc"},
        timeout=TIMEOUT,
    )
    if not resp.ok:
        fail("messages", resp)
    items = resp.json().get("value", [])
    print(f"messages: OK, {len(items)} most recent")
    for m in items:
        author = ((m.get("from") or {}).get("user") or {}).get("id") or "-"
        deleted = " deleted" if m.get("deletedDateTime") else ""
        kind = f"{m.get('messageType'):<20}"
        print(f"   {m['id']}  {m.get('createdDateTime')}  {kind} {author}{deleted}")


def subscribe(session: requests.Session, args: argparse.Namespace) -> None:
    expires = datetime.now(UTC) + timedelta(minutes=args.minutes)
    if args.chat_id:
        resource = f"/chats/{args.chat_id}/messages"
    else:
        resource = (
            f"/appCatalogs/teamsApps/{args.catalog_id}/installedToChats/getAllMessages"
        )
    body: Json = {
        "changeType": args.change_type,
        "notificationUrl": args.notification_url,
        "resource": resource,
        "includeResourceData": False,
        "expirationDateTime": expires.isoformat().replace("+00:00", "Z"),
        "clientState": args.client_state,
    }
    if args.lifecycle_url:
        body["lifecycleNotificationUrl"] = args.lifecycle_url
    resp = session.post(f"{GRAPH}/v1.0/subscriptions", json=body, timeout=TIMEOUT)
    if not resp.ok:
        fail("subscribe", resp)
    sub = resp.json()
    print(f"subscribe: OK, subscription {sub['id']}")
    print(f"   until {sub.get('expirationDateTime')}")


def subscriptions(session: requests.Session, args: argparse.Namespace) -> None:
    subs = get_all(session, f"{GRAPH}/v1.0/subscriptions")
    print(f"subscriptions: {len(subs)}")
    for s in subs:
        print(
            f"   {s['id']}  {s.get('changeType')}  until {s.get('expirationDateTime')}"
        )
        print(f"      {s.get('resource')}")


def unsubscribe(session: requests.Session, args: argparse.Namespace) -> None:
    url = f"{GRAPH}/v1.0/subscriptions/{args.subscription_id}"
    resp = session.delete(url, timeout=TIMEOUT)
    if not resp.ok:
        fail("unsubscribe", resp)
    print(f"unsubscribe: OK, HTTP {resp.status_code}")


def remove(session: requests.Session, args: argparse.Namespace) -> None:
    apps = app_installations(session, args)
    if not apps:
        print("remove: the app is not installed in the chat")
        return
    for a in apps:
        url = f"{GRAPH}/v1.0/chats/{args.chat_id}/installedApps/{a['id']}"
        resp = session.delete(url, timeout=TIMEOUT)
        if not resp.ok:
            fail("remove", resp)
        print(f"remove: OK, installation {a['id']} removed (HTTP {resp.status_code})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tenant-id", default=TENANT_ID)
    parser.add_argument("--app-id", default=GRAPH_APP_ID, help="Graph app (client) ID")
    parser.add_argument(
        "--pfx", required=True, help="Path to pmo-intelligence-graph.pfx"
    )
    parser.add_argument("--pfx-password-file", help="File holding the .pfx password")
    steps = parser.add_subparsers(dest="step", required=True)

    p = steps.add_parser("find")
    p.add_argument("--account", required=True, help="UPN of an account in the chat")
    p.add_argument("--prefix", default="PRJ ITC TEST")

    for name in ("install", "installed", "remove"):
        p = steps.add_parser(name)
        p.add_argument("--chat-id", required=True)
        p.add_argument(
            "--catalog-id", required=True, help="Catalog id, not manifest id"
        )

    p = steps.add_parser("members")
    p.add_argument("--chat-id", required=True)

    p = steps.add_parser("messages")
    p.add_argument("--chat-id", required=True)
    p.add_argument("--top", type=int, default=10)

    p = steps.add_parser("subscribe")
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--chat-id", help="One chat's messages (Chat.Read.All)")
    target.add_argument("--catalog-id", help="Every chat the app is installed in")
    p.add_argument("--notification-url", required=True, help="Public HTTPS URL")
    p.add_argument("--client-state", required=True, help="Secret, max 128 characters")
    p.add_argument("--change-type", default="created,updated")
    p.add_argument(
        "--minutes", type=int, default=55, help="Over 60 needs a lifecycle URL"
    )
    p.add_argument(
        "--lifecycle-url", help="Public HTTPS URL for lifecycle notifications"
    )

    steps.add_parser("subscriptions")

    p = steps.add_parser("unsubscribe")
    p.add_argument("--subscription-id", required=True)

    args = parser.parse_args()
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token(args)}"
    handlers = {
        "find": find,
        "install": install,
        "installed": installed,
        "members": members,
        "messages": messages,
        "subscribe": subscribe,
        "subscriptions": subscriptions,
        "unsubscribe": unsubscribe,
        "remove": remove,
    }
    handlers[args.step](session, args)


if __name__ == "__main__":
    main()
