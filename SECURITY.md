# Security

## Reporting a problem

Please do not open a public issue for a security problem.

Report it privately through GitHub: open the repository's **Security** tab and choose
**Report a vulnerability**. Describe what you found and how to reproduce it.

## What to keep in mind when running MirrorGuard

- **Never commit `.env`.** It holds your model provider key. It is listed in `.gitignore`.
- **Put HTTPS in front of the API.** Do not expose port 8000 directly to the internet.
- **Create API keys with `mirrorguard keys create`** and give each one the lowest role
  that works. Keys from `MG_API_KEYS` have full admin access and are meant for local use.
- **API keys are stored as hashes.** A key is shown once, when it is created.
- **Chat text is sensitive.** MirrorGuard masks emails, phone numbers, card and ID numbers
  before storing text. It does not mask names or addresses. Tenants who want no text
  stored at all can set `store_text` to false in their policy.
- **Run `mirrorguard retention purge` regularly** so old conversations are removed.
- **The audit log is add-only in the code**, but a person with direct database access
  could still change it. Restrict database access.

## Known limits

- The risk scorer is an AI model and can miss risk or flag harmless messages.
  MirrorGuard is a safety layer, not a guarantee, and not a medical device.
- The crisis message names a helpline for India by default. Set the right one for
  your country in the policy.
