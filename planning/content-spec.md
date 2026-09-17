# Project content and design brief

English academic research project website; Chinese communication with owner. Local drafts only, not published. Repository: https://github.com/gulucaptain/MiniMax-H3-Reason . Use actual manuscript figures supplied under docs/assets. No external decorative imagery, no invented logos or model affiliation.

Exact paper title: Can MiniMax-H3 Reason About the Physical World? An Evaluation of Omni-Modal Generative Model
Project name: MiniMax-H3-Reason
Authors: Haoyu Zhao*,†; Zihao Zhao*; Tianyu Deng*; Ziqin Xu*; Zihao Zhang; Xudong Wang; Jinxiang Guo; Chen Gao; Xiaobin Hu; Ziyi Ye; Yeying Jin‡; Jiaxi Gu‡; Zuxuan Wu; Shuicheng Yan.
Affiliations: National University of Singapore; Fudan University; Tencent. * Equal contribution; † Project lead; ‡ Corresponding authors. See manuscript for individual affiliations.

Core question: Can a model infer what to generate from incomplete, complementary multimodal evidence?
Core finding: Supporting multimodal inputs does not ensure reliable task completion.
Implicit prompts leave task-relevant information unstated. Complementary observations support an inference expressed through video generation, continuation, or editing.
517 evaluation instances, 4 scenarios, 29 subcategories; overall human-evaluated success rate 41.97%.
MSR — Multi-view Spatial Reasoning: multiple images + text; cross-view correspondence and spatial consistency; 200 instances, 10 subcategories, 43.50% SR.
ADR — Audio-based Disambiguation Reasoning: image + audio + text; resolve ambiguous visual events through acoustic evidence; 146 instances, 6 subcategories, 27.40% SR.
VDR — Video-based Decision Reasoning: prefix video + text; infer an appropriate continuation from observed dynamics; 100 instances, 8 subcategories, 56.00% SR.
AVIR — Audiovisual Integrated Reasoning: video + audio + text; ground audio evidence or spoken constraints in continuation or editing; 71 instances, 5 subcategories, 47.89% SR.
Three experts independently judge outputs and cross-check assessments. Multiple valid outputs allowed. Success is task satisfaction, not visual quality alone. Overall SR is sample-weighted. Scenario differences are not controlled modality comparisons. Outputs are behavioral evidence, not direct inspection of internal reasoning.
ADR example: a cabinet-opening sound or typewriter audio can guide a matching visual event. docs/assets/adr-examples.png is Fig 11, representative generated frames; no video files available. Do not create dummy video players.
Failure example from manuscript: cat-meowing audio animates the dog while cat remains inactive. Do not present a fabricated output.

Page structure: hero/title/authors/resources; central finding; overview image; four scenario definitions; results table or labeled bars with denominators; actual qualitative figure; evaluation protocol and limitations; resource status.
Resource status: local repo initially only README. Paper public URL not provided. Data/annotations/evaluation code/video downloads absent. Display plain 'Link pending' or status, never fake buttons or href=# resources. Working repository link permitted. No conference acceptance, release date, license, or installation command claims.

Three standalone responsive HTML drafts in planning/design-demos, each with inline CSS, embed the PNG figures as data URIs. Mobile >= 375px, body >= 16px, label >= 12px. All layouts distinct. Add short assumption comment at top. Each draft must include real content beyond hero and internally working navigation. Do not publish or select a final direction.
