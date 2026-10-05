# Model integration and automated evaluation

[中文](USAGE.zh-CN.md) | [English](USAGE.en.md)

Run commands from the GitHub project root. Download data as described in the root README; the default dataset root is `datasets/MiniMax-H3-Reason`. Override it with `--dataset-root /path/to/dataset`.

## 1. Evaluate your generated videos

Use **Python 3.10+**. Run these commands from the GitHub project root. The evaluated video model and the judge are separate: your generation adapter uses your model's credentials; this evaluator uses an image-capable judge's API key.

### Install video decoding

```bash
python3 -m pip install -r requirements/eval.txt
```

A working system FFmpeg can also be used. The evaluator checks system binaries and falls back to the portable FFmpeg dependency. `ffprobe` is optional for scoring: FFmpeg metadata probing is used if it cannot run. Select custom binaries with `--ffmpeg PATH --ffprobe PATH`. The standalone SDK validator's `--probe` option still requires a working system `ffprobe`.

### Import existing videos

Name each video with its exact case ID, for example `ADR-001.mp4`, `VDR-001.mp4`, `AVIR-012.mp4`, or `MSR-001.mp4`. Supported extensions are `.mp4`, `.mov`, `.mkv` and `.webm`.

```bash
python3 sdk/create_submission.py \
  --videos-dir /path/to/generated_videos \
  --output-dir my_submission \
  --model-id my-video-model --model-version 1.0
```

This copies videos into `my_submission/videos/` and writes the canonical submission files. Cases without a supplied video remain recorded as `skipped` and stay in the score denominator. Unknown or duplicated filenames are rejected. Edit `my_submission/submission.json` to record actual preprocessing, generation parameters and seed.

To evaluate only supported scenarios, add `--scenarios ADR VDR`, for example. VDR videos default to `continuation_only`; if they include the original prefix, add `--vdr-layout with_prefix` to infer the boundary from each source video. A manually prepared submission can mix the two VDR layouts. AVIR prediction cases likewise accept `continuation_only` (default) or `with_prefix`; select the latter with `--avir-layout with_prefix`. AVIR annotation cases always use `annotated_full_video`. The importer reads each case's `task` to select the appropriate layout.

If your model already returns canonical records, you can instead copy `submission_template/`, fill its metadata, and save the videos and `outputs.jsonl` directly as described in Section 3.

### Check videos without API calls

```bash
python3 evaluate.py --submission my_submission/outputs.jsonl \
  --report-dir checks --dry-run
```

This verifies dataset/reference hashes, submission structure, selected source-media hashes, output layout constraints, and media extraction. Dry runs produce `dry_run` labels and **no task success rates**. An all-skipped submission is rejected because there are no generated videos to inspect. A successful dry run verifies local execution, not judge-service compatibility.

### Configure the judge and evaluate

All providers use the same `evaluate.py` entry point and the same task prompts, reference answers, scoring weights and pass thresholds. Select a profile for your **image-capable judge**, independently of the video generation model:

| Provider | Configuration file | Example judge model | Key environment variable |
|---|---|---|---|
| DeepSeek | `configs/judges/deepseek.json` | `deepseek-flash` | `DEEPSEEK_API_KEY` |
| Kimi | `configs/judges/kimi.json` | `kimi-k2.6` | `MOONSHOT_API_KEY` |
| OpenAI / GPT | `configs/judges/openai.json` | `gpt-4.1-2025-04-14` | `OPENAI_API_KEY` |
| Other Chat Completions services | `configs/judges/compatible.json` | Set your vision model | `JUDGE_API_KEY` |

These are editable configuration examples, not a guarantee of model availability or identical judge decisions. Check your account's model access. The provider profiles follow the official [DeepSeek vision documentation](https://api-docs.deepseek.com/guides/vision/), [Kimi vision documentation](https://platform.kimi.ai/docs/guide/use-kimi-vision-model), and [OpenAI GPT-4.1 documentation](https://developers.openai.com/api/docs/models/gpt-4.1).

For example, select the OpenAI profile; replace `openai.json` with another profile as needed:

