# AI Tools Used in This Project

Per the challenge's compliance requirements, this document acknowledges the AI programming tools used during development and how.

## Tools

* **Claude (Anthropic)** — primary collaborator. Used via Claude Code / Claude.ai for:
  * Architecture brainstorming
  * Schema design and review
  * Initial agent prompt drafting
  * Code scaffolding (Python + TypeScript)
  * Documentation drafting
  * Critique of prior iterations of the same files
* **TRAE** — used as an inline coding assistant for refactors and small edits within the IDE.

## Where AI was used

The boundary is roughly: AI tools drafted the scaffolding; human review shaped the schema, security/compliance posture, and the agent prompts; AI assisted with idiomatic library usage (FastAPI, LangGraph, ReactFlow).

Specifically, AI was useful for:

* Boilerplate Pydantic models and their tests.
* The shape of the LangGraph state machine and its conditional edges.
* React component layouts and Tailwind utility class choices.
* Documentation prose.
* Mock-data generation for the demo mode.

Human judgment is responsible for:

* The three-pillar schema choice (function tree + pricing + user profile).
* The decision to enforce the QC feedback loop via state-injected rework notes (rather than a soft "please redo" instruction).
* The compliance posture around robots.txt, rate limiting, and PII redaction.
* All explicit safety constraints in the system prompts.
* All architectural decisions about extensibility (market profile abstraction, schema_version persistence).

## Verification

All AI-suggested code was reviewed before being committed. The codebase compiles, the test suite runs, and the schema is enforced by Pydantic — none of which the AI claims credit for without the developer running them.

## License

This file does not waive any rights; the project is MIT-licensed per `LICENSE`.
