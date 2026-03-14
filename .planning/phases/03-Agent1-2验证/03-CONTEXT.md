# Phase 3: Agent1-2 验证 - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

验证预处理+意图识别 Agent（Agent1）和案例检索 Agent（Agent2）的输出格式和内容符合下游规格。这是 TDD 测试编写阶段，同时包含将原 anthropic SDK 替换为 GLM-4.6V + Qwen3.5 的代码改造。测试覆盖：正常路径、边界情况、低相关度警告。

</domain>

<decisions>
## Implementation Decisions

### 模型分工

- **GLM-4.6V**（智谱，`glm-4.6v`，`requests` 调用，base_url: `https://open.bigmodel.cn/api/paas/v4`）
  - 负责 Agent1 的图像理解：一次调用返回图像内容描述（替代原来的 PaddleOCR + Claude Vision 两条路径）
  - 不再有单独的 OCR 路径和 Vision 路径，GLM 全包
- **Qwen3.5-35b-a3b-fp8**（南审网关，OpenAI SDK 兼容，base_url: `https://ai-api.nau.edu.cn/v1`）
  - 负责 Agent1 的意图分类：接收 GLM 的图像描述，输出 `intent_label`、`confidence`、`key_features`、`content_summary`
- **Agent2**：纯本地向量检索，不调用任何大模型 API，使用 sentence-transformers 本地 embedding
- **Phase 3 包含代码改造**：将 agent1_preprocessor.py 中的 anthropic SDK 调用替换为 GLM + Qwen 双调用，然后再写 TDD 测试

### API 调用策略

- **单元测试和集成测试均真实调用 API**（不 mock GLM/Qwen）
- API Key 通过 `.env` 环境变量注入：
  - `ZHIPU_API_KEY` → GLM-4.6V
  - `NAU_API_KEY`（或 `OPENAI_API_KEY`）→ Qwen3.5
- 删除所有 PaddleOCR 相关测试和 `pytest.skip()` 标记（OCR 路径已由 GLM 完全替代）
- sentence-transformers embedding 不需要 API Key，本地运行

### intent_label 配置化

- Agent1 输出的 `intent_label` 类型**存入配置文件**（如 `config/intent_labels.json`），数量和名称可由用户自定义
- Claude 设计初始 10 种标签作为默认值
- 测试验证输出的 label 属于配置文件中定义的合法值列表

### Agent2 检索规格

- sentence-transformers 具体模型**以现有 agent2_retrieval.py 代码为准**（不变更）
- 相似度阈值 **0.65 可配置**（从配置加载），默认值 0.65
- 返回字段：每条案例包含 `similarity_score`（浮点）+ 案例内容字段（以现有数据结构为准）
- 当 TOP-5 平均相似度 < 0.65 时，输出包含低相关度警告标志

### Claude's Discretion

- intent_label 初始10种具体内容（用户说"你自己决定"）
- API Key 环境变量命名规范（NAU_API_KEY vs OPENAI_API_KEY）
- 测试文件中 GLM/Qwen 的 fixture 设计
- 各测试用例的具体边界输入数据

</decisions>

<specifics>
## Specific Ideas

- **标签可配置化**：用户明确要求 intent_label 的数量和名称将来可由用户自行设定，应设计为从配置文件读取而非硬编码
- **两套 API 调用风格不同**：GLM 用 `requests`，Qwen 用 OpenAI SDK，两套客户端初始化需在 Agent1 中共存
- API 调用文件参考：`D:\个人项目\mutiagent_trea\api-key-hardcode-example.nau-zhipu.txt`

</specifics>

<deferred>
## Deferred Ideas

- 标签可配置化 Web UI 入口 — 属于 v2 Web 可视化阶段
- Qwen3.5 参与 Agent2 语义重排序 — 若相似度不理想可在 Phase 4/5 评估引入

</deferred>

---

*Phase: 03-Agent1-2验证*
*Context gathered: 2026-03-14*