```bash
cp configs/judges/openai.json judge_config.json
python3 evaluate.py --judge-config judge_config.json --check-judge \
  --prompt-key --report-dir judge_check
python3 evaluate.py --submission my_submission/outputs.jsonl \
  --judge-config judge_config.json --prompt-key \
  --report-dir evaluation_results
```

`--prompt-key` reads your key with hidden input and keeps it only in the current process. Alternatively, set the environment variable named by `api_key_env` and omit `--prompt-key`. Keys are configured by participants; the package contains no credentials. Never put credentials in configuration or submission files.

`--check-judge` makes one API request using two small synthetic images. It verifies image data URLs, multiple-image input and a correctly interpreted JSON response, then saves `judge_preflight.json`. It requires no submission or video decoder. Every scoring run also performs this preflight automatically before evaluating cases. This checks basic compatibility; it does not establish judge quality or full-size request capacity. Both preflight and scoring call your configured service and may incur its charges. `--dry-run` remains entirely local and makes no API calls.

The configuration fields are:

| Field | Meaning |
|---|---|
| `provider` | `deepseek`, `kimi`, `openai`, or `compatible`; selects request defaults |
| `base_url` | HTTPS API root including its version path; `/chat/completions` is appended unless already present |
| `model` | Image-capable model available to your account |
| `api_key_env` | Environment variable holding your key |
| `timeout`, `retries` | Request timeout in seconds and number of additional attempts |
| `max_tokens` | Output-token budget; serialized using `token_field` |
| `token_field` | `max_tokens` or `max_completion_tokens`; OpenAI profile uses the latter |
| `json_mode` | Enables `response_format: {"type": "json_object"}`; if unsupported, set to `false` while still requiring JSON output |
| `request_options` | Non-secret, model-specific parameters; cannot override managed request fields |

