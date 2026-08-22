from pathlib import Path
from tempfile import TemporaryDirectory

from backend.bi.materializer import BiMaterializer, BiMaterializerServices
from backend.bi.models import JobId
from backend.bi.snapshot_store import FileBiSnapshotStore
from backend.bi.tests.test_materializer import (
    FakeExtractor,
    FakeProfiler,
    FixedClock,
    profile,
    request,
)


def test_published_snapshot_carries_validated_source_lineage() -> None:
    # Given
    materialization_request = request()
    with TemporaryDirectory() as directory:
        materializer = BiMaterializer(
            BiMaterializerServices(
                FakeProfiler(profile()),
                FakeExtractor(),
                FileBiSnapshotStore(Path(directory)),
                FixedClock(),
            )
        )

        # When
        outcome = materializer.materialize(
            materialization_request,
            JobId("job-source-lineage"),
        )

        # Then
        assert outcome.snapshot is not None
        assert outcome.snapshot.source == materialization_request.source
