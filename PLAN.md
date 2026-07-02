# AI Persona Engine - 总体规划与进度追踪

> **用途**：跨会话的开发进度记录。每次新开 Claude Code 会话时，阅读此文件即可了解项目全貌和当前进度。
>
> **最后更新**：2026-07-01
>
> **当前阶段**：Phase 0 - 项目脚手架（未开始）

---

## 项目概览

**目标**：构建实时语音交互数字人平台，完整闭环为：

```
用户说话 → ASR(SenseVoice) → Persona/LLM → TTS(Fish Speech) → Avatar(LivePortrait/Hallo) → 视频输出
```

**技术栈**：
| 模块 | 方案 | 环境 |
|------|------|------|
| GPU | Intel ARC B580 | PyTorch 2.7.0+xpu |
| ASR | SenseVoice (FunASR 1.3.14) | xpu_env conda |
| LLM | OpenAI兼容API (openai 2.44.0) | DeepSeek/Qwen/本地 |
| TTS | Fish Speech 0.1.0 | xpu_env conda |
| Avatar | LivePortrait/Hallo | onnxruntime + face-alignment |
| Backend | FastAPI 0.138.2 + Uvicorn + WebSocket | xpu_env conda |
| Frontend | Vue 3 + Vite | Node.js |
| 工具 | loguru / pytest / redis / librosa | xpu_env conda |

---

## 目录结构设计

```
D:\AI-Persona\
├── CLAUDE.md                          # Claude Code 项目规则
├── PLAN.md                            # 本文件：总规划与进度
├── .gitignore
├── requirements.txt
│
├── backend/
│   ├── __init__.py
│   ├── app.py                         # FastAPI 主入口
│   ├── config/
│   │   ├── __init__.py
│   │   ├── app_config.yaml            # 主配置文件
│   │   └── config_loader.py           # YAML配置加载器（单例）
│   ├── speech_interface/
│   │   ├── __init__.py
│   │   ├── base_asr.py               # ASR 抽象接口
│   │   ├── sensevoice_asr.py          # SenseVoice 实现
│   │   └── tests/
│   │       └── test_asr.py
│   ├── persona_interface/
│   │   ├── __init__.py
│   │   ├── base_persona.py            # Persona 抽象接口
│   │   ├── base_llm.py                # LLM 抽象接口
│   │   ├── openai_llm.py              # OpenAI兼容 LLM 实现
│   │   ├── persona_manager.py         # 人格管理器（V2）
│   │   ├── conversation.py            # 会话历史管理
│   │   ├── zhangxuefeng/
│   │   │   ├── persona.yaml           # 人格配置
│   │   │   ├── prompt.txt             # 系统提示词
│   │   │   └── skills.py              # 技能函数（可选）
│   │   └── tests/
│   │       └── test_persona.py
│   ├── tts_interface/
│   │   ├── __init__.py
│   │   ├── base_tts.py                # TTS 抽象接口
│   │   ├── fish_speech_tts.py         # Fish Speech 实现
│   │   └── tests/
│   │       └── test_tts.py
│   ├── avatar_interface/
│   │   ├── __init__.py
│   │   ├── base_avatar.py             # Avatar 抽象接口
│   │   ├── liveportrait_avatar.py     # LivePortrait 实现
│   │   └── tests/
│   │       └── test_avatar.py
│   ├── websocket_handler/
│   │   ├── __init__.py
│   │   ├── ws_manager.py              # WebSocket 连接管理
│   │   ├── protocol.py                # 消息协议定义
│   │   └── pipeline.py                # 流水线编排器
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py                  # loguru 日志配置
│   │   ├── device.py                  # XPU/CPU 设备管理
│   │   └── metrics.py                 # 延迟指标追踪
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py                # 共享 pytest fixtures
│       └── test_integration.py
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── App.vue
│       ├── main.js
│       ├── composables/
│       │   ├── useWebSocket.js        # WebSocket 连接
│       │   ├── useAudioRecorder.js    # 麦克风录音
│       │   └── useMediaPlayer.js      # 音视频播放
│       ├── components/
│       │   ├── AvatarVideo.vue        # 视频显示
│       │   ├── SubtitleBar.vue        # 实时字幕
│       │   ├── MicrophoneButton.vue   # 录音按钮
│       │   ├── StatusBar.vue          # 状态栏
│       │   └── DisclaimerBanner.vue   # AI身份免责声明
│       └── assets/
│           └── styles.css
│
├── personas/                          # 人格模板目录
│   └── README.md
└── docs/
    ├── architecture.md
    ├── websocket-protocol.md
    └── deployment.md
```

