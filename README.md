# Can MiniMax H3 Reason About the Physical World?
### An Evaluation of Omni-Modal Generative Model

[![arXiv Paper](https://img.shields.io/badge/arXiv-2609.18323-B31B1B?logo=arxiv&logoColor=white)](https://arxiv.org/abs/2609.18323)
[![Hugging Face Dataset](https://img.shields.io/badge/Hugging%20Face-Dataset-FFD21E?logo=huggingface&logoColor=black)](https://huggingface.co/datasets/gulucaptain/MiniMax-H3-Reason)

**In this research, we ask that can a generative model infer what it should generate from complementary multimodal evidence?**

We study physical-world reasoning through video generation, continuation, and editing. Instead of describing the complete target event, our prompts leave task-relevant information to be inferred from images, audio, and video. We evaluate whether generated outputs satisfy the semantic constraints supported by those observations.

**517 evaluation instances · 4 reasoning scenarios · 29 subcategories · 41.97% overall success rate**

[Overview](#overview) · [Reasoning scenarios](#reasoning-scenarios) · [Results](#results) · [Evaluation protocol](#evaluation-protocol) · [Qualitative examples](#qualitative-examples) · [Citation](#citation)

## TODO List

- [x] Release the paper on arXiv — 2026-09-17.
- [ ] Open-source evaluation results — TODO.
- [ ] Open-source the evaluation dataset — TODO.

## Overview

![Overview of the evaluation framework and its four physical-world reasoning scenarios](assets/overview.jpg)

Our evaluation asks whether a model can recover task-relevant information that is left unstated in the text prompt. Depending on the task, this involves integrating multiple views, identifying an event from its sound, anticipating a response to observed dynamics, or grounding auditory constraints in video.

The framework provides:

- **Implicit task prompts:** the requested generation operation is specified, while the target inference remains grounded in the observations.
- **Complementary evidence:** four scenarios test spatial, temporal, and audiovisual relationships.
- **Task-specific evaluation:** experts assess whether the generated video satisfies the intended semantic requirement, allowing multiple valid visual realizations.

Our central finding is that **supporting multimodal inputs does not ensure reliable task completion**. MiniMax-H3 succeeds on 41.97% of the 517 evaluated instances.

## Reasoning scenarios

All scenarios include a text prompt.

| Scenario | Additional inputs | What a successful output must demonstrate | Instances | Subcategories |
| --- | --- | --- | ---: | ---: |
| **MSR** — Multi-view Spatial Reasoning | Multiple images | Preserve spatial relationships and coordinated actions across complementary views | 200 | 10 |
| **ADR** — Audio-based Disambiguation Reasoning | Image + audio | Resolve visual ambiguity and depict the event supported by the acoustic cue | 146 | 6 |
| **VDR** — Video-based Decision Reasoning | Prefix video | Continue observed dynamics with an appropriate response to the task | 100 | 8 |
| **AVIR** — Audiovisual Integrated Reasoning | Video + audio | Incorporate auditory evidence or spoken constraints into continuation or editing | 71 | 5 |
| **Total** | | | **517** | **29** |

For example, ADR may present several candidate sound sources in an image. The model must associate the supplied sound with the correct object and express that interpretation through the generated event. AVIR extends audio grounding to temporally evolving video, including the localization of content that conflicts with spoken constraints.

## Results

Human-evaluated success rates for MiniMax-H3, as reported in the manuscript:

| Scenario | Instances | Success rate ↑ |
| --- | ---: | ---: |
| MSR | 200 | 43.50% |
| ADR | 146 | 27.40% |
| VDR | 100 | **56.00%** |
| AVIR | 71 | 47.89% |
| **Overall** | **517** | **41.97%** |

The overall rate is calculated over all instances, not as an unweighted average of the four scenario rates.

- **VDR has the highest success rate** in this evaluation; ADR has the lowest.
- **Audio grounding remains challenging.** Selected failures include associating a sound with the wrong visible source and confusing similar mechanical sounds.
- **Visual plausibility is insufficient.** A generated video can look convincing while failing the required spatial, temporal, or audiovisual condition.

The scenarios differ in data, prompts, and generation targets. Their success rates describe task-level performance and are not a controlled comparison of the intrinsic value of different modalities.

## Qualitative examples

Successful generations from the Video-based Decision Reasoning (VDR) scenario. Click any animated preview to open the full video with audio.

<p align="center">
  <a href="assets/videos/VDR-004.mp4" title="VDR-004 · Watch video"><img src="assets/previews/VDR-004.gif" alt="VDR-004 — successful VDR generation" width="30%"></a>
  <a href="assets/videos/VDR-006.mp4" title="VDR-006 · Watch video"><img src="assets/previews/VDR-006.gif" alt="VDR-006 — successful VDR generation" width="30%"></a>
  <a href="assets/videos/VDR-011.mp4" title="VDR-011 · Watch video"><img src="assets/previews/VDR-011.gif" alt="VDR-011 — successful VDR generation" width="30%"></a>
</p>

<p align="center">
  <a href="assets/videos/VDR-013.mp4" title="VDR-013 · Watch video"><img src="assets/previews/VDR-013.gif" alt="VDR-013 — successful VDR generation" width="30%"></a>
  <a href="assets/videos/VDR-025.mp4" title="VDR-025 · Watch video"><img src="assets/previews/VDR-025.gif" alt="VDR-025 — successful VDR generation" width="30%"></a>
  <a href="assets/videos/VDR-037.mp4" title="VDR-037 · Watch video"><img src="assets/previews/VDR-037.gif" alt="VDR-037 — successful VDR generation" width="30%"></a>
</p>

<p align="center">
  <a href="assets/videos/VDR-047.mp4" title="VDR-047 · Watch video"><img src="assets/previews/VDR-047.gif" alt="VDR-047 — successful VDR generation" width="30%"></a>
  <a href="assets/videos/VDR-058.mp4" title="VDR-058 · Watch video"><img src="assets/previews/VDR-058.gif" alt="VDR-058 — successful VDR generation" width="30%"></a>
  <a href="assets/videos/VDR-060.mp4" title="VDR-060 · Watch video"><img src="assets/previews/VDR-060.gif" alt="VDR-060 — successful VDR generation" width="30%"></a>
</p>

<p align="center">
  <a href="assets/videos/VDR-061.mp4" title="VDR-061 · Watch video"><img src="assets/previews/VDR-061.gif" alt="VDR-061 — successful VDR generation" width="30%"></a>
  <a href="assets/videos/VDR-063.mp4" title="VDR-063 · Watch video"><img src="assets/previews/VDR-063.gif" alt="VDR-063 — successful VDR generation" width="30%"></a>
  <a href="assets/videos/VDR-066.mp4" title="VDR-066 · Watch video"><img src="assets/previews/VDR-066.gif" alt="VDR-066 — successful VDR generation" width="30%"></a>
</p>

<p align="center">
  <a href="assets/videos/VDR-072.mp4" title="VDR-072 · Watch video"><img src="assets/previews/VDR-072.gif" alt="VDR-072 — successful VDR generation" width="30%"></a>
</p>

## Evaluation protocol

1. **Construct the instance.** Pair multimodal observations with an implicit prompt and an annotated semantic target.
2. **Verify the evidence.** Experts check whether the observations support the intended inference and whether the prompt leaves that inference unstated.
3. **Generate the output.** Use the task's observations and prompt for video generation, continuation, or editing.
4. **Assess task satisfaction.** Three experts independently judge each output and then cross-check their assessments against the inputs and task instructions.

Success rate is the number of successful instances divided by the number of evaluated instances, multiplied by 100. Evaluation permits multiple valid outputs rather than requiring a match to one reference video.

Generated outputs provide behavioral evidence about the complete generation process. They do not directly expose an internal reasoning mechanism; failures may arise from perception, evidence integration, or generation.

## Citation

If you find this work useful, please cite our paper:

```bibtex
@misc{zhao2026minimaxh3reason,
  title         = {Can {MiniMax-H3} Reason About the Physical World? An Evaluation of Omni-Modal Generative Model},
  author        = {Haoyu Zhao and Zihao Zhao and Tianyu Deng and Ziqin Xu and Zihao Zhang and Xudong Wang and Jinxiang Guo and Chen Gao and Ziyi Ye and Yeying Jin and Jiaxi Gu and Zuxuan Wu and Shuicheng Yan},
  year          = {2026},
  eprint        = {2609.18323},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CV},
  url           = {https://arxiv.org/abs/2609.18323}
}
```

## Data sources and usage

The manuscript draws on real and synthetic visual and acoustic sources. Named dataset sources include HiFi-UMI-2K, VISTA-UMI-5K, HuMI-Unsheathe, Hy-Embodied-0.5-VLA-Data, 10Kh-RealOmin-OpenData, LLaVA-Video-178K, FSD50K, and ESC-50. Full bibliographic details are provided in the manuscript.

No repository license has been specified yet. Refer to the respective source datasets for their usage terms; this repository does not grant additional rights to third-party materials.
