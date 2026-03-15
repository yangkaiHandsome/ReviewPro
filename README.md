# ReviewPro

ReviewPro 是一个面向桌面场景的 AI 文档审查系统，适用于规格说明、SOR 文档、扫描版 PDF 以及图纸类页面等技术文件。

它将 WPF 客户端与 FastAPI 后端结合起来，提供基于策略的文档审查、页面预览、页级标注、异步审核任务，以及可选的 LLM 辅助分析能力。

## 概述

这个项目围绕一个很实际的目标设计：让文档审查过程可追踪、可视化、可复用。

ReviewPro 不把 PDF 当成一个不可拆分的黑盒文件，而是将其转换为一个按页面索引的审查对象：

- 定义可复用的审查策略和规则
- 上传 PDF 或图片文档
- 提取页面元数据和文本块
- 在审查预算约束下生成页面审查计划
- 运行异步审核任务
- 在桌面 UI 中以边界框形式展示页级问题

如果配置了 LLM API Key，后端可以调用兼容 Kimi 的接口生成结构化审核结果；如果没有配置，系统会回退到本地确定性启发式审核流程。

## 核心特性

- 策略管理：创建、编辑、删除并复用结构化审查策略
- 文档导入：支持 `PDF`、`PNG`、`JPG`、`JPEG`、`BMP`、`TIF`、`TIFF`
- 页面分析：识别文本密集页与图片密集页，并生成页面预览
- 基于预算的审查计划：挑选具有代表性的页面，而不是盲目逐页全量审查
- 异步审核流程：提交任务、轮询进度、重试失败或未完成任务
- 可视化审查 UI：浏览文档、查看页面、缩放，以及从问题结果跳转到页面标注
- 本地优先持久化：基于 SQLite，无需额外基础设施
- 可选 LLM 集成：配置后使用远程模型审查，否则走本地启发式审查

## 架构

### 前端

- 框架：`.NET 8` 上的 `WPF`
- 位置：`ReviewPro/ReviewPro`
- 职责：
  - 策略编辑
  - 文档列表与预览
  - 审核任务提交与进度轮询
  - 问题边界框可视化
  - 后端接口地址配置

### 后端

- 框架：`FastAPI`
- 位置：`backend`
- 职责：
  - 策略与文档 API
  - 文件上传与页面索引生成
  - 文本块提取与页面渲染
  - 审核队列处理
  - 审查计划生成
  - 结果持久化与查询

### 存储

- 数据库：`SQLite`
- 上传文件：`backend/storage/uploads`
- 页面索引缓存：`backend/storage/page_index`

## 工作流程

1. 在桌面客户端中创建一个审查策略。
2. 将文档上传到后端。
3. 后端分析文件并生成页面元数据：
   - 页数
   - 文本预览
   - 图片密度
   - 疑似目录页信号
   - 疑似图纸/重图片页信号
4. 系统根据页面预算生成审查计划，因此可以优先审查有代表性的页面，而不是始终扫描整份文档。
5. 审核工作线程从队列中拉取任务。
6. 后端收集页面载荷：
   - 文本型页面使用文本块
   - 图纸类或重图片页面使用图像模式
7. 后端执行以下两种方式之一：
   - 兼容 Kimi 的 LLM 审核
   - 本地启发式回退审核
8. 结构化问题结果被保存，并在 WPF 客户端中以页级高亮形式展示。

## 仓库结构

```text
.
|-- README.md
|-- ReviewPro/
|   |-- ReviewPro.sln
|   |-- ReviewPro/
|       |-- App.xaml
|       |-- MainWindow.xaml
|       |-- Models/
|       |-- Services/
|       `-- ReviewPro.csproj
`-- backend/
    |-- app/
    |   |-- api/
    |   |-- services/
    |   |-- config.py
    |   `-- main.py
    |-- tests/
    |-- requirements.txt
    |-- Dockerfile
    `-- docker-compose.yml
```

## 技术栈

- 桌面 UI：`WPF`、`C#`、`.NET 8`
- 后端 API：`FastAPI`、`Python`
- 数据库：`SQLite`、`SQLAlchemy`
- PDF 处理：`PyMuPDF`
- 图像处理：`Pillow`
- HTTP 客户端：`httpx`
- 测试：`pytest`

