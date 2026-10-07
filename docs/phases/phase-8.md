# Phase 8: Enterprise features

Built on the `phase-8-enterprise` branch, which was merged into `develop` and then removed.

## What this phase is for

A real company will not use a safety tool that lets everyone do everything, keeps personal details forever, or cannot say who changed a setting. This phase adds what an organisation needs before it can trust MirrorGuard with real chat traffic.

## A small example

A company called Acme starts using MirrorGuard:

```bash
mirrorguard tenants create acme --name "Acme Ltd"
mirrorguard keys create acme --role engineer --name "chatbot server"
mirrorguard keys create acme --role reviewer --name "asha"
```

- The **engineer** key goes into Acme's chatbot. It can send chat traffic and read results. It cannot change the policy.
- **Asha's reviewer** key lets her open the dashboard and review flagged conversations. It cannot send chat traffic or change the policy.
- When a user writes *"call me on 98765 43210"*, the text saved for review is *"call me on [PHONE]"*. The chatbot still saw the real message.
- When an admin switches shadow mode off, the audit log records who did it, when, and what changed.

## What was built

| Part | Where | What it does |
|---|---|---|
| Tenants and keys | `tenancy/repository.py` | Organisations and their API keys, in the database |
| Roles | `tenancy/roles.py` | admin, engineer, reviewer, viewer |
| Permission checks | `api/deps.py` | Every endpoint states which permission it needs |
| Audit log | `tenancy/audit.py`, `GET /v1/audit` | Who changed what, add-only |
| Masking | `privacy/redaction.py` | Hides emails, phone numbers, card and ID numbers, links, IP addresses before storage |
| No-text mode | `store_text` in the policy | Saves risk levels and actions but never the message text |
| Retention | `mirrorguard retention purge` | Deletes old guardrail events |
| Key endpoints | `GET/POST/DELETE /v1/keys` | Admins manage their own tenant's keys |

## Who can do what

| | Send chat traffic | Read data | Review flags | Change policy, keys, see audit log |
|---|---|---|---|---|
| admin | yes | yes | yes | yes |
| engineer | yes | yes | no | no |
| reviewer | no | yes | yes | no |
| viewer | no | yes | no | no |

## Why it is built this way

- **Keys are stored as hashes.** If the database leaks, the keys do not. A key is shown once, when it is created.
- **Key lookups are cached for 30 seconds**, so a busy server does not query the database on every request. A revoked key stops working everywhere within that time.
- **Every query is filtered by tenant.** There is no endpoint that can return another tenant's data, and tests check this for each one.
- **Permissions are named on each endpoint**, in one place (`api/deps.py`), so it is easy to see and audit who can call what.
- **Masking happens on the way to storage, not on the way to the chatbot.** The user's conversation is not changed. Only what is kept for review is masked.
- **The audit log can only be added to.** The code has no way to edit or delete an entry.

## How to use it

```bash
mirrorguard tenants create <id> --name "<name>"
mirrorguard tenants list
mirrorguard keys create <tenant> --role admin|engineer|reviewer|viewer --name "<label>"
mirrorguard keys list <tenant>
mirrorguard keys revoke <tenant> <key id>
mirrorguard retention purge --days 90      # run this daily, for example from cron
```

`MG_API_KEYS` in `.env` still works and gives admin access. It is meant for local use.

## What was checked

- Automated tests for masking (including that ordinary numbers such as "3 days" are left alone), each role against each kind of endpoint, the whole life of a key, the audit log, no-text mode, retention, and the admin commands.

## What is still open

- **Masking is pattern-based.** It catches details with a recognisable shape. It does **not** catch names or street addresses. A stronger tool such as Microsoft Presidio can be plugged in behind the same interface; that has not been done.
- **No single sign-on and no user accounts.** Access is by API key. Login with company accounts (Keycloak or similar) is listed in the scale-out plan.
- **The dashboard does not hide buttons by role.** A reviewer who opens the Policy page can see it and gets a clear "your role cannot do this" message on saving.
- **The audit log is protected by the code, not by the database.** A person with direct database access could still alter it. Database-level protection is a deployment task.
- **Legal compliance (DPDP Act, GDPR) has not been reviewed by anyone qualified.** These features support compliance. They do not prove it.
