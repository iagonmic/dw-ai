from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from dw_ai.dbt_generator import generate_dbt_project
from dw_ai.models import ArtifactBundle, DatasetProfile, ModelPlan, SourceRegistry


def build_artifact_zip(
    plan: ModelPlan,
    profile: DatasetProfile,
    registry: SourceRegistry,
) -> tuple[bytes, ArtifactBundle]:
    """Generate dbt files and package them into an in-memory ZIP for download."""
    artifact = generate_dbt_project(plan, profile, registry)
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for path, content in sorted(artifact.files.items()):
            archive.writestr(path, content)
    return buffer.getvalue(), artifact