## 环境要求

- WPF 前端需要 Windows
- `.NET SDK 8.0+`
- `Python 3.10+`

## 快速开始

### 1. 启动后端

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

后端 API 基础地址：

`http://127.0.0.1:8000/api`

### 2. 启动桌面客户端

```powershell
cd ReviewPro
dotnet run --project .\ReviewPro\ReviewPro.csproj
```

### 3. 使用应用

1. 打开客户端。
2. 确认后端地址为 `http://127.0.0.1:8000/api`。
3. 创建或编辑一个审查策略。
4. 上传文档。
5. 运行审核并查看生成的问题结果。

## 配置

后端从 `backend/.env` 中读取配置，配置项统一使用 `REVIEWPRO_` 前缀。

示例：

```env
REVIEWPRO_DATABASE_URL=sqlite:///./storage/reviewpro.db
REVIEWPRO_STORAGE_DIR=storage
REVIEWPRO_LOG_LEVEL=INFO
REVIEWPRO_LLM_API_KEY=
REVIEWPRO_LLM_BASE_URL=https://coding.dashscope.aliyuncs.com/v1
REVIEWPRO_LLM_MODEL=qwen3.5-plus
REVIEWPRO_MAX_PAGE_BUDGET=20
REVIEWPRO_MAX_PAGE_BUDGET_RATIO=0.3
REVIEWPRO_MIN_REVIEW_PAGES=4
REVIEWPRO_MAX_PREVIEW_CHARS=800
```

说明：

- 将 `REVIEWPRO_LLM_API_KEY` 留空时，系统会使用内置启发式回退路径。
- `REVIEWPRO_MAX_PAGE_BUDGET` 及相关设置用于控制每次审查选取的页面数量。
- WPF 客户端会将后端地址保存到当前用户的本地应用数据目录下。

## API 概览

主要后端接口：

- `GET /api/health`
- `GET /api/strategies`
- `POST /api/strategies`
- `PUT /api/strategies/{strategy_id}`
- `DELETE /api/strategies/{strategy_id}`
- `GET /api/documents`
- `POST /api/documents/upload`
- `GET /api/documents/{doc_id}/pages`
- `GET /api/documents/{doc_id}/search-pages`
- `GET /api/documents/{doc_id}/page/{page_number}/text-blocks`
- `GET /api/documents/{doc_id}/page/{page_number}/image`
- `DELETE /api/documents/{doc_id}`
- `POST /api/audit`
- `GET /api/audit/job/{job_id}`
- `GET /api/audit/{doc_id}`
- `POST /api/audit/{doc_id}/retry`

## 当前行为与设计取舍

- 系统针对的是文档审查流程，而不是文档编辑。
- 审核任务是异步的，由后台工作线程处理。
- 审查计划基于预算生成，用于控制长文档场景下的成本和延迟。
- 文本密集页优先采用文本块审查，以获得更精确的标注结果。
- 图片密集页优先采用图像模式，以更好兼容扫描件和图纸类文件。
- 后端首次启动时会预置一个默认策略。

## 开发

### 构建前端

```powershell
dotnet build ReviewPro\ReviewPro.sln
```

### 运行后端测试

```powershell
cd backend
python -m pytest -q
```

在撰写原 README 时，本地验证状态为：

- 前端构建：成功
- 后端测试：`8 passed`

## 已知限制

- 桌面客户端当前基于 WPF，因此只支持 Windows。
- 项目暂不提供在线多人协作能力。
- 审查质量取决于文档类型、规则质量以及是否配置了外部 LLM。
- 图纸/重图片文档已支持，但其精确语义理解仍然比原生文本 PDF 更困难。

## 开源发布说明

如果你计划把这个仓库发布到 GitHub，建议在发布前补充以下内容：

- `LICENSE` 文件
- 截图或简短演示 GIF
- 安全且不含敏感信息的示例文档
- 简短的变更记录或路线图

## 路线图想法

- 更丰富的规则结构与规则模板
- 可导出的审查报告
- 更好的扫描文档 OCR 支持
- 更多审查计划启发式策略与模型驱动的页面路由
- 容器化的一体化全栈启动流程

## 许可

当前仓库尚未包含许可证文件。如果你希望它作为开源项目被复用，请在发布前补充许可证。