---

## WebSocket 消息协议

```
Client                        Server (pipeline.py)
  |                                |
  |-- session_start ------------->|  选择人格，初始化会话
  |<------------ status -----------|  "Ready"
  |                                |
  |-- audio_start --------------->|  开始 ASR 流式识别
  |-- audio_binary (chunk 1) ---->|  发送音频数据
  |-- audio_binary (chunk 2) ---->|
  |<---------- asr_partial --------|  部分识别结果
  |-- audio_binary (chunk N) ---->|
  |-- audio_end ----------------->|  ASR 最终识别
  |<------------ asr_final --------|  最终文字
  |                                |
  |                               |  [ASR → Persona/LLM]
  |<------------ llm_chunk --------|  LLM 流式文本
  |<------------ llm_chunk --------|
  |                               |  [LLM → TTS（流水线）]
  |<------------ tts_audio --------|  TTS 音频块（二进制）
  |<------------ tts_audio --------|
  |                               |  [TTS → Avatar（流水线）]
  |<------------ avatar_frame -----|  视频帧（二进制 JPEG）
  |<------------ avatar_frame -----|
  |<------------ llm_done ---------|  LLM 生成完毕
  |<------------ tts_done ---------|  TTS 合成完毕
  |<------------ avatar_done ------|  Avatar 生成完毕
  |                                |
  |-- session_end --------------->|  清理会话
```

**消息类型枚举**：

| 方向 | 类型 | 说明 |
|------|------|------|
| C→S | `session_start` | 初始化会话，指定人格 |
| C→S | `audio_start` | 开始发送音频 |
| C→S | `audio_binary` | PCM 音频块（二进制帧） |
| C→S | `audio_end` | 音频发送完毕 |
| C→S | `text_message` | 直接文本输入（跳过ASR） |
| C→S | `session_end` | 结束会话 |
| S→C | `asr_partial` | ASR部分识别结果 |
| S→C | `asr_final` | ASR最终识别结果 |
| S→C | `llm_chunk` | LLM流式文本块 |
| S→C | `llm_done` | LLM生成完毕 |
| S→C | `tts_audio` | TTS音频块（二进制帧） |
| S→C | `tts_done` | TTS合成完毕 |
| S→C | `avatar_frame` | 视频帧（二进制帧） |
| S→C | `avatar_done` | Avatar生成完毕 |
| S→C | `status` | 系统状态 |
| S→C | `error` | 错误信息 |
| S→C | `disclaimer` | AI身份免责声明 |

---

## 分阶段实施计划

### Phase 0: 项目脚手架

**目标**：搭建项目骨架，初始化版本控制

**步骤**：
1. `git init` 初始化仓库
2. 创建完整目录结构（所有文件夹 + `__init__.py`）
3. 编写 `CLAUDE.md`（项目规则：架构约束、技术栈锁定、编码规范、设备管理、人格规则、文件约定）
4. 编写 `.gitignore`（Python缓存、模型文件、音视频、node_modules、.env等）
5. 创建 `requirements.txt`
6. 首次 git commit

**预计工时**：~4小时
**前置依赖**：无
**阻塞**：后续所有阶段

---

### Phase 0.5: 配置系统

**目标**：实现统一配置管理

**步骤**：
1. 创建 `backend/config/app_config.yaml`，包含：
   - `server`（host, port, debug）
   - `device`（preferred: auto/xpu/cpu, xpu_device_id）
   - `asr`（engine选择 + sensevoice参数：model, vad_model, language, batch_size_s）
   - `llm`（engine选择 + openai_compatible参数：base_url, api_key_env, model, max_tokens, temperature, stream）
   - `tts`（engine选择 + fish_speech参数：model_path, sample_rate, reference_audio）
   - `avatar`（engine选择 + liveportrait参数：model_path, source_image, fps）
   - `persona`（active, directory, max_history_turns）
   - `websocket`（audio_chunk_duration_ms, max_message_size_mb）
   - `logging`（level, file, rotation）
2. 实现 `config_loader.py`：
   - `AppConfig` 单例类
   - `get(dotted_key, default)` 支持 `"asr.sensevoice.model"` 形式
   - `resolve_env(env_key_name)` 解析环境变量
