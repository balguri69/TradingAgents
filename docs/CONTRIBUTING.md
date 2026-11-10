# Developer Contribution & Repository Guidelines

*Document Version: 1.0.0 | Status: Active Engineering Standard | Scope: All Contributors*

---

## 1. Development Principles & Code of Conduct

Welcome to the **Institutional Trading Intelligence Platform**. This repository maintains institutional software engineering standards. All contributors must follow the structured processes outlined below to ensure code quality, quantitative correctness, and backward compatibility.

---

## 2. Git Branch Naming Conventions

All development must occur on dedicated feature or bugfix branches branched off `main`. Direct commits to `main` are strictly prohibited.

Branch names must follow the format: `<type>/<issue-or-milestone>-<short-description>`

### Branch Types:
- `feat/`: New feature implementation from the active roadmap milestone.
  - *Example*: `feat/m1.2-crypto-market-data-adapter`
  - *Example*: `feat/m1.3-cftc-cot-positioning`
- `fix/`: Bug fixes or regression corrections.
  - *Example*: `fix/usdjpy-forex-normalization`
  - *Example*: `fix/safe-ticker-component-regex`
- `docs/`: Documentation additions, architectural specs, and roadmap updates.
  - *Example*: `docs/data-provider-interface`
  - *Example*: `docs/agent-architecture`
- `refactor/`: Non-breaking code refactoring without functional changes.
  - *Example*: `refactor/router-dispatch-logic`
- `test/`: Test suite additions, offline fixture updates, or performance benchmarks.
  - *Example*: `test/crypto-market-data-fixtures`

---

## 3. Commit Message Standards (Conventional Commits)

Commit messages must follow the [Conventional Commits](https://www.conventionalcommits.org/) specification to ensure automated changelog generation and clear git history.

### Commit Format:
```text
<type>(<scope>): <short imperative summary>

[optional detailed description explaining the why and what]

[optional issue or milestone reference]
```

### Allowed Types:
- `feat`: A new feature mapped to [ROADMAP.md](file:///Users/balgurimukeshrao/Documents/TradingAgents-main/ROADMAP.md).
- `fix`: A bug fix or patch.
- `docs`: Documentation only changes.
- `test`: Adding missing tests or correcting existing tests.
- `refactor`: A code change that neither fixes a bug nor adds a feature.
- `perf`: A code change that improves performance or latency.
- `chore`: Maintenance tasks, dependencies, or configuration updates.

### Examples:
- `feat(m1.1): implement universal multi-asset symbol normalizer and asset classifier`
- `fix(symbols): prevent bare crypto base from being overwritten by forex regex`
- `docs(arch): add decision engine pipeline specification and agent architecture`
- `test(crypto): add offline unit tests with mocked Binance klines fixtures`

---

## 4. Directory & Folder Conventions

Code must be placed in strictly designated directories:

| Directory | Permitted Contents | Forbidden Contents |
| :--- | :--- | :--- |
| `tradingagents/agents/` | Reasoning agents, prompts, and debate logic | Raw HTTP network calls, external vendor clients |
| `tradingagents/graph/` | LangGraph workflows, conditional edges, state propagation | Analytical prompt templates, vendor data parsers |
| `tradingagents/dataflows/` | Data routers, symbol normalization, caching, date guards | Agent debate logic, terminal UI formatting |
| `tradingagents/dataflows/vendors/` | Keyless FOSS data provider adapters implementing `MarketDataProvider` | Graph state objects, business decision logic |
| `tradingagents/llm_clients/` | Client gateways to LLM providers (OpenAI, Anthropic, Gemini) | Financial data ingestion, symbol mapping |
| `cli/` | Terminal user interface, Rich formatting, questionary menus | Core financial calculations, raw API calls |
| `docs/` | Architectural specs, engineering rules, diagrams | Executable production code |
| `tests/` | Unit, integration, and regression test suites | Production application modules |
| `tests/fixtures/` | Static recorded JSON/text mock responses for offline tests | Dynamic live network scripts |

---

## 5. Pre-Submission Review Checklist

Before opening a pull request or submitting code for review, verify every item on this checklist:

- [ ] **Roadmap Alignment**: The change implements exactly **one** approved feature from [ROADMAP.md](file:///Users/balgurimukeshrao/Documents/TradingAgents-main/ROADMAP.md).
- [ ] **Backward Compatibility**: All existing stock, ETF, and index workflows remain 100% operational.
- [ ] **Zero Regression**: Existing tests (`tests/test_symbols.py`, `tests/test_safe_ticker_component.py`) pass with 0 errors and 0 failures.
- [ ] **New Automated Tests**: Dedicated unit tests covering normal paths, edge cases, and failure modes are included.
- [ ] **Offline Determinism**: No test initiates a live network connection; all tests use fixtures or mocks.
- [ ] **Zero Paid APIs**: Uses only free, open-source, keyless public REST APIs or public domain data.
- [ ] **Type Annotations**: All public functions and methods carry complete type hints.
- [ ] **Docstrings Included**: All modules, classes, and public functions have clear PEP 257 docstrings.
- [ ] **Security Sanitization**: All user-provided ticker inputs interpolated into filesystem paths pass `safe_ticker_component()`.
- [ ] **SOLID Principles**: Module adheres to Single Responsibility, Open/Closed, and Dependency Inversion principles.
- [ ] **Composition Over Inheritance**: Avoids deep inheritance hierarchies; uses interfaces or protocols.

---

## 6. Definition of Done (DoD)

A milestone feature is officially marked **Done** in [ROADMAP.md](file:///Users/balgurimukeshrao/Documents/TradingAgents-main/ROADMAP.md) only when all of the following criteria are fulfilled:

1. **Code Complete**: The feature is fully implemented according to the approved plan.
2. **Contract Compliant**: Implements the appropriate interface defined in `docs/DATA_PROVIDER_INTERFACE.md`.
3. **Tests Passing**: 100% of unit, integration, and regression tests pass deterministically.
4. **Documentation Updated**: Architectural diagrams, roadmap statuses, and module docstrings reflect the implementation.
5. **Architectural Review**: The Lead Architect has reviewed the code diff, verified compliance with [docs/CODING_STANDARDS.md](file:///Users/balgurimukeshrao/Documents/TradingAgents-main/docs/CODING_STANDARDS.md), and granted explicit written approval.