DeepSeek and Kimi examples disable thinking using their documented `thinking` setting ([DeepSeek](https://api-docs.deepseek.com/guides/thinking_mode/), [Kimi](https://platform.kimi.ai/docs/api/models-overview)). If you select a different model, adjust or remove model-specific parameters according to that provider's documentation; profiles are not interchangeable across all models. The OpenAI profile sends no `thinking` parameter and uses the documented [completion-token limit](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create). Defaults can also be selected with `--judge-provider openai`; `--judge-model`, `--judge-base-url` and `--api-key-env` override the selected configuration.

The client uses non-streaming Chat Completions with image data URLs. It reads final answer content, accepts text blocks or a complete JSON code fence, and rejects refusals, truncated output and invalid JSON. It never treats reasoning text as the final answer. Transient network, rate-limit and server errors are retried. Authentication, access, endpoint and request-configuration errors stop the run immediately; partial reports retain pending cases and do not publish a complete success rate. Other exhausted judge failures appear as evaluator errors, not model task failures.

Each evaluated video normally needs two judge requests (prediction and judgment), plus one preflight per run; retries can add requests. A complete 517-case run can therefore require 1,034 scoring requests plus preflight. Use a small `--case-ids` subset first. Reports record provider, configured model and non-secret request settings; per-case raw responses preserve the returned model identifier where the service supplies it. Compare benchmark runs using the same judge model, settings and sampling configuration.

The default run processes **every case in the declared submission scope**, with no first-20 limit. Use `--resume` to reuse completed judgments only when the input, output, references, metadata and evaluator configuration match. Interrupted or failed cases are retried. For an explicitly reported test subset, use `--case-ids ADR-001 VDR-001 AVIR-012 MSR-001`.

The same interface supports scenario entry points such as:

```bash
python3 scripts/eval_vdr.py --submission my_submission/outputs.jsonl \
  --judge-config judge_config.json --prompt-key --report-dir vdr_results
```

### Read the results

`evaluation_results/summary.json` contains a `scenarios` object with `ADR`, `VDR`, `AVIR`, and `MSR`. Each has `n`, `pass`, `fail`, `unknown`, generation-status counts, `evaluator_error`, `task_success_rate`, and `decision_coverage`. Unselected scenarios have `n=0` and null rates. The CLI also prints the four-scenario table. See Section 5 for the exact denominator and interpretation.

- `judge_preflight.json`: the judge compatibility check result.
- `results.json` and `results.csv`: one result per selected case.
- `<case-id>/evaluation.json` and `evidence/`: judge responses and sampled-frame evidence.
- `review_queue.json`: cases requiring review or retry.

Scoring exits with code 1 if any case has an evaluator error, and code 2 for setup/validation failures. A model failing a task does not itself make the command fail.

### Load inputs for your generation adapter

```python
from sdk.interface import load_cases

for request in load_cases('datasets/MiniMax-H3-Reason', scenarios={'ADR'}):
    print(request['id'], request['inputs']['image']['local_path'])
    # Supply this request to your model adapter; save a canonical output record.
```

All scenarios use the same `load_cases()` interface. Input loading and basic structural validation require no third-party Python packages.

## 2. Unified input protocol

`<dataset-root>/data/cases.jsonl` is UTF-8 JSONL with one case per line. All four scenarios use the same top-level fields and media keys.

| Field | Meaning |
|---|---|
| `schema_version` | Input protocol version, currently `0.1.0` |
| `id` | Unique case ID, such as `VDR-001` |
| `scenario` | `ADR`, `VDR`, `AVIR`, or `MSR` |
| `subcategory` | Scenario subcategory |
| `task` | Task type, listed below |
| `prompt` | Task text to be executed by the model |
| `inputs` | Always contains `image`, `audio`, and `video`; unused modalities are `null` |
| `output_spec` | Output kind, permitted layouts, source-audio preservation requirement, and view order |

Media objects contain `path` and `sha256`. Audio and video objects also contain `duration_s`. Media paths are relative to the dataset root, not the `data/` folder. Pass the dataset root to the SDK and `--dataset-root`. `duration_s=null` means unverified, not zero duration. The SDK adds a runtime `local_path` field; the public manifest contains no machine-specific absolute paths.

The following example abbreviates the prompt and hashes; it is not a replacement for an actual record:

```json
{
  "schema_version": "0.1.0",
  "id": "ADR-001",
  "scenario": "ADR",
  "subcategory": "Vocalizations",
  "task": "audio_conditioned_generation",
  "prompt": "Original task text...",
  "inputs": {
    "image": {"path": "media/ADR/image/ADR-001.png", "sha256": "..."},
    "audio": {"path": "media/ADR/audio/ADR-001.wav", "sha256": "...", "duration_s": null},
    "video": null
  },
  "output_spec": {
    "kind": "video",
    "allowed_layouts": ["full_video"],
    "preserve_source_audio": false,
    "view_order": null
  }
}
```

All scenarios use the singular media keys `image`, `audio`, and `video`.

| Scenario | `task` | Permitted output `layout` |
|---|---|---|
| ADR | `audio_conditioned_generation` | `full_video` |
| VDR | `video_continuation` | `continuation_only`, `with_prefix` |
| AVIR: inconsistency annotation (48) | `audio_video_annotation` | `annotated_full_video` |
| AVIR: future prediction (23) | `audio_video_continuation` | `continuation_only`, `with_prefix` |
| MSR | `synchronized_dual_view_generation` | `side_by_side` |

ADR must use the input audio as a condition. `preserve_source_audio=false` only means the current output protocol does not require retaining the source audio track; it does not permit ignoring the input audio.

For VDR, `continuation_only` returns only the generated continuation. `with_prefix` returns the source prefix and continuation together and requires an explicit continuation boundary. AVIR has two intended subtasks, selected by `task`. Annotation cases retain the source timeline and audio and add red circles only as requested. Prediction cases generate the immediate future from both source-video and audio cues; they may return only the continuation or the prefix plus continuation. Do not add red circles to prediction cases simply because their scenario is AVIR. Follow each case's prompt and retain the provided source audio as required. In MSR, each frame places the left wrist camera on the left and the right wrist camera on the right; both views represent the same scene at the same time.

## 3. Model adapters and submissions

### Model adapter

Each model implements the method defined by the `ModelAdapter` protocol:

```python
from pathlib import Path

class MyModelAdapter:
    def generate(self, request: dict, output_root: Path) -> dict:
        # Read source media from request['inputs'], run the model, and save a video.
        # Return one result record in the format defined below.
        raise NotImplementedError('Implement your model-specific inference here')
```

The shared call is `adapter.generate(request, output_root)`. The adapter handles media uploads or local reads, inference, remote job polling, and video saving. Participants configure their own model credentials.

### Submission metadata: submission.json

Fill out the following fields in the template:

| Field | Requirement |
|---|---|
| `schema_version` | `0.1.0` |
| `dataset_manifest_sha256` | Retain the template hash identifying the current `<dataset-root>/data/cases.jsonl` |
| `model_id`, `model_version` | Actual model identity and version |
| `adapter_version` | Version of the adapter implementation |
| `scope` | Declared scenario list, such as `["ADR", "VDR"]` |
| `preprocessing` | Input-conversion steps, tool/model versions, and parameters; `[]` if none |
| `generation_config` | Generation parameters, such as duration, resolution, and sampling settings |
| `seed` | Actual random seed, or `null` when unavailable or not applicable |

Replace all `REPLACE_*` placeholders with actual model and adapter information for reproducibility.

### Per-case results: outputs.jsonl

Provide exactly one record for every case in the declared scope. Each `id` explicitly maps to an output video path; filenames can be chosen freely. Example of a successful generation record:

```json
{"id":"VDR-001","status":"ok","output":{"kind":"video","path":"videos/VDR-001.mp4","layout":"continuation_only","evaluation_start_s":0,"evaluation_end_s":null}}
```

`output.path` is relative to the submission directory, must point to an existing file, and must not escape that directory. The only currently supported `kind` is `video`.

`evaluation_start_s` is the start of the evaluation interval. For VDR or AVIR prediction `with_prefix`, it must equal the source-video duration. Other layouts require 0. `evaluation_end_s=null` means the end of the video. The evaluator assesses the complete output ending for all scenarios and rejects an earlier end boundary; AVIR annotation requires the entire annotated video; AVIR prediction scores the complete generated continuation.

| `status` | Meaning |
|---|---|
| `ok` | A video was generated and saved; this is not an evaluation pass |
| `error` | Generation or saving failed |
| `unsupported` | The model lacks a capability required by the case |
| `skipped` | The case was not run; a reason is required |

Non-`ok` records require a nonempty `reason` and `output=null`:

```json
{"id":"ADR-001","status":"unsupported","reason":"The model does not support audio-conditioned generation","output":null}
```

The validator checks case IDs, duplicate and missing records, declared scope, protocol version, dataset hash identity, output files and paths, layouts, and evaluation-interval fields. `--probe` additionally checks VDR/AVIR prediction prefix boundaries, AVIR annotation duration, AVIR audio-stream presence, MSR wide frames, and video streams. These checks do not establish action correctness, audio fidelity, or dual-view synchronization.

## 4. Model capabilities and comparison

Models may declare only the scenarios they support. Within that scope, unsuccessful or unsupported cases must remain represented as `unsupported`, `error`, or `skipped`; removing them must not improve reported performance.

Audio transcription, video frame extraction, and conditioning conversion by another model must be documented in `preprocessing`. Different input conditions and composite pipelines should be reported separately. Substituting evaluator audio descriptions for source audio is not the original audio-input task.

The current main track requires video outputs. Text-only and multimodal understanding models need separately defined text-answer, event-prediction, or localization outputs and metrics. They cannot use generation-video scores directly.

Compare models on identical scenarios or a fixed shared set of IDs, and report the tested scope. Overall scores obtained with different scopes, preprocessing protocols, or evaluator versions should not be combined into a single ranking.

## 5. Evaluation and reporting

`evaluate.py` combines the original four scenario evaluators under one submission protocol. Stage 1 makes a blind prediction from source media, the prompt and ADR/AVIR audio descriptions, without seeing generated videos or reference outcomes. Stage 2 judges chronological output frames against references, that prediction and scenario constraints. Raw audio is represented to the judge by hash-bound English descriptions. Both AVIR subtasks additionally compare decoded source/output audio waveforms locally. AVIR prediction is routed to its future-prediction judge and is not scored for red-circle correctness or unchanged generated actions.

| Assessment weight | ADR | VDR | AVIR | MSR |
|---|---:|---:|---:|---:|
| Human reference | 55% | 55% | 50% | 45% |
| Blind model prediction | 20% | 20% | 15% | 15% |
| Source continuity / continuation continuity | 15% | 15% | — | 10% |
| Physical coherence | 10% | 10% | — | 10% |
| Annotation correctness | — | — | 15% | — |
| Source preservation | — | — | 10% | — |
| Audio preservation | — | — | 10% | — |
| Dual-view synchronization | — | — | — | 20% |

Each assessment has score 0, 1, 2, or null. Scores are normalized to 0–100 using the available weights. A pass requires at least 75 plus nonzero, decidable critical assessments. A zero critical assessment fails; an undecidable critical assessment or intermediate overall result can be `unknown`. The Python scenario modules contain the exact response schemas and decision rules. VDR/MSR use cumulative applicable reference constraints; ADR handles compatible constraints and mutually exclusive alternatives; AVIR annotation accepts substantive reference branches alongside preservation and annotation requirements. AVIR prediction uses reference branches, audiovisual reasoning, continuation continuity and audio preservation.

**Task success rate** is `pass / n`, where `n` is every selected case, including `unknown`, `generation_error`, `unsupported`, and `skipped`. It is a confirmed-success rate; `success_rate_bounds` gives the possible range when cases are unknown. A case is counted once and a weighted score is not a percentage accuracy. `decision_coverage` is `(pass + fail) / n`, and `decidable_success_rate` is `pass / (pass + fail)`. Always report coverage with the task success rate.

Evaluator/network errors, pending cases and dry runs make the task success rate null for the affected scenario; rerun with `--resume` to complete it. Other scenarios can still have complete results. Different scopes and explicit ID subsets are identified in the report and must not be compared as full benchmark runs.

AVIR intentionally includes 48 inconsistency-annotation cases and 23 future-prediction cases. All 71 are eligible for evaluation under their respective subtask protocols. `scenarios.AVIR` reports the combined case-level success rate; `avir_subtasks` also reports annotation and prediction separately. Prediction scoring assigns 50% to human references, 15% to blind prediction, 15% to audiovisual reasoning, 10% to continuation continuity and 10% to audio preservation. Its critical assessments are human reference, audiovisual reasoning, continuity and audio preservation. Preservation clauses constrain the source scene/audio and must not be interpreted as prohibiting the future actions required by a prediction prompt.

Default sampling uses 8 source-video frames and 20 output-video frames, with maximum image side 1280 pixels. Configure `--input-frames`, `--output-frames`, and `--max-side` consistently across compared models. Sparse frames may miss brief events and do not certify every instant of a video. Store the judge model, configuration and evaluator version with every published result.

## 6. Versioning and reproducibility

`<dataset-root>/data/dataset.json` records the interface version, case counts, and input-manifest SHA-256. `<dataset-root>/data/assets.jsonl` supplies media hashes and sizes for checking local file consistency.

When publishing results, record the manifest hash, model and adapter versions, preprocessing, generation parameters, and random seed. Report results with different scenario scopes, input conditions, or scoring configurations separately.

## 7. Citation

If you use this dataset or evaluation framework in your research, please cite our paper:

[Can MiniMax-H3 Reason About the Physical World? An Evaluation of Omni-Modal Generative Model](https://arxiv.org/abs/2609.18323).

```bibtex
@misc{zhao2026minimaxh3reason,
  title         = {Can MiniMax-H3 Reason About the Physical World? An Evaluation of Omni-Modal Generative Model},
  author        = {Haoyu Zhao and Zihao Zhao and Tianyu Deng and Ziqin Xu and Zihao Zhang and Xudong Wang and Jinxiang Guo and Chen Gao and Ziyi Ye and Yeying Jin and Jiaxi Gu and Zuxuan Wu and Shuicheng Yan},
  year          = {2026},
  eprint        = {2609.18323},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CV},
  url           = {https://arxiv.org/abs/2609.18323}
}
```