3. 实现 `device.py`：
   - `get_device()` 函数
   - 优先级：配置偏好 > XPU > CPU
   - 使用 `torch.xpu.is_available()` 检测
   - 回退时记录 warning 日志

**预计工时**：~2小时
**前置依赖**：Phase 0
**阻塞**：所有模块实现

---

### Phase 1: 抽象接口层

**目标**：定义所有模块的抽象契约，这是架构骨架

**步骤**：

1. **`base_asr.py`** — ASR 抽象接口
   - `ASRResult` 数据类：text, language, confidence, is_final, start_ms, end_ms
   - `BaseASR(ABC)`：
     - `async initialize()` — 加载模型
     - `async transcribe(audio_bytes, sample_rate) -> ASRResult` — 完整音频转写
     - `async transcribe_stream(audio_chunks, sample_rate) -> AsyncIterator[ASRResult]` — 流式转写
     - `async shutdown()` — 释放资源

2. **`base_llm.py`** — LLM 抽象接口
   - `LLMMessage` 模型：role, content
   - `LLMConfig` 模型：model, temperature, max_tokens, stream
   - `BaseLLM(ABC)`：
     - `async initialize(config)` — 初始化客户端
     - `async generate(messages, config) -> str` — 完整生成
     - `async generate_stream(messages, config) -> AsyncIterator[str]` — 流式生成
     - `async shutdown()`

3. **`base_persona.py`** — Persona 抽象接口
   - `BasePersona(ABC)`：
     - `name: str`
     - `async initialize()` — 加载人格配置
     - `get_system_prompt() -> str` — 返回系统提示词
     - `async generate_response(user_text, history) -> str` — 完整回复
     - `async generate_response_stream(user_text, history) -> AsyncIterator[str]` — 流式回复
     - `build_messages(user_text, history) -> list[LLMMessage]` — 构建消息列表（有默认实现）
     - `async shutdown()`

4. **`base_tts.py`** — TTS 抽象接口
   - `TTSChunk` 数据类：audio_bytes, sample_rate, is_last, duration_ms
   - `BaseTTS(ABC)`：
     - `async initialize()`
     - `async synthesize(text, voice) -> TTSChunk` — 完整合成
     - `async synthesize_stream(text, voice) -> AsyncIterator[TTSChunk]` — 流式合成
     - `async shutdown()`

5. **`base_avatar.py`** — Avatar 抽象接口
   - `VideoFrame` 数据类：frame_bytes, format, width, height, timestamp_ms, audio_chunk
   - `BaseAvatar(ABC)`：
     - `async initialize()`
     - `async set_source_image(image_path)`
     - `async generate_frames(audio_chunk) -> list[VideoFrame]`
     - `async generate_frames_stream(audio_stream) -> AsyncIterator[VideoFrame]`
     - `async shutdown()`

6. **`protocol.py`** — WebSocket 消息协议
   - `MsgType` 枚举（18种消息类型）
   - `WSMessage` 模型：type, data, session_id, timestamp_ms

7. **`ws_manager.py`** — WebSocket 连接管理
   - `ConnectionManager` 类
   - `connect(websocket, session_id)`, `disconnect(session_id)`
   - `send_json(session_id, message)`, `send_bytes(session_id, data)`

**预计工时**：~6小时
**前置依赖**：Phase 0, Phase 0.5
**阻塞**：所有具体实现

---

### Phase 2: MVP — 基础语音问答（纯文本）

**目标**：用户说话 → 看到转写文字 → 看到 LLM 文字回答

**步骤**：

1. **`logger.py`** — loguru 配置
   - 从 config 读取 level/file/rotation
   - stderr + 文件双输出

2. **`sensevoice_asr.py`** — SenseVoice ASR 实现
   - 使用 `funasr.AutoModel(model="iic/SenseVoiceSmall", vad_model="fsmn-vad")`
   - 同步推理用 `asyncio.to_thread()` 包装
   - 音频格式转换：int16 PCM → numpy float32
   - 流式模式：内部维护音频缓冲区，VAD 分段后逐段推理

3. **`openai_llm.py`** — OpenAI 兼容 LLM 实现
   - `openai.AsyncClient(base_url=..., api_key=...)`
   - 流式：`stream=True`，逐 chunk yield `delta.content`
   - 支持 DeepSeek / Qwen / 本地 Ollama 等

