# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately to the repository owner through GitHub's security advisory feature. Do not open a public issue containing credentials, exploit details, personal data, or an unpatched proof-system weakness.

## Deployment guidance

- Treat this repository as a research prototype and place public deployments behind TLS, authentication, rate limiting, and request-size limits.
- Store API credentials and signing keys in a secret manager or local `.env` file that is never committed.
- The Hardhat default private key used by the local development stack is public and unsafe for real funds or public networks.
- Restrict access to generated claims, evidence, uploaded images, model transcripts, and proof packages; they may contain sensitive or copyrighted material.
- Pin and review dependencies, and repeat trusted-setup validation before production use.
- The ZK circuits prove membership and deterministic input binding only. They do not prove source truth, retrieval completeness, model execution, or verdict correctness.

## Supported versions

Security fixes are applied to the latest revision on the default branch.
