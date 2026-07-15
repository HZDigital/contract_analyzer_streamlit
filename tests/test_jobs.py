from src.api.jobs import JobDispatcher, JobService
from src.api.schemas import JobRecord
from src.api.settings import Settings


class _FailingCleanupStorage:
    def delete_inputs(self, _job: JobRecord) -> None:
        raise RuntimeError("temporary Blob failure")


def test_terminal_input_cleanup_is_best_effort() -> None:
    settings = Settings()
    dispatcher = JobDispatcher(JobService(_FailingCleanupStorage(), settings))  # type: ignore[arg-type]

    dispatcher._delete_inputs_best_effort(JobRecord(owner_oid="object-id", workflow="invoice"))
