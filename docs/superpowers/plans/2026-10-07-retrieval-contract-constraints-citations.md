# Retrieval Contract, Constraints, and Citations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete T1.13, T1.10, and T1.11 in order so the retrieval contract, SQL-level hard-constraint filtering, and citation validation form a tested recommendation boundary.

**Architecture:** Keep all cross-layer Protocols in `backend/domain/ports.py`. Extend the existing `HybridRetriever` so metadata constraints are applied inside the vector SQL query before recall results are returned, while BM25 candidates are constrained to the same allowed recipe IDs. Add citation/output validation as pure domain logic that accepts only retrieved recipe IDs and authoritative recipe names.

**Tech Stack:** Python 3.11+, Pydantic v2, typing.Protocol, SQLAlchemy async Core, PostgreSQL/pgvector/JSONB, pytest, pytest-asyncio, Ruff.

## Global Constraints

- Follow `api → services → domain / agents / rag → infra`; `domain` has no IO dependencies.
- Define all Protocol interfaces in `backend/domain/ports.py`.
- Do not invent upstream recipe values; missing source fields remain `None`.
- Hard constraints must be pushed into retrieval SQL, never applied after retrieval in Python.
- Every generated recommendation must carry a real `recipe_id` and must be validated against retrieved authoritative candidates.
- Use Pydantic v2 APIs and complete type annotations; do not add dependencies outside `backend/pyproject.toml`.
- Run backend Ruff and pytest with workspace-local temporary directories before completion.

---

### Task 1: T1.13 Minimal Cross-Layer Protocols

**Files:**
- Modify: `backend/domain/ports.py`
- Modify: `backend/domain/models/recipe.py` only if a repository return type needs an existing domain model adjustment
- Test: `backend/tests/unit/test_ports.py`

**Interfaces:**
- Consumes: existing `Recipe`, `HardFilters`, and `RecipeCandidate` domain models.
- Produces: `RecipeRepository.get_by_id(recipe_id: str) -> Recipe | None`; `RecipeRepository.search(filters: HardFilters | None = None, limit: int = 50) -> list[Recipe]`; `LLMClient.complete(messages: Sequence[dict[str, str]], *, temperature: float = 0.1, response_format: str | None = None) -> str`; existing retrieval/client Protocols remain compatible.

- [ ] **Step 1: Write the failing Protocol conformance tests**

```python
from collections.abc import Sequence

from domain.models.recipe import Recipe
from domain.models.retrieval import HardFilters
from domain.ports import LLMClient, RecipeRepository


class FakeRepository:
    async def get_by_id(self, recipe_id: str) -> Recipe | None:
        return None

    async def search(self, filters: HardFilters | None = None, limit: int = 50) -> list[Recipe]:
        return []


class FakeLLM:
    model = "fake"

    async def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.1,
        response_format: str | None = None,
    ) -> str:
        return "{}"


def test_fake_repository_satisfies_repository_protocol() -> None:
    assert isinstance(FakeRepository(), RecipeRepository)


def test_fake_llm_satisfies_llm_protocol() -> None:
    assert isinstance(FakeLLM(), LLMClient)
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run from `backend/`: `.venv\Scripts\python.exe -m pytest tests/unit/test_ports.py -q -p no:cacheprovider`
Expected: FAIL because `RecipeRepository` and `LLMClient` are not defined.

- [ ] **Step 3: Add the minimal runtime-checkable Protocol definitions**

Add `RecipeRepository` with the two async methods and `LLMClient` with the `model` attribute and `complete` method to `backend/domain/ports.py`. Import `Recipe` and keep all imports limited to standard library and domain models.

- [ ] **Step 4: Run focused tests and lint**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_ports.py -q -p no:cacheprovider` and `.venv\Scripts\python.exe -m ruff check domain/ports.py tests/unit/test_ports.py`
Expected: all tests pass and Ruff exits 0.

- [ ] **Step 5: Commit the contract change**

```text
git add backend/domain/ports.py backend/tests/unit/test_ports.py
git commit -m "feat: define repository and llm protocols"
```

---

### Task 2: T1.10 SQL-Level Hard-Constraint Filtering

**Files:**
- Modify: `backend/domain/models/retrieval.py`
- Modify: `backend/rag/retriever.py`
- Modify: `backend/rag/corpus.py` if constrained BM25 candidate selection needs a pure allow-list API
- Test: `backend/tests/unit/test_retriever_filters.py`
- Test: `backend/tests/integration/test_retriever.py`

**Interfaces:**
- Consumes: `HardFilters(max_time_minutes, tools_available, excluded_ingredients)`, `HybridRetriever.search(query, filters, top_k)`.
- Produces: filtered vector SQL using `recipes.time_minutes`, JSONB tools containment, and `NOT EXISTS` ingredient/alias exclusion; BM25 is restricted to the IDs returned by the constrained SQL; non-empty filters no longer raise `NotImplementedError`; an empty constrained result returns `[]`.

- [ ] **Step 1: Add failing unit tests for filter expression construction**

```python
from domain.models.retrieval import HardFilters
from rag.retriever import build_recipe_filter_clauses


def test_time_filter_is_included() -> None:
    clauses = build_recipe_filter_clauses(HardFilters(max_time_minutes=30))
    assert len(clauses) == 1


def test_empty_filters_produce_no_clauses() -> None:
    assert build_recipe_filter_clauses(HardFilters()) == []
```

