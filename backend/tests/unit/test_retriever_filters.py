"""T1.10 hard-filter SQL and retrieval-universe tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

from sqlalchemy.dialects import postgresql

from domain.models.retrieval import HardFilters
from infra.tables import ingredient_aliases, ingredients, recipe_ingredients
from rag.bm25_index import BM25Index
from rag.corpus import CardCorpus
from rag.retriever import HybridRetriever


async def test_bm25_allowed_universe_is_independent_of_vector_top50() -> None:
    class Embedder:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] for _ in texts]

    class Corpus:
        def __init__(self) -> None:
            self.allowed_ids: set[str] | None = None

        def search(self, query: str, top_n: int, allowed_ids: set[str] | None = None) -> list[tuple[str, float]]:
            self.allowed_ids = allowed_ids
            return [("recipe-59", 1.0)] if allowed_ids and "recipe-59" in allowed_ids else []

        def name_of(self, recipe_id: str) -> str:
            return recipe_id

    retriever = HybridRetriever(Embedder(), Corpus(), engine=AsyncMock(), vector_top_n=1)
    retriever._allowed_recipe_ids = AsyncMock(return_value={"recipe-59"})
    retriever._vector_search = AsyncMock(return_value=[])

    candidates = await retriever.search("egg", filters=HardFilters(tools_available=["pan"]))

    assert [candidate.recipe_id for candidate in candidates] == ["recipe-59"]
    assert retriever._corpus.allowed_ids == {"recipe-59"}


def test_bm25_search_can_restrict_to_sql_allowed_recipe_universe() -> None:
    index = BM25Index(["allowed", "excluded", "other"], [["egg"], ["egg", "shrimp"], ["salt"]])

    hits = index.search(["egg"], top_n=1, allowed_ids={"excluded"})

    assert hits == [("excluded", hits[0][1])]


def test_hard_filter_sql_uses_strict_known_time_semantics() -> None:
    retriever = HybridRetriever.__new__(HybridRetriever)
    statement = retriever._allowed_recipe_statement(HardFilters(max_time_minutes=30))

    sql = str(statement.compile(dialect=postgresql.dialect())).lower()

    assert "time_minutes is not null" in sql
    assert "time_minutes <=" in sql
    assert "time_minutes is null" not in sql


def test_hard_filter_sql_compiles_time_tools_and_case_insensitive_ingredients() -> None:
    retriever = HybridRetriever.__new__(HybridRetriever)
    statement = retriever._allowed_recipe_statement(
        HardFilters(max_time_minutes=30, tools_available=["炒锅"], excluded_ingredients=["虾"])
    )

    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled).lower()

    assert "time_minutes" in sql and "time_minutes_1" in sql
    assert "tools" in sql and "<@" in sql
    assert "lower(ingredients.name)" in sql
    assert "lower(recipe_ingredients.name_raw)" in sql
    assert "lower(ingredient_aliases.alias)" in sql
    assert "not (exists" in sql
    assert "虾" in compiled.params.values()


def test_excluded_ingredient_normalization_matches_sql_lower_semantics() -> None:
    retriever = HybridRetriever.__new__(HybridRetriever)
    statement = retriever._allowed_recipe_statement(HardFilters(excluded_ingredients=["ABC"]))

    compiled = statement.compile(dialect=postgresql.dialect())

    assert "abc" in compiled.params.values()


def test_empty_hard_filters_do_not_add_sql_predicates() -> None:
    retriever = HybridRetriever.__new__(HybridRetriever)

    assert retriever._allowed_recipe_statement(HardFilters()) is None
    assert retriever._allowed_recipe_statement(None) is None


def test_excluded_ingredient_sql_matches_unlinked_raw_name() -> None:
    retriever = HybridRetriever.__new__(HybridRetriever)
    statement = retriever._allowed_recipe_statement(HardFilters(excluded_ingredients=["虾"]))

    sql = str(statement.compile(dialect=postgresql.dialect())).lower()

    assert str(recipe_ingredients.c.name_raw).lower() in sql
    assert str(ingredients.c.name).lower() in sql
    assert str(ingredient_aliases.c.alias).lower() in sql


def test_corpus_allowed_ids_are_forwarded() -> None:
    corpus = CardCorpus([])
    assert corpus.search("鸡蛋", top_n=10, allowed_ids=set()) == []
