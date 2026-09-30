# Security and trust boundaries

The runtime loads only locally built static artifacts. It does not call a model,
execute shell commands, or accept arbitrary dialogue expressions from a provider.
The authoring CLI has no API credentials and performs no network calls. Its
provider integration boundary is request-file export and response-file import.

Content and save files are trusted local game assets, not a sandbox for hostile
mods or network clients. GDScript's underscore fields express API boundaries, not
access control. Review approvals are tamper-evident content/input hash bindings,
not cryptographic proof of reviewer identity. Protect your review files and build
pipeline using your own access controls.

Do not include secrets, private story packets, or reviewer personal data in a
public bug report. If a report requires private details, redact them and provide a
minimal synthetic reproduction first. GitHub Actions uses public dependency
fetches, read-only repository permissions, and no model credentials.