4. **`conversation.py`** — 会话历史管理
   - `ConversationManager` 按 session_id 管理历史
   - 滑动窗口：保留 system prompt + 最近 N 轮

5. **`zhangxuefeng/`** — 张雪峰人格配置
   - `persona.yaml`：name, display_name, description, disclaimer, voice
   - `prompt.txt`：角色设定、表达风格、回答要求

6. **`app.py`** — FastAPI 主入口
   - startup 事件：初始化日志、加载配置、初始化流水线
   - shutdown 事件：释放资源
   - WebSocket 端点 `/ws/{session_id}`
   - 健康检查 `GET /health`

7. **`pipeline.py`** — MVP 流水线（ASR→LLM）
   - 接收 WebSocket 音频帧 → 缓冲 → ASR → LLM 流式 → 发送文字
   - 使用 asyncio.Queue 连接各阶段
   - 各阶段作为独立 asyncio.Task 并发运行

8. **前端 MVP**
   - `useWebSocket.js`：WebSocket 连接与消息分发
   - `useAudioRecorder.js`：MediaRecorder/AudioWorklet 录音，16kHz PCM
   - `App.vue`：麦克风按钮 + ASR文字区 + LLM回答区 + 状态指示

9. **测试**
   - `test_asr.py`：SenseVoice 初始化、转写、错误处理
   - `test_persona.py`：提示词构建、历史管理、免责声明注入
   - `test_integration.py`：mock 全链路集成测试

**验收标准**：
- 浏览器打开，点击麦克风说中文，看到转写文字
- LLM 回答流式显示为文字
- 端到端可测量延迟

**预计工时**：~16小时
**前置依赖**：Phase 0, 0.5, 1
**阻塞**：V1 TTS/Avatar 集成

---

### Phase 3: V1 — TTS + Avatar

**目标**：完整闭环：说话 → 数字人视频+语音回复+字幕

**步骤**：

1. **`fish_speech_tts.py`** — Fish Speech TTS 实现
   - 调研 Fish Speech 0.1.0 的 Python API
   - 同步推理包装为 async
   - 句子级流式：按中文标点分句，逐句合成
   - 输出 PCM 音频，可配置采样率
   - 声音克隆：传入参考音频路径
   - XPU 兼容性验证

2. **`liveportrait_avatar.py`** — LivePortrait Avatar 实现
   - **关键调研**：LivePortrait 是视频驱动，非原生音频驱动
   - 方案选择：Hallo/Hallo2（音频驱动）或 Wav2Lip（口型同步）
   - 音频 → 唇形帧的流水线
   - JPEG 压缩输出，25fps 目标
   - async 线程运行

3. **流水线扩展**
   - pipeline.py 增加 TTS 和 Avatar 阶段
   - `ASR → Queue → LLM → Queue → TTS → Queue → Avatar → WebSocket`
   - 各阶段独立 asyncio.Task

4. **前端完善**
   - `AvatarVideo.vue`：Canvas 渲染 JPEG 帧
   - `useMediaPlayer.js`：AudioContext PCM 播放 + 帧同步
   - `SubtitleBar.vue`：ASR + LLM 实时字幕
   - `DisclaimerBanner.vue`：AI 身份免责声明
   - `StatusBar.vue`：连接状态 + 延迟显示

5. **集成测试**
   - mock 音频输入 → 验证所有消息按正确顺序到达
   - TTS 流式测试：验证音频块产生
   - 延迟测试：音频结束到首帧的时间

**验收标准**：
- 完整闭环：说话 → 看到数字人口型视频 + 听到语音 + 看到字幕
- 首包延迟 < 3 秒（争取 < 2 秒）
- 口型与音频基本同步

**预计工时**：~28小时
**前置依赖**：MVP 完成

---

### Phase 4: V2 — 人格系统 + 性能优化

**目标**：多人格支持、延迟优化 < 2 秒、长期稳定运行

**步骤**：

1. **`persona_manager.py`** — 人格管理器
   - 扫描人格目录，自动发现 persona.yaml
   - 按名称加载/切换人格
   - `list_personas()` / `get_persona(name)`

2. **流式优化**
   - 句子级 TTS：LLM 生成到句号/问号即送 TTS，不等完整回答
   - ASR 部分结果预热：partial 结果就开始准备 LLM
   - 模型预热：启动时跑一次 dummy 推理
   - 音频分块：50-100ms 小块发送

