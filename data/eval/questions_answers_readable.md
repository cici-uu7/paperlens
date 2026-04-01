# PaperLens 标准版 20 题评测集

这份文件已经替换原来的基础测试题，现在只保留标准版测试题。

分布如下：

- 普通问答：10 题
- 表格问题：4 题
- 跨文档对比：4 题
- 无法回答：2 题

对应的机器可读文件是：

- `questions.csv`

## 一、普通问答 10 题

1. Q: LayoutLM在文档理解里最核心的建模对象是什么？
   A: LayoutLM联合建模文档中的文本内容与二维版面布局，并可结合图像特征提升文档理解。

2. Q: LayoutLMv2新增的两个跨模态预训练任务是什么？
   A: LayoutLMv2新增了文本图像对齐任务 TIA 和文本图像匹配任务 TIM。

3. Q: LayoutLMv3中的WPA目标具体预测什么？
   A: WPA预测某个文本词对应的图像块是否被mask，用来学习词与图像块的跨模态对齐。

4. Q: Donut中的OCR-free具体是什么意思？
   A: Donut不依赖外部OCR系统，而是把原始文档图像直接映射到目标文本或结构化输出。

5. Q: RAG把哪两类记忆结合在一起？
   A: RAG把参数化的生成模型记忆与非参数化的检索记忆结合在一起，后者通常是可检索的文档索引。

6. Q: Self-RAG为什么比固定检索式RAG更灵活？
   A: Self-RAG可以按需决定是否检索，并通过reflection tokens对检索结果和生成内容进行自我批判与控制。

7. Q: DocLLM为融入版面信息，主要依赖什么输入，而不是昂贵的视觉编码器？
   A: DocLLM主要依赖文本token及其bounding box坐标来建模版面信息，而不是依赖昂贵的图像编码器。

8. Q: ColPali的核心检索对象是什么？
   A: ColPali直接对文档页面图像生成表示，并用late interaction机制进行页面级检索。

9. Q: DocLLM针对视觉文档设计的预训练目标是什么？
   A: DocLLM采用面向视觉文档的text infilling目标，按语义连贯的文本块进行补全文本。

10. Q: ColPali论文同时发布了哪个视觉文档检索基准？
    A: ColPali论文同时发布了视觉文档检索基准ViDoRe。

## 二、表格问题 4 题

11. Q: 根据LayoutLM在FUNSD上的表格结果，最佳F1是多少，使用了哪些信息？
    A: 最佳F1是0.7927，对应同时使用文本信息、版面布局信息和图像信息。

12. Q: 根据Donut在RVL-CDIP上的分类结果表，Donut的准确率和推理时延分别是多少？
    A: Donut在RVL-CDIP上的准确率是95.30%，推理时延约为752毫秒。

13. Q: 根据Donut在CORD上的信息抽取结果表，Donut的F1和TED准确率分别是多少？
    A: Donut在CORD上的F1是84.1，TED准确率是90.9。

14. Q: 根据LayoutLMv2的实体抽取结果表，LayoutLMv2 Large在FUNSD上的F1是多少，比LayoutLM Large高多少？
    A: LayoutLMv2 Large在FUNSD上的F1是0.8420，比LayoutLM Large的0.7895高0.0525。

## 三、跨文档对比 4 题

15. Q: 比较RAG和Self-RAG的检索策略，它们最大的区别是什么？
    A: RAG通常先检索固定数量的文档再生成，而Self-RAG会按需触发检索，并在生成过程中用reflection tokens进行自我评估和控制。

16. Q: 比较Donut和DocLLM处理视觉文档的方式：一个更偏端到端图像生成，一个更偏文本加版面建模，它们分别是哪种？
    A: Donut是OCR-free的端到端图像到结构化输出方法；DocLLM则是基于文本和bounding box的版面感知语言模型。

17. Q: 比较LayoutLMv3和ColPali对图像信息的使用目的：谁更偏通用文档理解，谁更偏页面检索？
    A: LayoutLMv3更偏通用文档理解与多任务预训练，ColPali更偏页面级文档检索。

18. Q: 比较LayoutLMv2和LayoutLMv3的预训练设计，哪一个强调TIA和TIM，哪一个强调统一的文本与图像masking加WPA？
    A: LayoutLMv2强调TIA和TIM等跨模态对齐任务；LayoutLMv3强调统一的文本masking与图像masking，并加入WPA目标。

## 四、无法回答 2 题

19. Q: 这批文档里有没有给出PaperLens项目自己的FastAPI启动命令？
    A: 当前文档集不包含PaperLens项目代码或部署命令，系统应明确说明无法根据现有文档回答。

20. Q: 这批文档里是否提供了2026年最新GPU租赁价格对比表？
    A: 当前文档集不包含2026年的GPU租赁价格信息，系统应拒答并说明缺少文档证据。
