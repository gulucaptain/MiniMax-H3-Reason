# MiniMax-H3-Reason

**中文（默认）** | [English](docs/README.en.md)

[论文](https://arxiv.org/abs/2609.18323) · [Hugging Face 数据集](https://huggingface.co/datasets/gulucaptain/MiniMax-H3-Reason) · [详细使用说明](docs/USAGE.zh-CN.md) · [论文介绍与结果](docs/PROJECT.en.md)

面向多模态视频生成模型的统一接入与自动评估工具，支持 ADR、VDR、AVIR、MSR 四个场景。

**数据与工具独立发布：**Hugging Face 提供 517 条任务、734 个源媒体文件、参考答案和声音描述；本 GitHub 仓库提供数据加载 SDK、模型适配接口、视频导入与校验、裁判服务适配及自动评分。原有论文展示素材保留在 `assets/`，它们不是测试输入。

## 工作介绍

**视频生成模型能否根据互补的多模态证据，推断自己应该生成什么？** 我们围绕这一问题构建 MiniMax-H3-Reason，评估模型在物理世界中的空间、时间和音视频推理能力。任务提供图像、声音或视频观察，文本 prompt 指定生成、续写或编辑操作；模型需要从观察中推断关键的目标事件，而不是只复现文字描述。

基准包含 **517 条任务、4 个场景、29 个子类别**。评估关注生成结果是否满足证据支持的语义条件，允许多种合理的视觉实现，不要求与某个参考视频逐像素一致。

![四类物理世界推理任务概览](assets/overview.jpg)

| 场景 | 输入（均含文本 prompt） | 任务目标 | 数量 | 子类别 |
|---|---|---|---:|---:|
| ADR — Audio-based Disambiguation Reasoning | 图像 + 音频 | 根据声音消除视觉歧义，生成对应事件 | 146 | 6 |
| VDR — Video-based Decision Reasoning | 前缀视频 | 根据已有动态预测并续写合理的后续行为 | 100 | 8 |
| AVIR — Audiovisual Integrated Reasoning | 视频 + 音频 | 检查音视频矛盾并画红圈，或预测接下来发生的事件 | 71 | 5 |
| MSR — Multi-view Spatial Reasoning | 包含两个视角的单张图像 | 保持多视角间的空间关系和动作协调 | 200 | 10 |

AVIR 的两类任务分别包含 48 条矛盾标注和 23 条未来预测；每条任务的 prompt 与任务字段决定应执行的操作。

## 论文结果与生成示例

论文中，MiniMax-H3 在全部 517 条任务上的**人工评估总体成功率为 41.97%**。这一结果表明，多模态输入能力并不自动保证模型能够完成证据驱动的生成任务。

| 场景 | 论文人工评估成功率 |
|---|---:|
| ADR | 27.40% |
| VDR | 56.00% |
| AVIR | 47.89% |
| MSR | 43.50% |
| 全部任务 | 41.97% |

总体成功率按全部任务计算。以上是论文的人工评估结果，使用下方自动评估工具得到的裁判评分应单独报告，并注明裁判模型和配置。

以下为论文中 VDR 的成功生成示例，点击预览可查看完整视频：

<p align="center">
  <a href="assets/videos/VDR-004.mp4"><img src="assets/previews/VDR-004.gif" alt="VDR-004" width="30%"></a>
  <a href="assets/videos/VDR-006.mp4"><img src="assets/previews/VDR-006.gif" alt="VDR-006" width="30%"></a>
  <a href="assets/videos/VDR-011.mp4"><img src="assets/previews/VDR-011.gif" alt="VDR-011" width="30%"></a>
</p>

<p align="center">
  <a href="assets/videos/VDR-013.mp4"><img src="assets/previews/VDR-013.gif" alt="VDR-013" width="30%"></a>
  <a href="assets/videos/VDR-025.mp4"><img src="assets/previews/VDR-025.gif" alt="VDR-025" width="30%"></a>
  <a href="assets/videos/VDR-058.mp4"><img src="assets/previews/VDR-058.gif" alt="VDR-058" width="30%"></a>
</p>

更多定性示例、人工评估流程及数据来源见 [完整论文介绍](docs/PROJECT.en.md)。下面介绍如何使用同一基准评测自己的视频生成模型。

## 快速开始

使用 Python 3.10+，在项目根目录执行：

```bash
git clone https://github.com/gulucaptain/MiniMax-H3-Reason.git
cd MiniMax-H3-Reason
python3 -m pip install -r requirements.txt
python3 sdk/download_dataset.py
```

默认数据目录是 `datasets/MiniMax-H3-Reason/`，已在 `.gitignore` 中排除，不提交到 GitHub。下载工具先将 `main` 解析为具体提交，再固定该提交下载数据，校验任务清单与参考文件哈希，记录到数据目录的 `download_metadata.json`。

固定历史数据版本或自定义目录：

```bash
python3 sdk/download_dataset.py --revision COMMIT_SHA --output-dir /path/to/data
```

下载目标已存在时不会覆盖；升级数据请选新目录。已有本地数据无需重复下载：向导入和评分命令传入 `--dataset-root /path/to/data`。这应是包含 `data/`、`media/` 的数据根目录。

## 接入生成模型

四个场景统一使用 `sdk/interface.py` 的 `load_cases()` 和 `ModelAdapter.generate(request, output_root)` 协议。模型服务的上传、生成、轮询和保存流程由使用者实现，参见 [适配器示例](examples/model_adapter.py)。这是可扩展接口，不内置各生成服务的专用 API 实现。

```python
from sdk.interface import load_cases

for request in load_cases('datasets/MiniMax-H3-Reason', scenarios={'ADR'}):
    print(request['id'], request['inputs']['image']['local_path'])
    # 将 request 的 prompt 和源媒体传入你的模型适配器。
```

被测模型只读取任务和源媒体，不得使用 `data/evaluation/` 下的参考材料。生成模型 Key 与裁判 Key 分别配置。也可跳过适配器，直接导入已有视频。

## 导入已有视频并评估

视频按 case ID 命名，如 `ADR-001.mp4`。导入会按数据集任务类型选择布局，未生成的任务保留为 `skipped`，仍计入分母。

```bash
python3 sdk/create_submission.py \
  --videos-dir /path/to/generated_videos --output-dir my_submission \
  --model-id my-video-model --model-version 1.0
python3 evaluate.py --submission my_submission/outputs.jsonl \
  --report-dir checks --dry-run
```

`--dry-run` 只执行本地校验，不调用裁判 API、不计算任务成功率。完善 `my_submission/submission.json` 中的真实预处理、生成参数和种子后，选择裁判配置：

| 裁判服务 | 配置示例 | 默认 Key 环境变量 |
|---|---|---|
| DeepSeek | `configs/judges/deepseek.json` | `DEEPSEEK_API_KEY` |
| Kimi | `configs/judges/kimi.json` | `MOONSHOT_API_KEY` |
| OpenAI / GPT | `configs/judges/openai.json` | `OPENAI_API_KEY` |
| 其他兼容服务 | `configs/judges/compatible.json` | `JUDGE_API_KEY` |

裁判模型须支持图片输入及 JSON 回答，配置示例可按服务和账号权限调整。以 OpenAI 示例为例：

```bash
cp configs/judges/openai.json judge_config.json
python3 evaluate.py --judge-config judge_config.json --check-judge --prompt-key
python3 evaluate.py --submission my_submission/outputs.jsonl \
  --judge-config judge_config.json --prompt-key --report-dir evaluation_results
```

`--prompt-key` 隐藏读取 Key，仅用于当前进程；也可设置配置文件 `api_key_env` 指定的环境变量并省略此选项。不要将 Key 提交到仓库。预检和正式评分会调用服务并可能产生费用。首次可加 `--case-ids ADR-001 VDR-001` 测试，失败或中断后可加 `--resume` 继续。

AVIR 含 48 条矛盾标注、23 条未来预测，两类任务按各自评分协议处理。VDR/AVIR 预测输出默认仅续写，包含前缀时在导入命令中添加 `--vdr-layout with_prefix` / `--avir-layout with_prefix`。完整配置、布局和评分规则见 [详细使用说明](docs/USAGE.zh-CN.md)。

## 结果与复现

`evaluation_results/summary.json` 的 `scenarios` 包含四个场景的任务成功率 `task_success_rate=pass/n`（包含未知、失败、不支持、跳过），以及判定覆盖率；`avir_subtasks` 分别报告 AVIR 两种任务。评估器错误、待处理和试运行使相关成功率为 null，不会计为模型失败。

报告记录任务清单和参考哈希、裁判配置、采样参数、评估器版本、代码内容哈希和 GitHub 提交。使用下载工具时还记录 Hugging Face 具体提交；手工提供本地数据时，无法推断远端提交，会标记为本地来源。尚未提交的代码以代码内容哈希区分，不能仅依靠 Git 提交号复现。

## 项目结构

```text
MiniMax-H3-Reason/
├── README.md
├── evaluate.py                  # 统一评分入口
├── sdk/                         # 下载、加载、模型协议、导入与校验
├── examples/model_adapter.py    # 使用者实现生成服务的适配器示例
├── evaluator/                   # 四场景评分、裁判客户端与媒体处理
├── configs/judges/              # 裁判配置示例，不含 Key
├── scripts/                     # 单场景入口、数据展示视图维护工具
├── requirements.txt             # 下载与评分依赖
├── requirements/eval.txt
├── submission_template/         # 当前数据版本的提交格式参考模板
├── tests/                       # 合成视频与模拟裁判的离线测试
├── docs/                        # 中英文工具说明与原论文介绍
└── assets/                      # 原有论文展示素材
```

提交模板绑定当前数据清单哈希；数据版本变化时优先使用导入工具按新数据生成提交。测试不调用真实模型 API：

```bash
python3 -m unittest discover -s tests -v
```

发布数据检查需已下载数据，或通过 `MINIMAX_H3_DATASET_ROOT` 指定其位置。没有数据时，这部分检查会跳过；合成数据评估和裁判契约测试仍可运行。

## Citation

论文说明、原始人工评估成绩与定性展示见 [项目介绍](docs/PROJECT.en.md)。使用数据或工具时，请引用：

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
