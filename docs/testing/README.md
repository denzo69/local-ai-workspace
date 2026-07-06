# Testing

Local AI Workspace uses pytest, branch coverage, JUnit XML output and HTML coverage reports.

## Quick command

```powershell
python -m pytest
```

The default options live in `pytest.ini` so local and CI test behavior stay aligned.

## Reports

Running pytest writes:

- `reports/coverage.xml` — coverage XML for CI tooling
- `reports/junit.xml` — JUnit test report
- `reports/htmlcov/` — browsable HTML coverage report
- `reports/pytest-output.txt` — captured CI terminal output

## Current baseline

Verified local baseline:

- 419 tests passing locally
- 93% total test coverage with branch coverage enabled
- Coverage gate: 60% minimum baseline guard
- CI matrix: Python 3.10, 3.11 and 3.12 on Ubuntu

The suite has since been expanded with additional learning/dev coverage tests; update the exact count only after the full suite has been re-run successfully.

## Eval and hardening coverage

The project includes deterministic and regression-oriented coverage for:

- response planning and answer grounding
- prompt-injection boundaries
- high-risk destructive action refusal
- manual AI behavior routing
- RAG/source boundaries
- web-search routing
- memory governance
- auth/session behavior
- tool routing and tool risk policies
- codebase-map and developer tooling
- persona/context handling
- autonomous learning and learning-review flows

Documented eval baselines include:

- 10,000 question chains
- 40,000 routing checks
- bilingual behavior evals
- focus behavior evals

## Coverage roadmap

Practical staged targets:

1. 60% — baseline regression guard
2. 75% — dev-team quality gate
3. 85% — strong portfolio gate
4. 90%+ — advanced branch coverage target

Avoid chasing 100% unless the remaining paths are meaningful and maintainable to test.