3. **`metrics.py`** — 延迟追踪
   - `PipelineMetrics` 数据类
   - 记录 ASR/LLM/TTS/Avatar 各阶段时间
   - 输出汇总日志

4. **多轮对话增强**
   - 上下文窗口管理
   - Redis 会话持久化（可选）
   - 人格状态保持

5. **内容安全**
   - 输入过滤（敏感词）
   - 输出过滤（有害内容检查）
   - 免责声明强制注入

6. **测试**
   - 并发会话负载测试
   - P50/P95 延迟测试
   - 人格切换测试
   - 20+ 轮长对话稳定性测试

**验收标准**：
- 多人格可加载和切换
- 首包延迟稳定 < 2 秒
- 连续运行 30+ 分钟无崩溃
- 日志显示各阶段延迟指标

**预计工时**：~40小时
**前置依赖**：V1 完成

---

## 交互延迟风险评估

### 流水线延迟链分析

完整链路中每个阶段的延迟估算：

```
用户停止说话
  │
  ├─── [1] VAD 静音检测 ──────────── 200~500ms（等待足够静音判定说完）
  ├─── [2] ASR 识别 ──────────────── 200~800ms（SenseVoice，取决于音频长度）
  ├─── [3] LLM 首个句子 ──────────── 100~2000ms（取决于 API/本地、prompt 长度）
  ├─── [4] TTS 首个音频块 ────────── 300~1000ms（Fish Speech，取决于是否 XPU）
  ├─── [5] Avatar 首批视频帧 ─────── 100~500ms（取决于帧数缓冲）
  ├─── [6] 网络回传 ──────────────── 10~200ms
  │
  ▼
用户看到/听到第一个响应
```

> **关键**：阶段 [3][4][5] 可以通过 asyncio 队列流水线部分重叠（LLM 生成第一个句号时就送 TTS，TTS 产出第一个音频块就送 Avatar），但 [1][2] 必须在 [3] 之前完成。

### 场景一：半双工模式（不考虑打断）

用户说完话 → 等待 AI 完整回答 → 用户再说下一句。

**延迟预算表**：

| 阶段 | 最佳 | 典型 | 最差 | 瓶颈说明 |
|------|------|------|------|----------|
| VAD 静音检测 | 200ms | 300ms | 500ms | 需要 300ms 静音才判定说完，不可压缩 |
| ASR 识别 | 100ms | 400ms | 800ms | SenseVoice 无流式 API，需缓冲完整语音 |
| LLM 首句 | 100ms | 800ms | 2000ms | 云 API 首 token 延迟高；本地模型更快 |
| TTS 首块 | 300ms | 500ms | 1000ms | Fish Speech CPU 慢，XPU 未验证 |
| Avatar 首帧 | 100ms | 200ms | 500ms | LivePortrait 需积累最小帧数才能输出 |
| 网络 | 10ms | 30ms | 200ms | 局域网 vs 远程 |
| **合计** | **810ms** | **2230ms** | **5000ms** | — |

**流水线优化后**（LLM→TTS→Avatar 并行）：

| 配置 | 串行延迟 | 流水线延迟 | 目标 |
|------|----------|-----------|------|
| 云 LLM + CPU TTS/Avatar | ~5000ms | ~3000ms | 难以达标 |
| 云 LLM + XPU TTS/Avatar | ~3000ms | ~2000ms | 勉强达标 |
| 本地 LLM + CPU TTS/Avatar | ~3500ms | ~2200ms | 勉强达标 |
| **本地 LLM + XPU TTS/Avatar** | **~2500ms** | **~1500ms** | **达标** |

**半双工结论**：
- 原方案 2 秒目标在**最优配置**下可达标
- 典型配置下约 2~3 秒，用户体验可接受（类似 Siri/小爱的等待感）
- **最大瓶颈**：VAD 静音检测（200-500ms）+ ASR 无流式 API（需缓冲完整语音）
- 用户体验风险：等待感明显但可接受，行业对标 Google Duplex (~1.5s) 仍有差距

---

### 场景二：全双工模式（考虑打断）

用户可以在 AI 说话过程中随时插话打断，AI 需立即停止并处理新输入。

**相比半双工，全双工需要额外解决 5 个核心问题**：

#### 问题 1: 回声消除（AEC）

```
┌─────────────┐    扬声器播放 AI 语音
│   用户端     │◄─────────────────────┐
│             │                       │
│  麦克风采集  │─── 混合了 AI 回声 ───►│ 需要 AEC 分离出纯净人声
└─────────────┘                       │
              ┌───────────────────────┘
              │ 回声信号
```

