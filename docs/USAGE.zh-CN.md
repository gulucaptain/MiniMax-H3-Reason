# 模型接入与自动评估

[中文](USAGE.zh-CN.md) | [English](USAGE.en.md)

在 GitHub 项目根目录运行命令。先按根目录 README 下载数据；默认数据目录为 `datasets/MiniMax-H3-Reason`，也可用 `--dataset-root /path/to/dataset` 指定本地数据。

## 1. 评估生成的视频

使用 **Python 3.10+**，在 GitHub 项目根目录执行命令。被测视频生成模型与裁判模型分别配置：生成适配器使用被测模型的凭据，评估程序使用具备图像理解能力的裁判模型 Key。

### 安装视频解码依赖

```bash
python3 -m pip install -r requirements/eval.txt
```

也可使用可正常运行的系统 FFmpeg。评估程序检查系统二进制，不可用时回退到便携式 FFmpeg 依赖。评分不强制要求 `ffprobe`：无法运行时用 FFmpeg 读取元信息。可用 `--ffmpeg PATH --ffprobe PATH` 指定路径。SDK 独立校验器的 `--probe` 仍要求可运行的系统 `ffprobe`。

### 导入已有视频

使用完整 case ID 命名视频，例如 `ADR-001.mp4`、`VDR-001.mp4`、`AVIR-012.mp4`、`MSR-001.mp4`。支持 `.mp4`、`.mov`、`.mkv`、`.webm`。

```bash
python3 sdk/create_submission.py \
  --videos-dir /path/to/generated_videos \
  --output-dir my_submission \
  --model-id my-video-model --model-version 1.0
```

导入工具会复制视频到 `my_submission/videos/`，并生成标准提交文件。缺少视频的任务记为 `skipped`，仍保留在评分分母中。未知 ID 或同一 ID 的重复文件会被拒绝。请在 `my_submission/submission.json` 中填写实际预处理、生成参数和随机种子。

如只评测支持的场景，可添加 `--scenarios ADR VDR`。VDR 默认视频布局为 `continuation_only`；若输出包含原始前缀，添加 `--vdr-layout with_prefix`，工具会按源视频时长确定续写起点。手动提交可混用两种布局。AVIR 预测任务同样默认 `continuation_only`，包含前缀时使用 `--avir-layout with_prefix`。AVIR 标注任务固定使用 `annotated_full_video`。导入工具依据每条任务的 `task` 选择布局。

若模型已经输出标准记录，也可复制 `submission_template/`，填写元信息，按第 3 节直接保存视频和 `outputs.jsonl`。

### 本地检查，不调用 API

```bash
python3 evaluate.py --submission my_submission/outputs.jsonl \
  --report-dir checks --dry-run
```

检查数据和参考文件哈希、提交结构、所选源媒体哈希、输出布局约束及媒体提取。试运行返回 `dry_run` 标签，**不产生任务成功率**。全部为 `skipped` 的提交会被拒绝，因为没有生成视频可检查。试运行成功表示本地流程可执行，尚未验证裁判服务兼容性。

### 配置裁判并评估

不同服务均使用同一个 `evaluate.py` 入口，以及相同的任务 prompt、参考答案、评分权重和通过阈值。请独立于被测视频模型选择**具备图像理解能力的裁判模型**：

| 服务 | 配置文件 | 示例裁判模型 | Key 环境变量 |
|---|---|---|---|
| DeepSeek | `configs/judges/deepseek.json` | `deepseek-flash` | `DEEPSEEK_API_KEY` |
| Kimi | `configs/judges/kimi.json` | `kimi-k2.6` | `MOONSHOT_API_KEY` |
| OpenAI / GPT | `configs/judges/openai.json` | `gpt-4.1-2025-04-14` | `OPENAI_API_KEY` |
| 其他兼容 Chat Completions 的服务 | `configs/judges/compatible.json` | 填写视觉模型名称 | `JUDGE_API_KEY` |

