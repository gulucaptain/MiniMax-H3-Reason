# Project page 内容组织与发布准备

## 内容依据

以 Writing/version2/neurips_2026.tex 和 secs/{intro,methods,exps}.tex 为依据。保留论文当前英文标题、作者顺序、单位、任务名称和数值；没有写入投稿录用信息或未经证实的公开资源链接。

当前远程仓库：https://github.com/gulucaptain/MiniMax-H3-Reason

## README 与主页分工

README 面向准备了解和使用资源的研究者：项目概述 → 四类任务 → 定量结果 → 真实案例 → 评测协议 → 资源状态 → 作者和引用。

Project page 面向第一次接触项目的读者：研究问题 → 核心发现 → 框架图 → 四类任务 → 结果 → 成功与失败案例 → 评测方法与解释边界 → 资源入口。

## 首屏文案

Project: MiniMax-H3-Reason

Title: Can MiniMax-H3 Reason About the Physical World?

Subtitle: An Evaluation of Omni-Modal Generative Model

Lead: Can a generative model infer what it should generate from complementary multimodal evidence?

Summary: We evaluate physical-world reasoning through video generation, continuation, and editing. Implicit prompts leave task-relevant information to be recovered from images, audio, and video.

Evidence strip: 517 evaluation instances / 4 reasoning scenarios / 29 subcategories / 41.97% overall success rate.

主结论：Supporting multimodal inputs does not ensure reliable task completion.

## 案例区的下一步素材组织

每个真实案例应包含：任务类别、原始输入、音频播放器（有音频时）、准确提示词、生成视频、判断结果，以及一句可核对的解释。展示顺序建议 MSR → ADR → VDR → AVIR。每类最终选择一个成功和一个失败案例。

当前使用论文原图，明确标记为静态帧；不把静态图片伪装成可播放视频，也不把论文举例当作原始评测提示词。

## 重要事实边界

- 41.97% 是 517 个样本的总体成功率，不是四类百分比的简单平均。
- 四类任务的数据、提示词与生成目标不同，不能把排序直接解释为模态本身优劣。
- 输出是行为层面的证据，不能凭此直接断言内部推理机制。
- 当前论文标题单数 “An Evaluation of Omni-Modal Generative Model” 按原文保留；若作者决定修订语法，README 与主页同步更新。
- 暂不添加没有公开记录的 BibTeX、arXiv 编号、会议徽标、下载按钮或安装命令。

## 发布前需要补齐的项目资料

1. 论文公开链接及正式引用信息。
2. 确认作者与单位沿用 version2；作者个人主页链接可后补。
3. 数据、提示词、标注、视频与评测代码的实际发布范围和位置。
4. 仓库许可与第三方素材的使用说明。
5. 从三个可查看的 HTML 初稿中确定最终方向，再形成 docs/index.html。

## 本地预览

三个初稿是独立 HTML，图片已内嵌，可以直接打开；位于 planning/design-demos/。它们用于选择方向，尚不是公开发布的主页。选定后整理 docs/index.html 和共享资源，保持相对链接以便部署。