- **问题**：麦克风同时采集到用户声音和扬声器播放的 AI 语音（TTS 输出）
- **影响**：不做 AEC → ASR 会把 AI 自己说的话也识别为用户输入 → 死循环
- **方案**：
  - 浏览器端 AEC：WebRTC 内置 `echoCancellation`（`getUserMedia` 约束）
  - 效果有限：浏览器 AEC 质量参差不齐，残余回声仍可能导致误识别
  - 服务端 AEC：需额外处理，复杂度高
- **延迟开销**：AEC 本身 ~10-30ms，但质量问题会导致**误触发**而非延迟问题
- **风险等级**：🔴 高

#### 问题 2: 打断检测（Barge-in Detection）

```
AI 正在说话 ──────────────────────────►
                用户开始插话 ──────────────────────►
                    │
                    ├── 检测到打断 ──► 停止 AI ──► 处理新输入
                    │
                    ▼
              检测延迟：200~500ms
```

- **问题**：如何区分"用户清嗓子/环境噪音"和"用户真正想打断"？
- **方案**：
  - 服务端 VAD 持续运行（即使 AI 在输出）
  - 需要能量阈值 + 语音活动双重判定
  - 通常需要 200-500ms 语音活动才判定为有效打断
- **延迟开销**：200-500ms 检测延迟
- **误判风险**：
  - 漏检：用户插话但系统没检测到 → 用户体验极差
  - 误检：噪音被当成打断 → AI 突然停止，体验突兀
- **风险等级**：🔴 高

#### 问题 3: 流水线取消传播

```
打断检测到
    │
    ├──► 取消 LLM 生成（可能正在 streaming）
    ├──► 取消 TTS 合成（可能正在合成句子）
    ├──► 取消 Avatar 生成（可能正在渲染帧）
    ├──► 清空所有 asyncio.Queue
    ├──► 通知前端停止播放
    │
    ▼
  取消延迟：50~200ms
```

- **问题**：流水线中 ASR→LLM→TTS→Avatar 各阶段有缓冲数据，需全部丢弃
- **方案**：
  - 每个 asyncio.Task 支持 `cancel()`
  - Queue 需要 `drain()` 清空
  - 前端收到 `interrupt` 消息后立即停止播放
- **延迟开销**：取消本身 50-200ms，但需要等当前推理步骤完成
- **风险等级**：🟡 中

#### 问题 4: 全双工 ASR 资源争用

```
GPU 时间线：
  ──[Avatar渲染]──[TTS合成]──[Avatar渲染]──[TTS合成]──
                        ↑
                    ASR 也要跑！
```

- **问题**：AI 输出阶段，GPU 被 TTS + Avatar 占用，ASR 无法同时推理
- **方案**：
  - ASR 回退 CPU（增加 200-400ms 延迟）
  - ASR 和 TTS/Avatar 分时复用 GPU（增加调度复杂度）
  - 使用独立 ASR 进程 + CPU 推理
- **延迟开销**：ASR CPU 回退增加 200-400ms
- **风险等级**：🟡 中

#### 问题 5: 时序编排复杂度

全双工状态下，系统需要同时处理**三条并行流**：

```
流 1（输出）：LLM → TTS → Avatar → 用户（可能随时被打断）
流 2（输入）：麦克风 → VAD → ASR → 新问题（持续监听）
流 3（控制）：打断检测 → 取消流 1 → 启动流 2 的 LLM
```

- **问题**：三条流的同步、优先级、资源分配极其复杂
- **方案**：需要在 pipeline.py 中实现状态机
- **风险等级**：🔴 高（工程复杂度）

---

### 全双工延迟预算表

| 阶段 | 延迟 | 说明 |
|------|------|------|
| 打断检测（VAD 判定） | 200~500ms | 需要连续 200ms+ 语音活动 |
| 取消当前流水线 | 50~200ms | cancel + queue drain |
| ASR 识别（CPU） | 400~1000ms | GPU 被占用，CPU 回退 |
| LLM 首句 | 100~2000ms | 同半双工 |
| TTS + Avatar（流水线） | 400~1500ms | 同半双工 |
| **打断响应总延迟** | **1150~5200ms** | — |

