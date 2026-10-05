"""Implement this interface for your video-generation service; credentials stay local."""
from pathlib import Path
from sdk.interface import ModelAdapter, load_cases


class MyModelAdapter:
    def generate(self, request: dict, output_root: Path) -> dict:
        # request has id, scenario, task, prompt, inputs and output_spec.
        # Each non-null media input has local_path. Use the source media, not references.
        # Implement provider-specific upload, inference/polling and video saving here.
        # Return one canonical record: {id, status, output} or {id, status, reason, output: None}.
        raise NotImplementedError('Implement your generation provider here.')


def generate_cases(adapter: ModelAdapter, dataset_root: Path, output_root: Path, scenarios=None):
    """Call a supplied adapter; invoke only after configuring your own generation service."""
    output_root.mkdir(parents=True, exist_ok=True)
    for request in load_cases(dataset_root, scenarios=scenarios):
        yield adapter.generate(request, output_root)
