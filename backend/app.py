"""
AI Persona Engine - FastAPI 主入口

启动方式：
    cd D:\\AI-Persona
    python -m backend.app

或在 PyCharm 中直接运行此文件。

启动后访问：
    http://localhost:8000          - 前端测试页面
    ws://localhost:8000/ws/{id}    - WebSocket 端点
    http://localhost:8000/health   - 健康检查
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

# 加载 .env 文件中的环境变量（必须在其他 import 之前）
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.config.config_loader import AppConfig
from backend.utils.logger import setup_logger
from backend.websocket_handler.pipeline import PipelineOrchestrator
from backend.websocket_handler.ws_manager import ConnectionManager

# 全局实例
config = AppConfig()
connection_manager = ConnectionManager()
pipeline = PipelineOrchestrator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。

    启动时初始化所有模块（ASR + LLM + Persona），
    关闭时释放资源。
    """
    # === 启动 ===
    setup_logger()
    logger.info("=" * 50)
    logger.info("AI Persona Engine 启动中...")
    logger.info("=" * 50)

    await pipeline.initialize()

    logger.info("=" * 50)
    logger.info("AI Persona Engine 已就绪")
    logger.info(f"  服务地址: http://{config.get('server.host')}:{config.get('server.port')}")
    logger.info("=" * 50)

    yield  # 应用运行中

    # === 关闭 ===
    await pipeline.shutdown()
    logger.info("AI Persona Engine 已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="AI Persona Engine",
    version="0.1.0",
    description="实时语音交互数字人平台",
    lifespan=lifespan,
)


# ===== WebSocket 端点 =====

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket 主端点。

    前端通过 ws://localhost:8000/ws/{session_id} 连接。
    session_id 由前端生成（如 UUID），用于标识一个对话会话。

    消息格式：所有消息都是 JSON
    - 前端 → 后端：{"type": "xxx", "data": {...}}
    - 后端 → 前端：{"type": "xxx", "data": {...}}
    """
    await connection_manager.connect(websocket, session_id)
    logger.info(f"WebSocket 连接建立: {session_id}")

    try:
        while True:
            # 接收 JSON 消息
            data = await websocket.receive_json()

            # 交给流水线处理
            await pipeline.handle_message(session_id, data, connection_manager)

    except WebSocketDisconnect:
        logger.info(f"WebSocket 断开: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket 异常: {session_id} - {e}", exc_info=True)
    finally:
        connection_manager.disconnect(session_id)
        await pipeline.cleanup_session(session_id)


# ===== HTTP 端点 =====

@app.get("/health")
async def health():
    """健康检查端点。"""
    return {
        "status": "ok",
        "version": "0.1.0",
        "active_sessions": connection_manager.active_count,
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    """返回前端 MVP 测试页面。"""
    html_path = Path(__file__).parent.parent / "frontend" / "mvp_test.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>AI Persona Engine</h1><p>前端测试页面未找到，请创建 frontend/mvp_test.html</p>"
    )


# ===== 启动入口 =====

if __name__ == "__main__":
    uvicorn.run(
        "backend.app:app",
        host=config.get("server.host", "0.0.0.0"),
        port=config.get("server.port", 8000),
        reload=config.get("server.debug", False),
        log_level="info",
    )
