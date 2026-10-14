# Teams / Microsoft Graph Access: Setup

**Goal**: let PMO Intelligence read the consultant group chats it is explicitly added to, and nothing else.
**Route**: route A (decided 2026-10-13, see "Part C"): find every group chat titled `PRJ ITC …` through one PMO account's chat list, add the Teams app to each through Graph, and read each with resource-specific consent (RSC). Before 2026-10-13 the route was RSC with the app added to each chat by hand, and application permission `Chat.Read.All` requested in parallel as the fallback (left ungranted; not chosen).
**Tenant**: Information Tech Consultants (`2b32b1fa-7899-482e-a6de-be99c0ff5516`)
**Status**: 2026-10-13: route A chosen; its two permissions added to the app registration, not yet consented ("Part C"); opening the Teams app showed "This app is not available. Please check with your admin"; the app's certificate sign-in works and its token holds no application permission. A1–A3 done 2026-10-06 (app-only sign-in verified). A4: the package was submitted via "Submit an app to your org" on 2026-10-06, and the Teams app **PMO Intelligence 1.0.0 was seen published in the Teams admin center on 2026-10-08** (approval done; no ticket number was issued). Its availability is the org-wide default, *everyone, including guests and external users*: to be narrowed to the PMO team (BACKLOG). Installed for no one yet. Still open: chat RSC state (admin step 1) and the A5 read test, both before Phase 3 watches real chats.
**Research date**: 2026-10-06. Graph rules change, so re-check the linked Microsoft pages before acting.

| Part | Who | Needs admin rights? |
|------|-----|---------------------|
| A. Certificate, app registration, Teams app package, test | Project developer | No (tenant lets users register apps) |
| B. Check the RSC setting, approve the Teams app, decide on the fallback | Tenant administrator (Global or Teams Administrator) | Yes |

---

## Part A: Developer steps

Run from the repository root in PowerShell, signed in to the Azure CLI as yourself (`az login`, then check with `az account show`).

