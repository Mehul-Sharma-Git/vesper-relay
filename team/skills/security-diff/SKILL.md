---
name: security-diff
description: Use when a candidate changes authentication, authorization, untrusted input, credentials, file or process access, or another trust boundary.
---

# Security diff review

Trace each changed input from its source and principal through validation
and access checks to a sensitive action. Include unchanged callees when
the patch changes reachability or assumptions. Start with attacker
capability and reproducible impact rather than pattern matches alone.

| Surface | Probe |
| --- | --- |
| Object IDs or tenant selectors | Use a valid ID from another principal; inspect writes, bulk reads, and existence leakage. |
| File paths, URLs, or shell arguments | Follow canonicalization, traversal or symlink behavior, redirects, and argument boundaries to the sink. |
| HTML, SQL, templates, or commands | Verify context-appropriate escaping or parameterization at the actual sink. |
| Cookies, tokens, or credentials | Check expiry and principal binding, log redaction, and accidental propagation to untrusted clients or services. |
| Dependency or configuration | Identify new privileges, executable hooks, reachable behavior, and fallback defaults. |

Example: a new download route checks authentication, then uses the supplied
attachment ID directly. Verify that resource lookup binds to the active
account and that a foreign ID cannot reveal metadata or file bytes.
Review access at the enforced boundary; client controls are not proof.

Review read-only. Use isolated, approved fixtures if proving a finding;
never target live services or expose secrets. Report path, source,
principal, sink, unmet check, practical consequence, and focused fix.
State uncertainty separately. See [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/).