这些配置示例可修改；模型是否可用取决于账号权限，不同裁判也可能给出不同判断。配置依据 [DeepSeek 视觉文档](https://api-docs.deepseek.com/guides/vision/)、[Kimi 视觉文档](https://platform.kimi.ai/docs/guide/use-kimi-vision-model)和 [OpenAI GPT-4.1 文档](https://developers.openai.com/api/docs/models/gpt-4.1)。

以下以 OpenAI 为例；使用其他服务时替换 `openai.json`：

```bash
cp configs/judges/openai.json judge_config.json
python3 evaluate.py --judge-config judge_config.json --check-judge \
  --prompt-key --report-dir judge_check
python3 evaluate.py --submission my_submission/outputs.jsonl \
  --judge-config judge_config.json --prompt-key \
  --report-dir evaluation_results
```

`--prompt-key` 通过隐藏输入读取 Key，仅在当前进程中使用。也可设置 `api_key_env` 指定的环境变量，并省略 `--prompt-key`。Key 由使用者自行配置，发布包不包含凭据。请勿将凭据写入配置或提交文件。

`--check-judge` 用两张小型合成图片发起一次 API 请求，检查图片 data URL、多图片输入和正确的 JSON 回答，结果保存为 `judge_preflight.json`。此检查不需要提交视频或安装解码器。每次正式评分也会在评测任务前自动预检。预检验证基础兼容性，不代表裁判质量或大请求容量已获验证。预检与评分均会调用所配置的服务，可能产生该服务的费用；`--dry-run` 始终只在本地执行，不调用 API。

| 配置字段 | 含义 |
|---|---|
| `provider` | `deepseek`、`kimi`、`openai` 或 `compatible`，选择默认请求参数 |
| `base_url` | 带版本路径的 HTTPS API 根地址；未包含 `/chat/completions` 时自动追加 |
| `model` | 账号有权限使用的视觉模型 |
| `api_key_env` | 保存 Key 的环境变量名称 |
| `timeout`、`retries` | 请求超时秒数及额外重试次数 |
| `max_tokens` | 输出 token 预算，按 `token_field` 序列化 |
| `token_field` | `max_tokens` 或 `max_completion_tokens`；OpenAI 示例使用后者 |
| `json_mode` | 启用 `response_format: {"type": "json_object"}`；服务不支持时设为 `false`，但回答仍须是 JSON |
| `request_options` | 不含凭据的模型专用参数，不得覆盖程序管理的请求字段 |

DeepSeek 和 Kimi 示例依据文档通过 `thinking` 参数关闭思考模式（[DeepSeek](https://api-docs.deepseek.com/guides/thinking_mode/)、[Kimi](https://platform.kimi.ai/docs/api/models-overview)）。更换模型时需按服务文档调整或移除专用参数；配置不能直接通用于所有模型。OpenAI 示例不发送 `thinking`，并采用其文档规定的[输出 token 上限字段](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。也可用 `--judge-provider openai` 选择默认配置，再用 `--judge-model`、`--judge-base-url`、`--api-key-env` 覆盖相应设置。

客户端使用非流式 Chat Completions 和图片 data URL。它解析最终回答，接受文本块或完整 JSON 代码围栏，拒绝拒答、截断输出和无效 JSON，不把思考文本当成最终答案。临时网络错误、限流和服务器错误会重试；认证、访问权限、端点或请求配置错误会立即停止。部分报告保留待处理任务，不发布完整成功率。其他重试耗尽的裁判错误记为评估器错误，不计为被测模型任务失败。

每条正常评估的视频通常需要两次裁判请求（预测与判断），每次运行另有一次预检，重试会增加请求量。完整评估 517 条最多通常需要 1,034 次评分请求，另加预检。建议先用少量 `--case-ids` 测试。报告记录服务、配置的模型及非敏感请求设置；服务提供返回模型 ID 时，原始响应也会保留该信息。比较结果时应使用一致的裁判模型、设置和采样配置。

默认处理**声明评测范围内的全部任务**，没有只处理前 20 条的限制。使用 `--resume` 时，仅在输入、输出、参考、元信息和评估配置一致时复用已完成判断；中断或失败的任务会重试。明确评测子集可使用 `--case-ids ADR-001 VDR-001 AVIR-012 MSR-001`，报告会标明子集。

单场景入口使用相同接口，例如：

```bash
python3 scripts/eval_vdr.py --submission my_submission/outputs.jsonl \
  --judge-config judge_config.json --prompt-key --report-dir vdr_results
```

### 查看结果

`evaluation_results/summary.json` 的 `scenarios` 包含 `ADR`、`VDR`、`AVIR`、`MSR`。每个场景有 `n`、`pass`、`fail`、`unknown`、生成状态计数、`evaluator_error`、`task_success_rate` 和 `decision_coverage`。未选择的场景 `n=0`，比例为 null。命令行也打印四场景结果表。分母和指标解释见第 5 节。

- `judge_preflight.json`：裁判兼容性预检结果。
- `results.json`、`results.csv`：所选任务逐条评估结果。
- `<case-id>/evaluation.json`、`evidence/`：裁判响应和采样帧证据。
- `review_queue.json`：需复核或重试的任务。

有任务发生评估器错误时退出码为 1；设置或校验失败时为 2。被测模型任务失败本身不会使命令以错误码退出。

### 为生成适配器加载输入

```python
from sdk.interface import load_cases

for request in load_cases('datasets/MiniMax-H3-Reason', scenarios={'ADR'}):
    print(request['id'], request['inputs']['image']['local_path'])
    # Supply this request to your model adapter; save a canonical output record.
```

四个场景统一使用 `load_cases()`。输入加载和基础结构校验无需第三方 Python 包。

## 2. 统一输入协议

`<dataset-root>/data/cases.jsonl` 为 UTF-8 JSONL，每行一条任务。四个场景使用相同的顶层字段和媒体键。

| 字段 | 含义 |
|---|---|
| `schema_version` | 输入协议版本，当前为 `0.1.0` |
| `id` | 唯一任务 ID，例如 `VDR-001` |
| `scenario` | `ADR`、`VDR`、`AVIR` 或 `MSR` |
| `subcategory` | 场景子类别 |
| `task` | 下表列出的任务类型 |
| `prompt` | 要求被测模型执行的任务文本 |
| `inputs` | 始终包含 `image`、`audio`、`video`，不用的模态为 `null` |
| `output_spec` | 输出类型、允许的布局、源音频保留要求和视角顺序 |

媒体对象包含 `path` 和 `sha256`；音频和视频还包含 `duration_s`。媒体路径相对于数据集根目录，而非 `data/` 目录。向 SDK 和 `--dataset-root` 传入数据集根目录。`duration_s=null` 表示时长未核验，不表示 0。SDK 在运行时增加 `local_path`；公开清单不含机器专用的绝对路径。

下例缩略了 prompt 和哈希，仅说明结构，不能替代实际任务记录：

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

四个场景均使用单数媒体键 `image`、`audio`、`video`。

| 场景 | `task` | 允许的输出 `layout` |
|---|---|---|
| ADR | `audio_conditioned_generation` | `full_video` |
| VDR | `video_continuation` | `continuation_only`、`with_prefix` |
| AVIR：矛盾标注（48 条） | `audio_video_annotation` | `annotated_full_video` |
| AVIR：未来预测（23 条） | `audio_video_continuation` | `continuation_only`、`with_prefix` |
| MSR | `synchronized_dual_view_generation` | `side_by_side` |

ADR 必须使用输入音频作为生成条件。`preserve_source_audio=false` 仅表示当前输出协议不要求保留源音轨，不允许忽略输入音频。

VDR 的 `continuation_only` 仅输出续写部分；`with_prefix` 输出源前缀和续写，须显式给出续写起点。AVIR 根据 `task` 区分两类设计：标注任务保留源时间轴和音频，只按要求添加红圈；预测任务结合源视频和音频线索生成紧接着的未来，可只输出续写，也可包含前缀。不能仅因场景为 AVIR 就给预测任务添加红圈。请遵循每条 prompt，并按要求保留提供的源音频。MSR 的每帧左侧为左腕部相机、右侧为右腕部相机，两侧表示同一时刻的同一场景。

## 3. 模型适配器与提交

### 模型适配器

每个模型实现 `ModelAdapter` 协议定义的方法：

```python
from pathlib import Path

class MyModelAdapter:
    def generate(self, request: dict, output_root: Path) -> dict:
        # Read source media from request['inputs'], run the model, and save a video.
        # Return one result record in the format defined below.
        raise NotImplementedError('Implement your model-specific inference here')
```

统一调用为 `adapter.generate(request, output_root)`。适配器负责媒体上传或本地读取、模型推理、远程任务轮询及视频保存。参与者自行配置被测模型凭据。

### 提交元信息：submission.json

填写模板中的以下字段：

| 字段 | 要求 |
|---|---|
| `schema_version` | `0.1.0` |
| `dataset_manifest_sha256` | 保留模板中标识当前 `<dataset-root>/data/cases.jsonl` 的哈希 |
| `model_id`、`model_version` | 实际模型名称及版本 |
| `adapter_version` | 适配器实现版本 |
| `scope` | 声明的场景列表，例如 `["ADR", "VDR"]` |
| `preprocessing` | 输入转换步骤、工具或模型版本、参数；无预处理时为 `[]` |
| `generation_config` | 时长、分辨率、采样设置等生成参数 |
| `seed` | 实际随机种子；不可用或不适用时为 `null` |

将全部 `REPLACE_*` 占位符替换为真实模型和适配器信息，以便复现。

### 逐条输出：outputs.jsonl

声明范围内每条任务必须恰有一条记录。每个 `id` 明确对应输出视频路径，手动提交时可自定文件名。成功生成的记录示例：

```json
{"id":"VDR-001","status":"ok","output":{"kind":"video","path":"videos/VDR-001.mp4","layout":"continuation_only","evaluation_start_s":0,"evaluation_end_s":null}}
```

`output.path` 相对于提交目录，须指向已有文件，且不能越出该目录。当前仅支持 `kind=video`。

`evaluation_start_s` 为评估起点。VDR 或 AVIR 预测任务使用 `with_prefix` 时，起点须等于源视频时长；其他布局须为 0。`evaluation_end_s=null` 表示视频结束。所有场景均评估完整输出结尾，不接受提前截断的终点；AVIR 标注评估完整标注视频，AVIR 预测评估完整生成续写。

| `status` | 含义 |
|---|---|
| `ok` | 视频已生成并保存，不等于评估通过 |
| `error` | 生成或保存失败 |
| `unsupported` | 模型不具备该任务需要的能力 |
| `skipped` | 未执行该任务，必须给出原因 |

非 `ok` 记录必须包含非空 `reason`，且 `output=null`：

```json
{"id":"ADR-001","status":"unsupported","reason":"The model does not support audio-conditioned generation","output":null}
```

校验器检查 ID、重复和缺失记录、声明范围、协议版本、数据集哈希身份、输出文件和路径、布局及评估时间区间。`--probe` 还检查 VDR/AVIR 预测前缀边界、AVIR 标注时长、AVIR 音轨存在性、MSR 宽画幅和视频流。这些检查不代表动作正确、音频保真或双视角同步已经通过。

## 4. 模型能力与公平比较

模型可只声明支持的场景。在声明范围内，失败或不支持的任务必须保留为 `unsupported`、`error` 或 `skipped`，不能通过删除任务提高报告成绩。

音频转写、视频抽帧、通过其他模型转换生成条件等步骤须记录在 `preprocessing`。不同输入条件或组合流水线应分别报告。用评估器声音描述替代源音频，不属于原始音频输入任务。

当前主评测要求输出视频。纯文本或多模态理解模型需要另行定义文本答案、事件预测或定位输出及相应指标，不能直接使用视频生成成绩。

模型比较应采用相同场景或固定的共同 ID 集合，并报告测试范围。不同范围、预处理协议或评估器版本的总体成绩，不应混合形成同一排名。

## 5. 评估与报告

`evaluate.py` 将四个场景的原始评估器统一到同一提交协议。第一阶段仅根据源媒体、prompt 和 ADR/AVIR 声音描述进行盲预测，不查看生成视频或参考结果。第二阶段按时间顺序读取输出帧，结合参考答案、盲预测和场景约束进行判断。裁判通过与音频哈希绑定的英文描述获得声音信息。两类 AVIR 任务还会在本地比较解码后的源音频和输出音频波形。AVIR 预测使用专门的未来预测裁判，不评估红圈正确性，也不要求生成动作保持不变。

下表 AVIR 权重对应**矛盾标注任务**；预测任务的权重另见下文。

| 评估项权重 | ADR | VDR | AVIR 标注 | MSR |
|---|---:|---:|---:|---:|
| 人工参考答案 | 55% | 55% | 50% | 45% |
| 模型盲预测 | 20% | 20% | 15% | 15% |
| 源连续性 / 续写连续性 | 15% | 15% | — | 10% |
| 物理一致性 | 10% | 10% | — | 10% |
| 标注正确性 | — | — | 15% | — |
| 源内容保留 | — | — | 10% | — |
| 音频保留 | — | — | 10% | — |
| 双视角同步 | — | — | — | 20% |

每项评分为 0、1、2 或 null。可用权重归一化为 0–100 分。通过要求总分至少 75，且关键评估项可判断、非零。关键项为 0 时失败；关键项无法判断或整体处于中间状态时可能标为 `unknown`。各场景 Python 模块包含精确的响应结构和判定规则。VDR/MSR 累计评估适用参考约束；ADR 区分可同时满足的约束与互斥备选结果；AVIR 标注结合实质参考分支、源保留与标注要求；AVIR 预测结合参考分支、音视频推理、续写连续性和音频保留。

**任务成功率（四场景准确率）**为 `pass / n`。`n` 包含所选范围内全部任务，包括 `unknown`、`generation_error`、`unsupported` 和 `skipped`，因此表示已确认成功的比例。存在未知结果时，`success_rate_bounds` 给出可能范围。每条任务只计一次，加权分数不能直接理解为百分比准确率。`decision_coverage=(pass + fail) / n` 为判定覆盖率，`decidable_success_rate=pass / (pass + fail)` 为可判定任务成功率。报告任务成功率时应同时给出覆盖率。

评估器或网络错误、待处理任务及试运行会使对应场景的任务成功率为 null，可用 `--resume` 补齐；其他场景仍可保留完整结果。报告会标明不同声明范围和显式 ID 子集，不能将它们当作完整基准结果比较。

AVIR 包含 48 条矛盾标注任务与 23 条未来预测任务，全部 71 条按各自协议参加评估。`scenarios.AVIR` 报告合并的任务成功率，`avir_subtasks` 分别报告标注与预测结果。预测任务权重为：人工参考 50%、盲预测 15%、音视频推理 15%、续写连续性 10%、音频保留 10%。其关键项为人工参考、音视频推理、连续性和音频保留。源保留条款约束的是源场景和音频，不能解释为禁止 prompt 所要求的未来动作。

默认采样源视频 8 帧、输出视频 20 帧，图片最长边为 1280 像素。模型比较时统一配置 `--input-frames`、`--output-frames`、`--max-side`。稀疏采样可能遗漏短暂事件，不能证明视频每个瞬间均正确。发布结果时记录裁判模型、配置和评估器版本。

## 6. 版本与复现

`<dataset-root>/data/dataset.json` 记录接口版本、任务数量和输入清单 SHA-256。`<dataset-root>/data/assets.jsonl` 提供媒体哈希与大小，便于核对本地文件一致性。

发布结果时记录清单哈希、模型和适配器版本、预处理、生成参数及随机种子。不同场景范围、输入条件或评分配置的结果应分别报告。

## 7. 引用（Citation）

如在研究中使用本数据集或评估框架，请引用以下论文：

[Can MiniMax-H3 Reason About the Physical World? An Evaluation of Omni-Modal Generative Model](https://arxiv.org/abs/2609.18323)。

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
