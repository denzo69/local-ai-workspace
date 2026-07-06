# Limitations

Local AI Workspace is a portfolio-stage local-first AI assistant project. It is not production-ready without additional operational and enterprise hardening.

## Current boundaries

- The app is intended for local or trusted-network use, not direct public internet exposure.
- Web search returns sources and cautious summaries, but source claims are not automatically guaranteed as true.
- Local model quality depends on the installed Ollama model and local hardware.
- Some internal names originate from the earlier Finnish prototype stage.
- Production deployment would require additional hardening, monitoring, user management and operational review.

## Before production use

A production-grade deployment would need at least:

- hardened identity and access management
- monitored secrets handling
- rate limiting and abuse protection
- deployment environment separation
- observability, metrics and alerting
- backup and restore verification
- rollback strategy
- dependency and image vulnerability policy
- formal data retention policy
- security review for tool execution boundaries

## Positioning

The correct public positioning is:

> Portfolio-stage local-first AI workspace demonstrating practical AI engineering.

Avoid presenting it as:

> Production-ready SaaS platform.