**全双工结论**：
- 打断后到新响应的延迟约 **2~5 秒**，体验不如人类对话（<500ms）
- 回声消除和打断检测是最难解决的工程问题
- 全双工的工程复杂度是半双工的 **3-5 倍**

---

### 两种模式对比与建议

| 维度 | 半双工（无打断） | 全双工（有打断） |
|------|-----------------|-----------------|
| 交互方式 | 用户按住说话 / 点击录音 → 等待 → AI 回答 | 用户随时可以说话，AI 自动响应 |
| 首包延迟 | 1.5~3 秒 | 打断后 2~5 秒 |
| 工程复杂度 | 中等 | 极高（AEC + 打断检测 + 状态机） |
| 关键风险 | 延迟 > 2s 目标 | AEC 质量 + 误触发 + GPU 资源争用 |
| 用户体验 | 类似 Siri（可接受） | 类似真人对话（理想但难实现） |
| 推荐阶段 | **MVP + V1（必须）** | **V2+ 或后续迭代** |

### 推荐实施策略

**第一阶段（MVP/V1）：半双工**
- 实现 Push-to-Talk（按住说话）或 Click-to-Record（点击录音）
- 前端录音按钮控制 audio_start / audio_end
- 专注优化流水线延迟，目标 < 2 秒
- 最简实现，快速验证闭环

**第二阶段（V2+）：半双工增强**
- 加入 VAD 自动端点检测（用户停止说话自动触发）
- 减少不必要的等待，但仍为"轮流对话"模式
- 此阶段延迟优化到 < 1.5 秒

**第三阶段（后续迭代）：全双工**
- 仅在半双工稳定后考虑
- 需要解决：浏览器端 AEC、服务端打断检测、GPU 资源调度
- 可参考：Google Duplex、GPT-4o voice mode 的实现方案
- 建议作为**独立特性**单独规划，不阻塞主流程

### 延迟优化手段优先级

| 优先级 | 手段 | 节省延迟 | 实施难度 |
|--------|------|----------|----------|
| P0 | asyncio 队列流水线（LLM→TTS→Avatar 并行） | 500~1500ms | 中 |
| P0 | VAD 自动端点检测（避免手动按按钮） | 用户体验提升 | 低 |
| P1 | 句子级 TTS（不等 LLM 全部生成完） | 300~800ms | 中 |
| P1 | 模型预热（启动时 dummy 推理） | 200~500ms（首请求） | 低 |
| P2 | SenseVoice VAD 分段流式处理 | 200~400ms | 中 |
| P2 | 本地 LLM（消除云 API 延迟） | 300~1500ms | 中 |
| P3 | TTS/Avatar 使用 XPU 加速 | 200~500ms | 高（兼容性） |
| P3 | 前端音频预缓冲 + 渐入播放 | 感知延迟降低 | 中 |

---

## 工时估算

| 阶段 | 说明 | 工时 | 日历天 |
|------|------|------|--------|
| Phase 0 | 脚手架 + Git | 4h | Day 1 |
| Phase 0.5 | 配置系统 | 2h | Day 1 |
| Phase 1 | 抽象接口层 | 6h | Day 1-2 |
| Phase 2 | MVP（ASR+LLM+文字） | 16h | Day 2-4 |
| Phase 3 | V1（TTS+Avatar+视频） | 28h | Day 5-10 |
| Phase 4 | V2（人格+优化） | 40h | Day 11-20 |
| **合计** | | **96h** | **~20 工作日** |

---

## 当前进度

```
Phase 0   [ ] 项目脚手架
Phase 0.5 [ ] 配置系统
Phase 1   [ ] 抽象接口层
Phase 2   [ ] MVP - 基础语音问答
Phase 3   [ ] V1 - TTS + Avatar
Phase 4   [ ] V2 - 人格系统 + 优化
```

---

## 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-07-01 | 技术栈：SenseVoice + Fish Speech + LivePortrait + FastAPI + Vue3 | 全开源、本地部署、Intel ARC 兼容 |
| 2026-07-01 | 所有模块使用 ABC 抽象基类 | 接口分离、可替换实现 |
| 2026-07-01 | asyncio 队列流水线 | 各阶段并发、降低首包延迟 |
| 2026-07-01 | 配置统一使用 YAML | 结构清晰、易于管理 |
| 2026-07-01 | 设备管理默认 XPU 回退 CPU | Intel ARC B580 兼容性保障 |

---

## 已知问题 / 阻塞项

（暂无）
