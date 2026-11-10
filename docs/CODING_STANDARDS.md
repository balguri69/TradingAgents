# Engineering & Coding Standards: Institutional Trading Intelligence Platform

*Document Version: 2.0.0 | Status: Active Engineering Standard | Scope: Entire Repository*

---

## 1. Permanent Engineering Commandments

All code contributions, architectural modifications, and feature implementations across this repository must adhere strictly to the following core rules:

### 1. One Roadmap Feature per Implementation
- To maintain strict architectural discipline and auditability, each change or pull request must correspond to exactly **one** discrete feature from [ROADMAP.md](file:///Users/balgurimukeshrao/Documents/TradingAgents-main/ROADMAP.md).
- Never bundle unrelated refactors, speculative future asset registrations, or extraneous library integrations into an active milestone feature. Complete the scope approved in the plan and nothing more.

### 2. No Breaking Changes & Backward Compatibility Required
- Existing functionality—specifically equity, ETF, index workflows, and existing CLI capabilities—must continue to operate without regression.
- Existing regression test suites (`tests/test_symbols.py`, `tests/test_safe_ticker_component.py`, `tests/test_crypto_asset_mode.py`) must pass at 100% on every modification. Any change that alters existing public method signatures or output formats without a backward-compatible adapter will be rejected.

### 3. Every Feature Requires Tests
- Zero code is merged without dedicated automated tests.
- Unit test suites must cover:
  1. Valid standard inputs
  2. Edge cases (null values, empty strings, whitespace, unexpected casing)
  3. Boundary conditions (zeros, negative rates, extreme volatility)
  4. Failure paths (network timeouts, rate limits, malformed payloads)
- **Offline Determinism**: Tests must never rely on live external networks. All external HTTP requests must be mocked or backed by static recorded fixtures.

### 4. No Duplicated Business Logic (DRY & SSOT)
- Adhere strictly to the Single Source of Truth (SSOT) and Don't Repeat Yourself (DRY) principles.
- Symbol normalization must live strictly in [tradingagents/dataflows/symbols.py](file:///Users/balgurimukeshrao/Documents/TradingAgents-main/tradingagents/dataflows/symbols.py).
- Quantitative calculations (Sharpe, ATR, Drawdowns, Basis Points) must live in centralized mathematical modules rather than being reimplemented inside agent prompts.
- Ticker security sanitization must exclusively invoke `safe_ticker_component`.

### 5. Type Hints Required
- Complete type annotations (PEP 484, PEP 585) are mandatory on all functions, methods, parameters, and return types.
- Avoid `Any` wherever a specific type, generic, or union can be expressed.
- Use `from __future__ import annotations` across all modules.

### 6. Public Functions Require Docstrings
- All public modules, classes, functions, and methods must carry comprehensive docstrings (PEP 257) detailing:
  - Purpose and architectural context
  - Parameter definitions and types
  - Return value definitions and types
  - Explicit exceptions raised

### 7. SOLID Principles Mandatory
- **Single Responsibility Principle (SRP)**: Each class and module must have one reason to change (e.g. data fetching is separated from indicator calculation).
- **Open/Closed Principle (OCP)**: Modules must be open for extension (via new provider adapters or analyst personas) but closed for modification.
- **Liskov Substitution Principle (LSP)**: Any subclass or provider implementing `MarketDataProvider` must be completely interchangeable without breaking downstream callers.
- **Interface Segregation Principle (ISP)**: Clients should not be forced to depend on methods they do not use (e.g. specialized crypto metrics are segregated from the base provider interface).
- **Dependency Inversion Principle (DIP)**: High-level modules (analysts, graph nodes) must depend on abstractions (`MarketDataProvider`), not concrete network implementations.

### 8. Dependency Injection Preferred
- Components must not instantiate concrete network clients, clocks, or file paths internally.
- Pass dependencies explicitly into constructors or module factory functions. This ensures trivial testability via test doubles and mocks without patching global module states.

### 9. Prefer Composition Over Inheritance
- Favor decoupled, protocol-based composition over deep inheritance hierarchies.
- Define components using Python `typing.Protocol` or abstract base classes (`abc.ABC`) with minimal surface area.
- Avoid class inheritance beyond one level deep.

### 10. Free / Open Source Only Unless Explicitly Approved
- The platform must remain fully accessible using Free and Open-Source Software (FOSS) technologies.
- All data streams must use keyless public REST endpoints, public domain data (CFTC, FRED), or open-source libraries.
- Never introduce a dependency on a paid API, proprietary subscription, or mandatory credit-card-gated service without prior architectural approval.

### 11. Common Data Provider Interface Required
- All data providers must implement the universal contract detailed in [docs/DATA_PROVIDER_INTERFACE.md](file:///Users/balgurimukeshrao/Documents/TradingAgents-main/docs/DATA_PROVIDER_INTERFACE.md).
- Downstream analyst desks must never invoke vendor-specific libraries directly.

### 12. Providers Must Never Contain Trading or Analytical Logic
- **Strict Inviolable Rule**: Providers are pure data ingestion, validation, and normalization engines.
- Providers must **never** calculate moving averages, RSI, MACD, volatility bands, position sizes, or trade recommendations.
- Their responsibility is strictly limited to:
  1. Transforming domain requests into transport queries
  2. Ingesting raw responses from the injected `TransportClient`
  3. Validating schemas and error payloads
  4. Emitting immutable, standardized DTOs (`QuoteDTO`, `CandleDTO`, `OrderBookDTO`, `FundingRateDTO`)

### 13. Decoupled Transport Layer
- Providers must never import or invoke raw socket, HTTP, or WebSocket libraries directly.
- All network interaction must flow through an injected `TransportClient` abstraction. This permits running stateless REST, streaming WebSockets, or simulated backtest transports without touching provider code.

### 14. Mandatory Observability & Telemetry
- Every provider request must emit structured telemetry encapsulated in `RequestMetricsDTO`.
- Metrics captured include: `latency_ms`, `retries`, `failovers`, `cache_hit`, `provider_name`, and `status_code`.

---

## 2. Python Idioms & Language Standards

1. **Python Version**: Python 3.11+. Write modern, standard-library-first Python.
2. **String Enums**: Always use `class AssetClass(str, Enum)` with `from enum import Enum` rather than `StrEnum` to maximize interpreter compatibility.
3. **Data Classes**: Prefer `@dataclass(frozen=True)` or `typing.NamedTuple` for immutable data objects and domain entities.
4. **Imports Order**:
   - Standard library imports
   - Related third-party imports
   - Local application/library imports
   - Alphabetical sorting within each block.
5. **No Global Mutables**: Never maintain mutable state in module-level variables. Use thread-safe registries, dependency injection, or explicit context dictionaries.

---

## 3. Error Handling & Resilience Contracts

1. **Never Swallow Exceptions**: Bare `except:` or `except Exception: pass` is strictly prohibited. If an error is caught, it must be logged with context or re-raised as a domain-specific exception.
2. **Domain Exception Hierarchy**: All custom errors must inherit from a common dataflow base class in [tradingagents/dataflows/errors.py](file:///Users/balgurimukeshrao/Documents/TradingAgents-main/tradingagents/dataflows/errors.py):
   ```python
   class TradingAgentsError(Exception):
       """Base domain error for all platform exceptions."""

   class MarketDataError(TradingAgentsError):
       """Base error for data retrieval failures."""

   class VendorUnavailableError(MarketDataError):
       """Raised when a public endpoint is down or unreachable."""

   class VendorRateLimitError(MarketDataError):
       """Raised when an external public API throttles requests."""
   ```
3. **Timeouts**: Every external network call must specify an explicit timeout (recommended: 10.0 seconds). Unbounded network calls are prohibited.

---

## 4. Security & Sanitization Guardrails

1. **Path Traversal Prevention**: Any ticker or identifier interpolated into a filesystem path or cache directory must pass validation via `safe_ticker_component(value)`.
2. **Prompt Injection Defense**: News headlines, social commentary, and external web content must be sanitized and clearly demarcated as untrusted user content before interpolation into LLM prompts.
3. **Credential Protection**: Environment variables, API tokens, and private configuration files must never be committed to git or exposed in client logs.
