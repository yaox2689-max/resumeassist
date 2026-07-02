<div align="center">

# ResumeAst

**AI 模拟面试平台 | AI Agent Development**

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Vue%203-4FC08D?style=flat&logo=vue.js&logoColor=white" alt="Vue 3">
  <img src="https://img.shields.io/badge/WebSocket-Realtime-blue" alt="WebSocket">
  <img src="https://img.shields.io/badge/ReAct%20Agent-Custom-orange" alt="ReAct Agent">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="MIT License">
</p>

<p align="center">
  面向求职面试场景的 AI 模拟面试平台，自研 ReAct Agent 框架，支持文字/语音双模式面试、JD 分析、简历多模态分析，以及跨会话分层记忆系统。
</p>

<p align="center">
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-核心功能">核心功能</a> ·
  <a href="#-架构设计">架构设计</a> ·
  <a href="#-技术栈">技术栈</a> ·
  <a href="#-项目结构">项目结构</a> ·
  <a href="#-roadmap">Roadmap</a> ·
  <a href="#-contributing">参与贡献</a>
</p>

<br>

</div>

---

## 核心功能

### 模拟面试（文字 + 语音双模式）

- **文字模式**：基于 SSE 流式输出，ReAct Agent 逐步推理、追问，支持打断恢复
- **语音模式**：基于 WebSocket 双泵架构，实时语音 LLM（DashScope Qwen-Omni / OpenAI Realtime），支持语义 VAD、双向实时转写、barge-in 打断
- **一键切换**：文字/语音无缝衔接，历史对话自动回放，handoff 指令防止上下文断裂

### Agent 框架（自研 ReAct）

- **7 态有限状态机**：IDLE → THINKING → STREAMING_TEXT → EXECUTING_TOOLS → AGGREGATING → INTERRUPTED → COMPACTING，严格校验转换，任意状态可中断
- **上下文压缩**：超 80K token 自动摘要旧轮次，保留近 3 轮完整对话
- **工具系统**：装饰器声明 + Pydantic 参数校验 + 白名单隔离 + 超时控制
- **LLM 降级**：主模型 ProviderError 时自动切换 fallback 模型

### 配置驱动（YAML Agent Profile）

```yaml
id: "interviewer-technical"
llm:
  provider: "mimo"
  model: "mimo-v2.5-pro"
  temperature: 0.7
  fallback: { provider: "mimo", model: "mimo-v2.5" }
tools: ["save_real_question"]
realtime:
  provider: "dashscope_realtime"
  vad_mode: "semantic"
  max_session_minutes: 15
```

不同面试官角色（技术面/行为面/综合面）只需一个 YAML 文件，不改代码。

### 分层记忆系统

```
storage/memory/<user_id>/
├── user.md                    # 用户画像（跨简历共享）
└── <resume_id>/
    ├── INTERVIEW_NOTE.md      # 面试官笔记（跨会话持久化）
    └── REAL_QUES.md           # 真实面试题
```

- **实时路径**：用户提到面试题 → `save_real_question` 工具即时写入
- **异步路径**：面试结束 → `summary-generator` Agent 从对话中提取用户画像和面试官笔记，LLM 智能合并写入

### 其他能力

- **JD 分析**：粘贴职位描述，结构化拆解核心要求、隐含期望
- **简历分析**：支持 PDF/图片多模态解析，AI 给出改进建议
- **面试总结**：面试结束后自动生成报告（亮点、建议、技术/行为评估）
- **Langfuse 可观测性**：全链路追踪 ReAct 步骤、工具调用、LLM 耗时、token 消耗

---

## 架构设计

### 文字模式（SSE 流式）

```
┌─────────┐    POST /messages    ┌──────────────┐    stream     ┌─────────┐
│  Vue 3  │ ──────────────────►  │   FastAPI    │ ────────────► │  LLM    │
│ Frontend│ ◄──────────────────  │ ReActAgent   │ ◄──────────── │ Provider│
│         │    GET /stream (SSE)  │  7态FSM      │   tool_use    │         │
└─────────┘                      └──────┬───────┘               └─────────┘
                                        │
                                   ┌────▼────┐
                                   │  Tools  │
                                   │ (Pydantic)
                                   └─────────┘
```

### 语音模式（WebSocket 双泵）

```
┌─────────┐   WebSocket    ┌──────────────────────────┐   WS/HTTP   ┌──────────────┐
│  Client │ ◄────────────► │     RealtimeAgent        │ ◄─────────► │ Realtime LLM │
│  Audio  │                │  ┌─────────────────────┐ │             │ (Qwen-Omni)  │
└─────────┘                │  │ 上行泵: 音频/指令转发 │ │             └──────────────┘
                           │  │ 下行泵: 音频/事件推送 │ │
                           │  └─────────────────────┘ │
                           │  + MidSummary (8min)     │
                           │  + Inactivity Watchdog   │
                           └──────────────────────────┘
```

### 状态机（文字模式 7 态）

```
IDLE ──► THINKING ──► STREAMING_TEXT ──► [end_turn] ──► IDLE
              ▲              │
              │         [tool_use]
              │              ▼
              └── AGGREGATING ◄── EXECUTING_TOOLS

任何状态 ──[interrupt]──► INTERRUPTED ──► IDLE
THINKING ──[>80k token]──► COMPACTING ──► THINKING
```

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- 至少一个 LLM API Key（MiMo / DashScope / DeepSeek）

### 后端