Also add integration cases that seed recipes with different `time_minutes`, `tools`, and excluded ingredient aliases, then assert disallowed IDs never appear in results and an impossible filter returns `[]`.

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_retriever_filters.py -q -p no:cacheprovider`
Expected: FAIL because `build_recipe_filter_clauses` does not exist and the current retriever raises `NotImplementedError` for non-empty filters.

- [ ] **Step 3: Implement SQL filter clauses**

Implement `build_recipe_filter_clauses(filters)` in `backend/rag/retriever.py`:

- `max_time_minutes` becomes `recipes.c.time_minutes.is_not(None) & recipes.c.time_minutes <= value`.
- `tools_available` becomes PostgreSQL JSONB containment requiring recipe tools to be contained by the available tools, using `recipes.c.tools.contained_by(filters.tools_available)` or the SQLAlchemy equivalent supported by the existing JSONB column.
- `excluded_ingredients` becomes a correlated `NOT EXISTS` over `recipe_ingredients` joined to `ingredients` and `ingredient_aliases`, matching canonical names, raw names, or aliases case-insensitively.

Apply clauses in `_vector_search` before `ORDER BY distance` and `LIMIT`. Return recipe IDs from this constrained query.

- [ ] **Step 4: Constrain BM25 candidates using the SQL allow-list**

After vector SQL returns, derive the allowed ID set from the constrained vector query. Add a corpus method that accepts an optional allowed-ID set and skips documents outside it without performing a post-retrieval hard-filter pass. Use the SQL-constrained IDs as the candidate universe, and preserve the existing unfiltered path when filters are empty.

- [ ] **Step 5: Run unit and integration tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_retriever_filters.py tests/integration/test_retriever.py -q -p no:cacheprovider`
Expected: all focused tests pass, including existing unfiltered RRF/rerank behavior.

- [ ] **Step 6: Commit the filtering change**

```text
git add backend/domain/models/retrieval.py backend/rag/retriever.py backend/rag/corpus.py backend/tests/unit/test_retriever_filters.py backend/tests/integration/test_retriever.py
git commit -m "feat: push hard constraints into recipe retrieval"
```

---

### Task 3: T1.11 Citation and Anti-Hallucination Validation

**Files:**
- Create: `backend/domain/models/recommendation.py`
- Create: `backend/domain/citations.py`
- Modify: `backend/domain/models/retrieval.py` only if shared candidate fields need a documented constraint
- Test: `backend/tests/unit/test_citations.py`

**Interfaces:**
- Consumes: `RecipeCandidate` objects from `HybridRetriever` and authoritative recipe names.
- Produces: `Recommendation` with `recipe_id: str`, `name: str`, `reason: str`, `missing_ingredients: list[str]`, `substitutions: list[str]`, `time_minutes: int | None`; `validate_recommendations(recommendations, candidates, *, expected_count: int = 3) -> list[Recommendation]`; invalid or out-of-corpus IDs raise a typed domain validation error.

- [ ] **Step 1: Write failing citation tests**

```python
import pytest
from domain.citations import CitationValidationError, validate_recommendations
from domain.models.recommendation import Recommendation
from domain.models.retrieval import RecipeCandidate


def candidate(recipe_id: str = "r1", name: str = "西红柿炒鸡蛋") -> RecipeCandidate:
    return RecipeCandidate(recipe_id=recipe_id, name=name, score=1.0, rank=1, sources=["vector"])


def test_valid_recommendation_is_accepted() -> None:
    recommendation = Recommendation(recipe_id="r1", name="西红柿炒鸡蛋", reason="有番茄", time_minutes=None)
    assert validate_recommendations([recommendation], [candidate()], expected_count=1) == [recommendation]


def test_unknown_recipe_id_is_rejected() -> None:
    recommendation = Recommendation(recipe_id="outside", name="外部菜", reason="", time_minutes=None)
    with pytest.raises(CitationValidationError, match="recipe_id"):
        validate_recommendations([recommendation], [candidate()], expected_count=1)


def test_name_mismatch_is_rejected() -> None:
    recommendation = Recommendation(recipe_id="r1", name="红烧肉", reason="", time_minutes=None)
    with pytest.raises(CitationValidationError, match="name"):
        validate_recommendations([recommendation], [candidate()], expected_count=1)
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_citations.py -q -p no:cacheprovider`
Expected: FAIL because the recommendation model and validator do not exist.

- [ ] **Step 3: Implement the recommendation model and validator**

Use Pydantic v2 for `Recommendation`. Validate non-empty `recipe_id`, require exact ID membership in candidates, require exact authoritative name match, and enforce `expected_count` exactly. Keep the validator pure and independent of database/LLM code. Raise `CitationValidationError` with actionable field-level messages.

- [ ] **Step 4: Add candidate identity and ordering tests**

Test duplicate recommendation IDs, wrong count, blank IDs, and a valid three-item list. Confirm the output preserves candidate-independent recommendation order while every item is grounded in the candidate set.

- [ ] **Step 5: Run full backend verification**

From repository root, set `$env:TEMP='D:\Allcode\MealCompass\.tmp'`, then run:

```text
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m ruff format --check backend
backend\.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
```

Expected: Ruff checks pass and all tests pass. If an integration test requires PostgreSQL unavailable in the environment, report that exact limitation rather than weakening the tests.

- [ ] **Step 6: Synchronize documentation and TODO**

Update `TODO.md` to mark T1.13, T1.10, and T1.11 only after their tests pass. Update `docs/ARCHITECTURE.md` with the final Protocol signatures, SQL filter flow, and citation validation boundary. Append a dated entry to `docs/mistakes.md` describing the verification outcome.

- [ ] **Step 7: Commit the completed chain**

```text
git add backend/domain/models/recommendation.py backend/domain/citations.py backend/tests/unit/test_citations.py TODO.md docs/ARCHITECTURE.md docs/mistakes.md
git commit -m "feat: close retrieval constraints and citation validation"
```
