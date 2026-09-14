#!/usr/bin/env python3
"""
SnowLuma Remote MCP Server (Streamable HTTP / SSE)
Designed for RikkaHub Android Agent & Claude MCP Protocol.
Directly communicates with SnowLuma OneBot v11 HTTP API.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

# 配置与环境变量（默认均使用通用占位符，生产环境请在 .env 或环境变量中配置）
HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "8766"))
AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "change_me_to_a_secure_random_token")

SNOWLUMA_API_BASE = os.getenv("SNOWLUMA_API_BASE", "http://127.0.0.1:3000").rstrip("/")
SNOWLUMA_API_TOKEN = os.getenv("SNOWLUMA_API_TOKEN", "")
TIMEOUT = float(os.getenv("SNOWLUMA_TIMEOUT", "30.0"))

_http_client: httpx.AsyncClient | None = None

# 表情映射表（支持常见 QQ 表情名与系统表情 ID 互转）
EMOJI_NAME_MAP: dict[str, int] = {
    # 常用高频 Reaction
    "点赞": 76,
    "赞": 76,
    "like": 76,
    "thumbsup": 76,
    "爱心": 66,
    "心": 66,
    "红心": 66,
    "love": 66,
    "heart": 66,
    "OK": 124,
    "ok": 124,
    "好的": 124,
    "狗头": 277,
    "doge": 277,
    "摸鱼": 285,
    "鱼": 285,
    "贴贴": 350,
    "蹭蹭": 350,
    "抱抱": 49,
    "菜狗": 317,
    "便便": 59,
    "屎": 59,
    "大哭": 9,
    "流泪": 5,
    "哭": 5,
    "委屈": 9,
    "心碎": 67,
    "玫瑰": 63,
    "花": 63,
    "炸弹": 11,
    "骷髅": 37,
    "骷髅头": 37,
    "微笑": 14,
    "喵喵": 175,
    "卖萌": 175,
    "斜眼笑": 178,
    "滑稽": 178,
    "幽灵": 187,
    "鬼魂": 187,
    "打call": 311,
    "打Call": 311,
    "大怨种": 344,
    "怨种": 344,
    "比心": 66,
    "吃瓜": 277,
    "牛": 114,
    "庆祝": 147,
    "脑壳疼": 260,
    "托腮": 260,
}


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        headers = {"Content-Type": "application/json"}
        if SNOWLUMA_API_TOKEN:
            headers["Authorization"] = f"Bearer {SNOWLUMA_API_TOKEN}"
        _http_client = httpx.AsyncClient(timeout=TIMEOUT, headers=headers)
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


async def call_snowluma(action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """向 SnowLuma OneBot HTTP API 发送动作请求"""
    client = await get_http_client()
    url = f"{SNOWLUMA_API_BASE}/{action.lstrip('/')}"
    try:
        resp = await client.post(url, json=params or {})
        if resp.status_code in (401, 403):
            return {"ok": False, "retcode": resp.status_code, "error": "SnowLuma OneBot API 认证失败（Token 错误）"}
        if resp.status_code >= 400:
            return {"ok": False, "retcode": resp.status_code, "error": f"HTTP {resp.status_code}: {resp.text}"}
        data = resp.json()
        retcode = data.get("retcode", 0)
        if retcode == 0:
            return {"ok": True, "data": data.get("data")}
        return {
            "ok": False,
            "retcode": retcode,
            "error": data.get("wording") or data.get("msg") or "OneBot action failed",
            "data": data.get("data"),
        }
    except Exception as exc:
        return {"ok": False, "error": f"请求 SnowLuma 异常: {type(exc).__name__} ({str(exc)})"}


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """验证请求携带的 Bearer Token，保护公网接口安全"""

    def __init__(self, app: Any, expected_token: str):
        super().__init__(app)
        self.expected_token = expected_token

    async def dispatch(self, request: Any, call_next: Any) -> Response:
        # 健康探活与首页免鉴权
        if request.url.path in ("/", "/health", "/healthz"):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "token" in request.query_params:
            token = request.query_params["token"]

        if not token or token != self.expected_token:
            return Response(
                "Unauthorized: invalid or missing Bearer token",
                status_code=401,
                media_type="text/plain",
                headers={"WWW-Authenticate": 'Bearer realm="snowluma-mcp"'},
            )

        return await call_next(request)


def build_snowluma_mcp() -> FastMCP:
    # 允许反向代理穿透与公网域名 Host
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    mcp = FastMCP(
        name="SnowLuma",
        instructions=(
            "SnowLuma QQ 机器人控制网关。支持收发群聊与私聊消息（支持@群友和引用回复）、查看历史记录、"
            "贴表情反应（Reaction）、管理群成员，以及通过 call_onebot_action 透传调用底层 170+ 个 OneBot v11 原生动作。"
        ),
        streamable_http_path="/mcp",
        transport_security=security,
    )

    # ---------------- 核心消息工具 ----------------

    @mcp.tool()
    async def send_private_msg(user_id: int, message: str, auto_escape: bool = False) -> dict[str, Any]:
        """向指定 QQ 用户发送私聊消息。支持纯文本或 CQ 码。"""
        return await call_snowluma("send_private_msg", {
            "user_id": int(user_id),
            "message": message,
            "auto_escape": bool(auto_escape),
        })

    @mcp.tool()
    async def send_group_msg(
        group_id: int,
        message: str,
        at_user_id: int | None = None,
        reply_to_message_id: int | None = None,
        auto_escape: bool = False,
    ) -> dict[str, Any]:
        """向指定 QQ 群发送群聊消息。
        - at_user_id: 可选，传入要 @ 的群友 QQ 号（如传入，将在消息开头自动添加 @提醒）。
        - reply_to_message_id: 可选，引用回复的消息 ID。
        - auto_escape: 是否纯文本转义（默认 False，支持 CQ 码）。
        """
        final_msg = message
        # 1. 自动处理 @群友
        if at_user_id and not auto_escape and f"[CQ:at,qq={at_user_id}]" not in message:
            final_msg = f"[CQ:at,qq={int(at_user_id)}] {final_msg}"
        # 2. 自动处理 引用回复
        if reply_to_message_id and not auto_escape and "[CQ:reply" not in message:
            final_msg = f"[CQ:reply,id={int(reply_to_message_id)}]{final_msg}"

        return await call_snowluma("send_group_msg", {
            "group_id": int(group_id),
            "message": final_msg,
            "auto_escape": bool(auto_escape),
        })

    @mcp.tool()
    async def send_msg(
        message: str,
        message_type: str = "group",
        group_id: int | None = None,
        user_id: int | None = None,
        auto_escape: bool = False,
    ) -> dict[str, Any]:
        """通用发送消息接口。message_type 可选 'group' 或 'private'。"""
        params: dict[str, Any] = {
            "message_type": message_type,
            "message": message,
            "auto_escape": bool(auto_escape),
        }
        if message_type == "group" and group_id:
            params["group_id"] = int(group_id)
        elif message_type == "private" and user_id:
            params["user_id"] = int(user_id)
        return await call_snowluma("send_msg", params)

    @mcp.tool()
    async def delete_msg(message_id: int) -> dict[str, Any]:
        """撤回指定的消息（需在撤回时限内且具备管理员权限或为自身发送）。"""
        return await call_snowluma("delete_msg", {"message_id": int(message_id)})

    @mcp.tool()
    async def get_msg(message_id: int) -> dict[str, Any]:
        """根据消息 ID 获取单条消息的具体内容与发送者详情。"""
        return await call_snowluma("get_msg", {"message_id": int(message_id)})

    @mcp.tool()
    async def get_group_msg_history(
        group_id: int,
        count: int = 20,
        message_seq: int | None = None,
    ) -> dict[str, Any]:
        """获取指定群的最近历史消息记录。count 默认为 20 条，便于理解上下文。"""
        params: dict[str, Any] = {"group_id": int(group_id), "count": min(max(int(count), 1), 100)}
        if message_seq is not None:
            params["message_seq"] = int(message_seq)
        res = await call_snowluma("get_group_msg_history", params)
        if not res.get("ok"):
            return res

        raw_messages = res.get("data", {}).get("messages", [])
        clean_msgs = []
        for m in raw_messages:
            clean_msgs.append({
                "message_id": m.get("message_id"),
                "sender_id": m.get("sender", {}).get("user_id"),
                "nickname": m.get("sender", {}).get("nickname") or m.get("sender", {}).get("card"),
                "time": m.get("time"),
                "raw_message": m.get("raw_message"),
            })
        return {
            "ok": True,
            "count": len(clean_msgs),
            "messages": clean_msgs,
        }

    @mcp.tool()
    async def set_msg_emoji_like(message_id: int, emoji: str | int) -> dict[str, Any]:
        """为指定的群消息贴表情反应（Reaction）。emoji 可传数字 ID 或常用名称（如'点赞','摸鱼','贴贴','菜狗','狗头','大哭','爱心','ok','便便'等）。"""
        emoji_id: int
        if isinstance(emoji, int):
            emoji_id = emoji
        elif str(emoji).isdigit():
            emoji_id = int(emoji)
        else:
            name = str(emoji).strip()
            emoji_id = EMOJI_NAME_MAP.get(name) or 76  # 默认点赞
        return await call_snowluma("set_msg_emoji_like", {
            "message_id": int(message_id),
            "emoji_id": emoji_id,
            "set": True,
        })

    @mcp.tool()
    async def list_supported_emojis() -> dict[str, Any]:
        """获取贴表情反应（Reaction）所支持的常用表情名称与对应的 ID 字典。"""
        return {
            "ok": True,
            "count": len(EMOJI_NAME_MAP),
            "emojis": EMOJI_NAME_MAP,
            "description": "调用 set_msg_emoji_like 时可直接传其中的任意名称或数字 ID",
        }

    # ---------------- 状态与关系工具 ----------------

    @mcp.tool()
    async def get_login_info() -> dict[str, Any]:
        """获取当前机器人的 QQ 号与昵称信息。"""
        return await call_snowluma("get_login_info")

    @mcp.tool()
    async def get_status() -> dict[str, Any]:
        """获取机器人当前运行状态、在线情况与连接状态。"""
        return await call_snowluma("get_status")

    @mcp.tool()
    async def get_friend_list() -> dict[str, Any]:
        """获取机器人的好友列表。"""
        return await call_snowluma("get_friend_list")

    @mcp.tool()
    async def get_group_list() -> dict[str, Any]:
        """获取机器人已加入的 QQ 群聊列表。"""
        return await call_snowluma("get_group_list")

    @mcp.tool()
    async def get_group_info(group_id: int, no_cache: bool = False) -> dict[str, Any]:
        """获取指定群的详细资料（群名、成员数、最大容量等）。"""
        return await call_snowluma("get_group_info", {
            "group_id": int(group_id),
            "no_cache": bool(no_cache),
        })

    @mcp.tool()
    async def get_group_member_list(group_id: int, no_cache: bool = False) -> dict[str, Any]:
        """获取指定群的完整成员列表。"""
        return await call_snowluma("get_group_member_list", {
            "group_id": int(group_id),
            "no_cache": bool(no_cache),
        })

    # ---------------- 群管理工具 ----------------

    @mcp.tool()
    async def set_group_ban(group_id: int, user_id: int, duration: int = 1800) -> dict[str, Any]:
        """禁言群成员。duration 为禁言秒数，传 0 表示解除禁言。"""
        return await call_snowluma("set_group_ban", {
            "group_id": int(group_id),
            "user_id": int(user_id),
            "duration": int(duration),
        })

    @mcp.tool()
    async def set_group_card(group_id: int, user_id: int, card: str) -> dict[str, Any]:
        """修改指定群成员的名片（群昵称）。"""
        return await call_snowluma("set_group_card", {
            "group_id": int(group_id),
            "user_id": int(user_id),
            "card": card,
        })

    @mcp.tool()
    async def set_group_kick(group_id: int, user_id: int, reject_add_request: bool = False) -> dict[str, Any]:
        """将成员移出群聊。"""
        return await call_snowluma("set_group_kick", {
            "group_id": int(group_id),
            "user_id": int(user_id),
            "reject_add_request": bool(reject_add_request),
        })

    # ---------------- 全能透传工具 ----------------

    @mcp.tool()
    async def call_onebot_action(action: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """全能动作透传接口：直接调用 SnowLuma 底层 170+ 个 OneBot v11 原生动作。用于执行上述预设工具未直接暴露的高级指令。"""
        return await call_snowluma(action, params or {})

    return mcp


def create_asgi_app() -> Starlette:
    """构建包含鉴权中间件与健康路由的 Starlette ASGI 实例"""
    mcp = build_snowluma_mcp()
    app = mcp.streamable_http_app()

    # 注册健康检查路由
    async def health_endpoint(request: Any) -> Response:
        status_res = await call_snowluma("get_status")
        login_res = await call_snowluma("get_login_info")
        return JSONResponse({
            "service": "snowluma-mcp",
            "version": "1.1.0",
            "status": "online",
            "snowluma_onebot": {
                "alive": status_res.get("ok", False),
                "bot_qq": login_res.get("data", {}).get("user_id"),
                "bot_nickname": login_res.get("data", {}).get("nickname"),
            },
            "protocol": "Streamable HTTP (MCP 2024-11-05)",
            "endpoint": "/mcp",
        })

    from starlette.routing import Route
    app.routes.append(Route("/health", health_endpoint, methods=["GET"]))
    app.routes.append(Route("/healthz", health_endpoint, methods=["GET"]))
    app.routes.append(Route("/", health_endpoint, methods=["GET"]))

    # 添加 Bearer 鉴权中间件
    app.add_middleware(BearerAuthMiddleware, expected_token=AUTH_TOKEN)
    return app


def main() -> None:
    import uvicorn

    print(f"[SnowLuma MCP] Starting on {HOST}:{PORT}, target OneBot: {SNOWLUMA_API_BASE}")
    asgi_app = create_asgi_app()
    uvicorn.run(asgi_app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