### A1. Create the certificate
```powershell
powershell -ExecutionPolicy Bypass -File scripts\teams\New-GraphCertificate.ps1
```
- Add `-GeneratePassword` to write a random `.pfx` password to `pmo-intelligence-graph.pfx-password.txt` in the same folder instead of being prompted. Move it into a password manager afterwards.
- This writes `pmo-intelligence-graph.cer` (public) and `pmo-intelligence-graph.pfx` (private, password-protected) to `%USERPROFILE%\pmo-intelligence-secrets\`, outside the repo.
- Record the thumbprint and expiry date it prints. The `.pfx` never goes into git, email or chat; later it goes to AWS Secrets Manager.

### A2. Register the Graph app
```powershell
powershell -ExecutionPolicy Bypass -File scripts\teams\Register-GraphApp.ps1
```
- This creates the single-tenant app **PMO Intelligence Graph** and its service principal, uploads the `.cer`, and adds `Chat.Read.All` as a requested but **ungranted** permission (the fallback).
- Record the **Graph app (client) ID** it prints.
- If it fails with a permissions error, the tenant has restricted app registration. Add that to the admin request in Part B: ask the admin to create the app and add you as an owner.

### A3. Build the Teams app package
```powershell
uv run python teams-app\build_package.py --app-id d3b0556f-bcf2-4a5a-8d05-37f40aaa03b3
```
- Output: `teams-app\build\pmo-intelligence-teams-app.zip`. It declares only `ChatMessage.Read.Chat` and `ChatMember.Read.Chat`.
- The description users see in the chat states what the app reads and how to stop it.

### A4. Submit the app and add it to one test chat
1. Create a test group chat with one colleague (not a real consultant chat yet).
2. In Teams: **Apps → Manage your apps → Upload an app**.
   - If **Upload a custom app** is offered: upload the zip, then add it to the test chat. Teams shows the two permissions, and as a chat member you consent.
   - If only **Submit an app to your org** is offered: submit the zip. The admin approves it in Part B, and then you add it to the test chat from the Apps store under "Built for your org".
3. Get the chat ID: open the chat in **Teams on the web** and copy the `19:...@thread.v2` part of the URL.

If Teams accepts the package but doesn't offer it in the chat's **+ Add apps** list, Teams needs the app to declare a chat capability. Raise it in the next session and a minimal chat tab will be added to the package.

### A5. Verify read access
```powershell
uv run --with msal --with requests python scripts\teams\verify_chat_access.py --tenant-id 2b32b1fa-7899-482e-a6de-be99c0ff5516 --app-id d3b0556f-bcf2-4a5a-8d05-37f40aaa03b3 --chat-id "<19:...@thread.v2>" --pfx "$env:USERPROFILE\pmo-intelligence-secrets\pmo-intelligence-graph.pfx" --pfx-password-file "$env:USERPROFILE\pmo-intelligence-secrets\pmo-intelligence-graph.pfx-password.txt"
```
The script prints three checks: token, RSC grants and message read. It shows message times, types and authors only, never content. Success means the RSC route works end to end, and the fallback isn't needed.

---

## Part B: Request to the tenant administrator

Send this after A2 (and A4 if you used "Submit an app to your org"). Fill in the angle-bracket values.

> **Subject: Approval request: "PMO Intelligence" Teams app (read access to selected PMO group chats)**
>
> Hi,
>
> For the new PMO Intelligence tool, I need read access to the Teams group chats where our consultants post their placement updates. There is one chat per consultant. Access is granted per chat, through resource-specific consent (RSC): the app reads only the chats it is explicitly added to and stays visible in each one. It cannot read any other chat or channel, it never posts, and it takes no automated action.
>
> I have already registered the Entra app **PMO Intelligence Graph** (app ID `d3b0556f-bcf2-4a5a-8d05-37f40aaa03b3`, certificate credential, no client secret). I need three things from you:
>
> 1. **Confirm chat RSC is allowed.** Please run:
>    `Connect-MgGraph -Scopes "TeamworkAppSettings.ReadWrite.All"` then `Get-MgBetaChatRscConfiguration` (Microsoft.Graph.Beta module).
>    `ManagedByMicrosoft` (the default) or `EnabledForAllApps` means nothing needs changing. If it shows `DisabledForAllApps`, please let me know.
> 2. **Approve the Teams app "PMO Intelligence".** I've submitted it for org approval (Teams admin center → Teams apps → Manage apps; it should show as pending). It requests only the RSC permissions `ChatMessage.Read.Chat` and `ChatMember.Read.Chat`. Please publish it and make it available to the PMO team: `<names or group>`.
> 3. **Fallback only, no action now:** the app registration also lists the application permission `Chat.Read.All`, **not granted**. Please don't consent to it unless chat RSC turns out to be blocked. In that case we'd discuss it first, since it's tenant-wide.
>
> For our records, could you also give me a ticket number for this request?
>
> Thanks,
> `<your name>`

---

## Part C: Reading every PRJ ITC chat (route A, decided 2026-10-13)
**Requirement** (user, 2026-10-13): read every group chat whose title has the form `PRJ ITC <stack> - <consultant> - <client> - <start> - <end>`, for example `PRJ ITC DS - Stephen Owusu - UST Global - 21/9/2026 - 21/09/2027`. `PRJ ITC` marks a PMO group. The title is the quick-add line format, so each chat maps to its placement by consultant, client and start date.

**How it works**:
1. **Find**: list the chats of the PMO accounts that between them are members of every `PRJ ITC` chat (named 2026-10-13: `Sunny.Dhanoe@InformationTechConsultants.com` and `uttam.kumar@InformationTechConsultants.com`; the lists are merged by chat ID) (`GET /users/{id}/chats`, application `Chat.ReadBasic.All`: chat titles and members, not messages) and keep the `PRJ ITC` titles.
2. **Join**: add the Teams app "PMO Intelligence" to each such chat that does not have it (`POST /chats/{id}/installedApps` with its RSC permissions in `consentedPermissionSet`, application `TeamsAppInstallation.ReadWriteAndConsentSelfForChat.All`; the plainer `TeamsAppInstallation.ReadWriteSelfForChat.All` cannot install an app that needs RSC). Each chat shows that the app was added.
3. **Read**: poll each chat's messages with the RSC permission `ChatMessage.Read.Chat` (see "Engineering notes").

| Application permission | App role ID | Why |
|------------------------|-------------|-----|
| `Chat.ReadBasic.All` | `b2e060da-3baf-4687-9611-f4ebc0f0cbde` | Find the `PRJ ITC` chats by title |
| `TeamsAppInstallation.ReadWriteAndConsentSelfForChat.All` | `ba1ba90b-2d8f-487e-9f16-80728d85bb5c` | Add the app to each found chat and grant its chat RSC |

Role IDs read from the tenant's Microsoft Graph service principal on 2026-10-13. Both were added to the app registration on 2026-10-13 with `az ad app permission add` (not by `Register-GraphApp.ps1`, which adds only `Chat.Read.All`); not yet granted. Not chosen: route B, application `Chat.Read.All`, a Microsoft protected API that reads every chat in the tenant.

**Still to confirm before Sprint 4 builds on it**: that `Chat.ReadBasic.All` is not a protected API (Microsoft's protected-API page could not be opened on 2026-10-13); whether the Teams app's availability settings also govern an install through Graph; whether a package with RSC permissions only installs into a chat this way.

**Discovery check (2026-10-14, read-only: chat lists only, nothing installed, no message read)**: admin consent was granted on 2026-10-14, and the app's token holds `Chat.ReadBasic.All`, `TeamsAppInstallation.ReadWriteAndConsentSelfForChat.All` and also `Chat.Read.All` (granted with the others, though the request asked to leave it ungranted). Kept granted for now as a fallback (user decision 2026-10-14); the code calls Graph only for `PRJ ITC` chats. `GET /users/{id}/chats` answered for both accounts, so `Chat.ReadBasic.All` works app-only without a protected-API approval. Sunny Dhanoe: 504 chats, 326 group chats, 147 titled `PRJ ITC`; Uttam Kumar: 3,383 chats, 2,822 group chats, 124 titled `PRJ ITC`; together 151 distinct `PRJ ITC` chats (whether any exists outside both lists is not known). Only 42 of the 151 titles parse with the quick add's line parser: 57 differ in separators (no space round a dash, dates in brackets, an extra or missing part), 40 write a date as D/M/YY or YYYY-MM-DD, 10 write the prefix `PRJ ITC-` or with a dash after `PRJ ITC`, and 2 have an end date before the start; 41 use en dashes. The list includes old engagements (titles with 2021 and 2025 dates). Still not tested: an install through Graph, and whether the Teams app's "not available" state blocks it.

**Request to the tenant administrator** (after the two permissions are added to the app registration; sent, and consent granted 2026-10-14):

> PMO Intelligence needs to read the PMO group chats, the chats titled "PRJ ITC …" (one per consultant placement), and nothing else. Please grant tenant-wide admin consent (Entra → App registrations → PMO Intelligence Graph → API permissions → Grant admin consent) to two application permissions on the Entra app **PMO Intelligence Graph** (app ID `d3b0556f-bcf2-4a5a-8d05-37f40aaa03b3`):
>
> - `Chat.ReadBasic.All`: read the names and members of chats, not their messages. The service lists the chats of Sunny Dhanoe and Uttam Kumar, who are in every PMO group chat, and keeps only the "PRJ ITC" ones.
> - `TeamsAppInstallation.ReadWriteAndConsentSelfForChat.All`: lets the PMO Intelligence Teams app add itself to those chats and grant its own chat-level read permission there. Every chat shows that the app was added, and removing it from a chat stops the reading.
>
> Messages are read only in those chats, with the chat-level permission `ChatMessage.Read.Chat`. The app never posts and takes no automated action. Please also confirm that chat RSC is not `DisabledForAllApps` (`Get-MgBetaChatRscConfiguration`), and check why the Teams app "PMO Intelligence" shows "This app is not available. Please check with your admin" (Teams admin center → Manage apps → PMO Intelligence: status, publishing state, users and groups). The fallback `Chat.Read.All` is still not needed; please leave it ungranted.

---
## Results to record (goes into the Sprint 0 handover)

| Item | Value |
|------|-------|
| Tenant ID | `2b32b1fa-7899-482e-a6de-be99c0ff5516` |
| Graph app (client) ID | `d3b0556f-bcf2-4a5a-8d05-37f40aaa03b3` (created 2026-10-06; app-only sign-in verified, no roles granted) |
| Teams app ID | `0f2eaf35-928a-4321-9261-692893f270ff` |
| Certificate thumbprint and expiry date | `F46877044D95A517407208FF2D2FE9F382684BD3`, expires 2027-10-06 |
| Chat RSC state (admin step 1) | not yet confirmed (needs a Teams or Global admin; before Phase 3) |
| Teams app approved (date) | submitted 2026-10-06; seen **published, version 1.0.0** on 2026-10-08 (exact approval date not recorded). Available to: everyone (org-wide default, including guests and external users), to be narrowed to the PMO team. Installed for: no one |
| Fallback `Chat.Read.All` status | granted 2026-10-14 with the route A permissions (not asked for; see Part C). Kept granted for now as a fallback (user decision 2026-10-14); the code calls Graph only for `PRJ ITC` chats. |
| Admin ticket number | none issued: the app was approved without one (Sprint 0 exit gate met by the approval itself, user decision 2026-10-08) |
| Test chat verified (A5 date) | not yet run (before Phase 3) |
| Route A permissions (Part C) | added to the app registration 2026-10-13; admin consent granted 2026-10-14 (with `Chat.Read.All` as well) |
| PMO accounts covering every `PRJ ITC` chat | `Sunny.Dhanoe@InformationTechConsultants.com`, `uttam.kumar@InformationTechConsultants.com` (named by the user 2026-10-13); 151 distinct `PRJ ITC` chats between them on 2026-10-14 |

---

## Research findings

| Topic | Finding | Source |
|-------|---------|--------|
| Cost | "Starting August 25, 2025, the Teams APIs are no longer metered, and no billing configuration is required." | [Metered APIs list](https://learn.microsoft.com/en-us/graph/metered-api-list) |
| Least privilege | For `GET /chats/{chat-id}/messages`, the least-privileged application permission is RSC `ChatMessage.Read.Chat`; `Chat.Read.All` is listed as higher-privileged | [List messages in a chat](https://learn.microsoft.com/en-us/graph/api/chat-list-messages?view=graph-rest-1.0) |
| Tenant control of chat RSC | Default `ManagedByMicrosoft` (chat members may consent); can be `EnabledForAllApps` or `DisabledForAllApps`; viewing it needs Global Admin, Global Reader, Teams Admin or Privileged Role Admin | [Grant RSC permissions](https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/rsc/grant-resource-specific-consent) |
| Who consents | For application RSC on a chat, a chat member consents at install | [RSC overview](https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/rsc/resource-specific-consent) |
| One Teams app per Entra app | "There must be a 1:1 mapping between a Teams app and a Microsoft Entra app" | [Grant RSC permissions](https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/rsc/grant-resource-specific-consent) |
| Protected-API approval for `Chat.Read.All` | **Unconfirmed.** Microsoft's protected-API request page no longer resolves. If an app-only call with `Chat.Read.All` fails with a protected-API error, approval is still required. | [Teams Export APIs](https://learn.microsoft.com/en-us/microsoftteams/export-teams-content) |
| Capability needed for chat install | **Unconfirmed** whether a package with only RSC permissions (no tab or bot) can be added to a chat; step A4 tests it | — |
| Meetings (Phase 5) | RSC also offers `OnlineMeetingRecording.Read.Chat` and `OnlineMeetingTranscript.Read.Chat` for meetings associated with a watched chat (not requested now) | [RSC overview](https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/rsc/resource-specific-consent) |
| Permission IDs (checked against the tenant) | `Chat.Read.All` app role `6b7d71aa-70aa-4810-a8d9-5d9fb2830017`; RSC `ChatMessage.Read.Chat` `9398c3de-3f6b-4958-90f3-5098714ff50c`, `ChatMember.Read.Chat` `e854bbc6-07e3-45cc-af99-b6e78fab5b80` | Graph service principal in tenant |

## Engineering notes (for Phase 3)
- Poll each watched chat with `GET /chats/{id}/messages?$orderby=lastModifiedDateTime desc&$filter=lastModifiedDateTime gt {watermark}`. `$filter` only works when `$orderby` uses the same property. Ascending order isn't supported, and `$top` is at most 50.
- Store the watermark on `teams_groups`. Edits and deletions show up as newer `lastModifiedDateTime` values.
- System event messages (for example "member added") come through with `messageType` = `systemEventMessage` and must be filtered out before the chat pipeline.
- The app must call from the tenant that owns the chat. Chats in a partner tenant need that tenant's own consent.
