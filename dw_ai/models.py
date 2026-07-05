from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SourceTable(BaseModel):
    name: str
    relation: str
    original_name: str
    source_type: str
    path: str | None = None


class SourceRegistry(BaseModel):
    name: str = "raw"
    tables: list[SourceTable] = Field(default_factory=list)


class ColumnProfile(BaseModel):
    name: str
    data_type: str
    null_count: int = 0
    null_rate: float = 0.0
    distinct_count: int = 0
    unique_ratio: float = 0.0
    sample_values: list[Any] = Field(default_factory=list)
    is_numeric: bool = False
    is_temporal: bool = False
    is_identifier: bool = False
    is_candidate_key: bool = False


class TableProfile(BaseModel):
    name: str
    row_count: int
    columns: list[ColumnProfile] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class RelationshipCandidate(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    confidence: float
    reason: str


class DatasetProfile(BaseModel):
    tables: list[TableProfile] = Field(default_factory=list)
    relationships: list[RelationshipCandidate] = Field(default_factory=list)

    def table(self, name: str) -> TableProfile:
        for table in self.tables:
            if table.name == name:
                return table
        raise KeyError(name)


class DimensionRef(BaseModel):
    dimension: str
    source_column: str
    dimension_key: str


class DimensionModel(BaseModel):
    name: str
    source_table: str | None = None
    natural_key: str | None = None
    surrogate_key: str
    columns: list[str] = Field(default_factory=list)
    description: str = ""


class FactModel(BaseModel):
    name: str
    source_table: str
    grain: str
    measures: list[str] = Field(default_factory=list)
    degenerate_dimensions: list[str] = Field(default_factory=list)
    dimensions: list[DimensionRef] = Field(default_factory=list)
    date_columns: list[str] = Field(default_factory=list)
    description: str = ""


class ModelPlan(BaseModel):
    facts: list[FactModel] = Field(default_factory=list)
    dimensions: list[DimensionModel] = Field(default_factory=list)
    date_dimension: bool = False
    assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""


class ArtifactBundle(BaseModel):
    files: dict[str, str]
    diagram: str

