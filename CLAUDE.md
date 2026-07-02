# AI Persona Engine - Project Rules

## 架构规则
- 所有模块必须使用抽象基类（ABC）定义接口
- 禁止模块间直接导入实现类，必须通过接口通信
- 所有模块间通信通过定义好的接口进行
- 每个流水线阶段必须支持流式处理（Streaming）

## 技术栈（已锁定）
- Python 3.11 in xpu_env conda 环境
- GPU: Intel ARC B580（使用 "xpu" 设备，禁止使用 "cuda"）
- ASR: SenseVoice via FunASR
- LLM: OpenAI 兼容 API（openai SDK）
- TTS: Fish Speech
- Avatar: LivePortrait / Hallo
- Backend: FastAPI + Uvicorn + WebSockets
- Frontend: Vue 3 + Vite
- Logging: loguru（禁止使用 print）
- Testing: pytest
- Config: YAML 文件，通过 config_loader 加载

## 编码规范
- 遵循 PEP 8，4 空格缩进，函数/变量使用 snake_case
- 所有公共函数签名必须有类型提示（Type Hints）
- 所有公共函数和类必须有 Docstring
- 配置通过 YAML 文件管理，禁止硬编码值
- 错误处理：try/except + loguru 日志，禁止静默失败
- 中文注释在领域相关逻辑处使用，增加可读性

## 设备管理
- 始终使用 utils.device 模块获取计算设备
- 默认 "xpu:0"，不可用时回退 "cpu"
- 使用 `torch.xpu.is_available()` 检测，永远不要假设 CUDA 可用

## 人格规则
- 每个人格回复必须包含 AI 身份免责声明
- 高风险话题（医疗、法律等）需额外免责声明
- 人格配置文件位于 backend/persona_interface/<name>/

## 交互模式
- MVP/V1 采用半双工模式（Push-to-Talk / Click-to-Record）
- 全双工（打断功能）作为后续迭代，不阻塞主流程
- 延迟目标：首包响应 < 2 秒

## 文件约定
- 模型文件、音频、视频等二进制文件不入 git（加入 .gitignore）
- 测试文件与源码布局镜像，位于各模块的 tests/ 目录下
- 日志输出到 logs/ 目录