```bash
cd backend
uv sync                          # 安装依赖（推荐 uv）
cp .env.example .env             # 填入 LLM API Key
#uv run uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
uv run uvicorn api.app:app --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev                      # 开发服务器 http://localhost:3000
```

### 语音模式（可选）

语音面试需要配置实时语音 LLM 的 API Key：

```bash
# .env
DASHSCOPE_API_KEY=sk-xxx         # DashScope（默认）
OPENAI_API_KEY=sk-xxx            # OpenAI Realtime（可选）
```

### Langfuse 追踪（可选）

```bash
# .env 中设置
TRACER=langfuse
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx

# 或使用 Docker Compose 启动本地 Langfuse
docker compose --profile langfuse up -d
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | Vue 3 + Vite + Tailwind CSS + Pinia |
| **后端** | FastAPI + 自研 ReAct Agent + WebSocket |
| **数据库** | SQLite (aiosqlite) + SQLAlchemy 2.0 |
| **事件存储** | JSONL Event Sourcing（过滤高频事件，保留关键对话） |
| **记忆系统** | 分层 Markdown 文件 + LLM 智能合并 |
| **LLM Provider** | MiMo / DashScope / DeepSeek（文本）；DashScope Qwen-Omni / OpenAI Realtime（语音） |
| **可观测性** | Langfuse（OpenTelemetry SDK） |

---

## 项目结构

```
resumeassist/
├── backend/                     # FastAPI 后端
│   ├── agent/                   #   Agent 核心
│   │   ├── loop.py              #     ReActAgent（文字模式，7态FSM）
│   │   ├── realtime_agent.py    #     RealtimeAgent（语音模式，双泵架构）
│   │   ├── factory.py           #     AgentFactory（配置驱动创建）
│   │   ├── profile.py           #     AgentProfile（Pydantic 配置模型）
│   │   ├── context/             #     上下文构建与压缩
│   │   └── llm/                 #     LLM 抽象层 + Provider 实现
│   │       ├── providers/       #       文本 LLM（MiMo、DeepSeek、DashScope）
│   │       └── realtime/        #       实时语音 LLM（OpenAI、DashScope）
│   ├── api/                     #   路由层（REST / SSE / WebSocket）
│   ├── config/                  #   配置 + Agent Profile YAML
│   │   └── agents/              #     7 个面试官角色配置
│   ├── tool/                    #   工具系统（装饰器 + 注册表 + 执行器）
│   ├── service/                 #   业务逻辑（会话、简历、任务）
│   ├── storage/                 #   数据存储（SQLite、JSONL、Markdown 记忆）
│   ├── trace/                   #   Langfuse 可观测性
│   ├── data/                    #   系统提示词 + 技能定义
│   └── tests/                   #   测试
├── frontend/                    # Vue 3 前端
│   └── src/
│       ├── pages/               #   页面（首页、面试、简历、JD 分析）
│       ├── components/          #   组件（面试、通用、Landing）
│       ├── composables/         #   组合式函数（语音、配置）
│       ├── stores/              #   Pinia 状态管理
│       └── api/                 #   接口层
└── README.md
```

---

## Agent Profile 配置

所有面试官角色通过 YAML 配置定义，支持热插拔（改配置无需重启，新会话自动加载）：

| Profile | 用途 |
|---------|------|
| `interviewer-technical` | 技术面试官 |
| `interviewer-behavior` | 行为面试官 |
| `interviewer-comprehensive` | 综合面试官 |
| `resume-analyzer` | 简历分析 |
| `jd-analyzer` | JD 分析 |
| `summary-generator` | 面试总结生成 |
| `mid-summary-injector` | 语音中段摘要 |

---

## Roadmap

### 简历-JD 智能匹配

基于简历内容和目标 JD，自动计算匹配度评分，生成差距分析报告（技能缺口、经验匹配、关键词覆盖），并据此生成针对性的面试准备建议和模拟面试题。

### 多 Agent 协作

引入评分 Agent 和策略 Agent，与面试官 Agent 并行工作：评分 Agent 实时监听对话流并打分，策略 Agent 根据评分动态调整后续问题方向，面试结束后自动生成结构化评估报告。

### 面试实时评分

在 ReAct 循环中增加 `score_answer` 工具，Agent 自主决定何时对用户回答进行评分（不是每轮都评，而是有代表性的一轮才评），评分结果存入记忆层，面试结束时汇总成多维评估报告。

### 记忆系统增强

引入工具记忆层框架（`memory_layer`）：工具执行结果自动写入持久化记忆文件并注入 system prompt，天然免疫上下文压缩。支持记忆淘汰策略（按时间/频次淘汰旧数据），防止 system prompt 膨胀。

### RAG 知识检索

复用 RAG 检索能力，为面试官 Agent 增加 `search_knowledge` 工具。用户回答技术问题时，Agent 可实时检索知识库验证答案准确性，实现精准追问。

### 上下文压缩优化

引入工具结果分离保留机制：压缩前提取 `role: tool` 的结构化数据单独注入 system prompt，只对纯对话内容做摘要，确保工具调用结果不被自然语言化丢失。

---

## Contributing

欢迎贡献！请阅读以下步骤：

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'feat: add your feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 提交 Pull Request

### 开发规范

- Python：遵循 PEP 8，使用 `ruff` 格式化
- Vue：遵循 Vue 3 Composition API 规范
- 提交信息：使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式
- 新功能请附带测试

---

## License

[MIT License](LICENSE) © 2026 [yaox2689-max](https://github.com/yaox2689-max)

---

<div align="center">
  <sub>Built with ❤️ by ResumeAst</sub>
</div>
