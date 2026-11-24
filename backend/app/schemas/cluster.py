from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MisconceptionClusterItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cluster_id: str
    linked_concept: str
    hypothesis: str
    student_count: int
    student_ids: List[int] = Field(default_factory=list)
    finding_ids: List[int] = Field(default_factory=list)
    evidence_excerpts: List[str] = Field(default_factory=list)
    severity_distribution: Dict[str, int] = Field(default_factory=lambda: {"low": 0, "medium": 0, "high": 0})
    recommended_intervention: str


class MisconceptionClusterResponse(BaseModel):
    assessment_id: int
    assessment_title: Optional[str] = None
    clusters: List[MisconceptionClusterItem] = Field(default_factory=list)
    isolated: List[MisconceptionClusterItem] = Field(default_factory=list)
    total_findings_evaluated: int = 0
    total_students_evaluated: int = 0

