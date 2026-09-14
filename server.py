#!/usr/bin/env python3
"""
SnowLuma Remote MCP Server (Streamable HTTP / SSE)
Designed for RikkaHub Android Agent & Claude MCP Protocol.
Directly communicates with SnowLuma OneBot v11 HTTP API on localhost:3000.
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

# 配置与环境变量
HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "8766"))
AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "change_me_to_a_secure_random_token")

SNOWLUMA_API_BASE = os.getenv("SNOWLUMA_API_BASE", "http://127.0.0.1:3000").rstrip("/")
SNOWLUMA_API_TOKEN = os.getenv("SNOWLUMA_API_TOKEN", "")
TIMEOUT = float(os.getenv("SNOWLUMA_TIMEOUT", "30.0"))

_http_client: httpx.AsyncClient | None = None

# 表情映射表（支持常见 QQ 表情名与系统表情 ID 互转）
# 表情映射表（打通 Linux NTQQ 官方全量 280+ 系统表情与 340+ 常用网络别名）
EMOJI_NAME_MAP: dict[str, int] = {
    "流泪": 5,
    "打call": 311,
    "变形": 312,
    "仔细分析": 314,
    "菜汪": 317,
    "崇拜": 318,
    "比心": 319,
    "庆祝": 320,
    "吃糖": 324,
    "惊吓": 325,
    "花朵脸": 337,
    "我想开了": 338,
    "舔屏": 339,
    "打招呼": 341,
    "酸Q": 342,
    "我方了": 343,
    "大怨种": 344,
    "红包多多": 345,
    "你真棒棒": 346,
    "戳一戳": 324,
    "太阳": 74,
    "月亮": 75,
    "敲敲": 351,
    "坚强": 349,
    "贴贴": 350,
    "略略略": 395,
    "篮球": 114,
    "生气": 11,
    "蛋糕": 53,
    "鞭炮": 137,
    "烟花": 333,
    "续标识": 424,
    "划龙舟": 415,
    "中龙舟": 416,
    "大龙舟": 417,
    "龙年快乐": 392,
    "新年中龙": 393,
    "新年大龙": 394,
    "求放过": 425,
    "偷感": 427,
    "玩火": 426,
    "给你一拳": 474,
    "干饭": 475,
    "不是吧": 476,
    "你懂的": 477,
    "心动": 472,
    "对的对的": 478,
    "不对不对": 479,
    "散味儿": 480,
    "学习": 481,
    "热化了": 482,
    "略": 483,
    "比爱心": 484,
    "火车": 419,
    "中火车": 420,
    "大火车": 421,
    "蛇年快乐": 429,
    "蛇身": 430,
    "蛇尾": 431,
    "微笑": 14,
    "撇嘴": 450,
    "色": 451,
    "发呆": 3,
    "得意": 4,
    "害羞": 6,
    "闭嘴": 456,
    "睡": 8,
    "大哭": 9,
    "尴尬": 10,
    "发怒": 11,
    "调皮": 12,
    "呲牙": 13,
    "惊讶": 0,
    "难过": 15,
    "酷": 16,
    "冷汗": 96,
    "抓狂": 18,
    "吐": 19,
    "偷笑": 20,
    "可爱": 21,
    "白眼": 22,
    "傲慢": 23,
    "饥饿": 24,
    "困": 25,
    "惊恐": 26,
    "流汗": 27,
    "憨笑": 28,
    "悠闲": 29,
    "奋斗": 30,
    "咒骂": 31,
    "疑问": 32,
    "嘘": 33,
    "晕": 34,
    "折磨": 35,
    "衰": 36,
    "骷髅": 37,
    "敲打": 38,
    "再见": 39,
    "擦汗": 97,
    "抠鼻": 98,
    "鼓掌": 99,
    "糗大了": 100,
    "坏笑": 101,
    "左哼哼": 102,
    "右哼哼": 103,
    "哈欠": 104,
    "鄙视": 105,
    "委屈": 106,
    "快哭了": 107,
    "阴险": 108,
    "右亲亲": 305,
    "左亲亲": 109,
    "吓": 110,
    "可怜": 111,
    "眨眼睛": 172,
    "笑哭": 182,
    "doge": 277,
    "泪奔": 173,
    "无奈": 174,
    "托腮": 212,
    "卖萌": 175,
    "斜眼笑": 178,
    "喷血": 177,
    "小纠结": 176,
    "我最美": 183,
    "脑阔疼": 262,
    "沧桑": 263,
    "捂脸": 264,
    "辣眼睛": 265,
    "哦哟": 266,
    "头秃": 267,
    "问号脸": 268,
    "暗中观察": 269,
    "emm": 270,
    "吃瓜": 271,
    "呵呵哒": 272,
    "汪汪": 277,
    "喵喵": 307,
    "牛气冲天": 306,
    "无眼笑": 281,
    "敬礼": 282,
    "狂笑": 283,
    "面无表情": 284,
    "摸鱼": 285,
    "摸锦鲤": 293,
    "魔鬼笑": 286,
    "哦": 287,
    "睁眼": 289,
    "期待": 294,
    "拜谢": 297,
    "元宝": 298,
    "牛啊": 299,
    "胖三斤": 300,
    "嫌弃": 323,
    "举牌牌": 332,
    "豹富": 336,
    "拜托": 353,
    "耶": 355,
    "666": 356,
    "尊嘟假嘟": 354,
    "咦": 352,
    "裂开": 357,
    "收到": 428,
    "虎虎生威": 334,
    "大展宏兔": 347,
    "马到成功": 470,
    "右拜年": 303,
    "左拜年": 302,
    "拿到红包": 295,
    "拥抱": 49,
    "爱心": 66,
    "玫瑰": 63,
    "凋谢": 64,
    "幽灵": 187,
    "爆筋": 146,
    "示爱": 116,
    "心碎": 67,
    "咖啡": 60,
    "羊驼": 185,
    "赞": 76,
    "OK": 124,
    "抱拳": 118,
    "握手": 78,
    "勾引": 119,
    "胜利": 79,
    "拳头": 120,
    "差劲": 121,
    "踩": 77,
    "NO": 123,
    "点赞": 76,
    "㊗": 12951,
    "祝": 12951,
    "笑翻": 129315,
    "🤣": 129315,
    "笑倒": 129315,
    "我酸了": 273,
    "猪头": 46,
    "菜刀": 112,
    "刀": 56,
    "手枪": 169,
    "茶": 171,
    "便便": 59,
    "喝彩": 144,
    "棒棒糖": 147,
    "西瓜": 89,
    "发抖": 41,
    "转圈": 125,
    "爱情": 42,
    "跳跳": 43,
    "怄火": 86,
    "挥手": 129,
    "飞吻": 85,
    "马上到": 464,
    "羞羞哒": 466,
    "摇花手": 467,
    "我吗": 458,
    "优雅": 459,
    "硬撑": 460,
    "宕机": 461,
    "无语": 462,
    "拆红包": 465,
    "出去玩": 403,
    "别说话": 402,
    "太头秃": 390,
    "太沧桑": 391,
    "太头疼": 388,
    "太赞了": 389,
    "呜呜呜": 386,
    "太气了": 385,
    "晚安": 384,
    "太好笑": 387,
    "失眠": 468,
    "坚毅": 469,
    "新年快乐": 463,
    "超级赞": 364,
    "芒狗": 366,
    "好兄弟": 362,
    "抛媚眼": 397,
    "狼狗": 396,
    "亲亲": 109,
    "狗狗笑哭": 361,
    "狗狗可怜": 363,
    "狗狗生气": 365,
    "狗狗疑问": 367,
    "emo": 382,
    "企鹅爱心": 383,
    "超级转圈": 401,
    "快乐": 400,
    "真棒": 380,
    "路过": 381,
    "企鹅流泪": 379,
    "跺脚": 376,
    "企鹅笑哭": 378,
    "嗨": 377,
    "tui": 399,
    "超级ok": 398,
    "忙": 373,
    "祝贺": 370,
    "超级鼓掌": 375,
    "奥特笑哭": 368,
    "彩虹": 369,
    "冒泡": 371,
    "气呼呼": 372,
    "波波流泪": 374,
    "摇起来": 413,
    "好运来": 405,
    "闪亮登场": 404,
    "姐是女王": 406,
    "么么哒": 410,
    "一起嗨": 411,
    "我听听": 407,
    "臭美": 408,
    "开心": 412,
    "送你花花": 409,
    "粽于等到你": 422,
    "复兴号": 423,
    "灵蛇献瑞": 432,
    "开学大吉": 488,
    "骰子": 358,
    "包剪锤": 359,
    "thumbsup": 76,
    "like": 76,
    "大拇指": 76,
    "强": 76,
    "给力": 76,
    "顶": 76,
    "好评": 76,
    "溜溜溜": 356,
    "ok": 124,
    "好的": 124,
    "没问题": 124,
    "心": 66,
    "红心": 66,
    "love": 66,
    "heart": 66,
    "蹭蹭": 350,
    "蹭一蹭": 242,
    "抱抱": 49,
    "狗头": 277,
    "菜狗": 317,
    "咸鱼": 285,
    "怨种": 344,
    "call": 311,
    "应援": 311,
    "真的假的": 354,
    "心态裂开": 357,
    "秃头": 267,
    "掉发": 267,
    "问号": 268,
    "满脸问号": 268,
    "疑惑": 268,
    "脑洞": 424,
    "狂按按钮": 424,
    "看戏": 271,
    "窥屏": 269,
    "没眼看": 265,
    "无奈捂脸": 264,
    "头疼": 262,
    "不是吧阿sir": 476,
    "干饭人": 475,
    "恰饭": 475,
    "揍你": 474,
    "出拳": 474,
    "抑郁了": 382,
    "呸": 399,
    "柠檬精": 273,
    "猫猫": 307,
    "拒绝": 322,
    "膜拜": 318,
    "放礼花": 320,
    "求求了": 353,
    "剪刀手": 355,
    "暴富": 336,
    "脸红": 6,
    "哭": 9,
    "呜呜": 9,
    "气死": 11,
    "屎": 59,
    "花": 63,
    "骷髅头": 37,
    "敲头": 38,
    "猪": 46,
    "鬼魂": 187,
    "草泥马": 185,
    "萌": 175,
    "叹气": 275,
    "欧皇": 422,
    "非酋": 423,
    "锦鲤": 432,
    "招财": 488
}


def resolve_emoji_id(emoji: str | int) -> int:
    """将表情名或 ID 解析为整型 emoji_id。"""
    if isinstance(emoji, int):
        return emoji
    stripped = str(emoji or "").strip().lstrip("/")
    if not stripped:
        return 76  # 默认点赞
    if stripped.isdigit():
        return int(stripped)
    if stripped in EMOJI_NAME_MAP:
        return EMOJI_NAME_MAP[stripped]
    lower_s = stripped.lower()
    if lower_s in EMOJI_NAME_MAP:
        return EMOJI_NAME_MAP[lower_s]
    # 单个 Unicode 字符（如单个 Emoji 🤣 或 ㊗）自动转为十进制码点
    if len(stripped) == 1:
        return ord(stripped)
    for k, v in EMOJI_NAME_MAP.items():
        if k in stripped or stripped in k:
            return v
    return 76


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
        """为指定的群消息贴表情反应（Reaction）。
        emoji 可传数字 ID（1~488）或中文表情名/网络热梗（支持 280+ 官方系统表情及 340+ 常用别名，如'点赞','摸鱼','贴贴','菜狗','狗头','尊嘟假嘟','打call','大哭','爱心','ok','便便','给你一拳','吃瓜','头秃','裂开'等）。"""
        emoji_id = resolve_emoji_id(emoji)
        return await call_snowluma("set_msg_emoji_like", {
            "message_id": int(message_id),
            "emoji_id": emoji_id,
            "set": True,
        })

    @mcp.tool()
    async def list_supported_emojis() -> dict[str, Any]:
        """获取贴表情反应（Reaction）所支持的常用表情名称与对应的 ID 字典。已扩充至全量 280+ 官方系统表情与 340+ 别名映射。"""
        return {
            "ok": True,
            "count": len(EMOJI_NAME_MAP),
            "unique_ids_count": len(set(EMOJI_NAME_MAP.values())),
            "description": "调用 set_msg_emoji_like 时可直接传其中的任意名称或数字 ID",
            "categories": {
                "认同赞美": ["点赞", "赞", "超级赞", "666", "强", "OK", "收到", "鼓掌", "崇拜"],
                "喜爱亲昵": ["贴贴", "比心", "爱心", "抱抱", "亲亲", "蹭一蹭", "么么哒"],
                "幽默搞怪": ["狗头", "菜狗", "打call", "摸鱼", "尊嘟假嘟", "喵喵", "摇起来"],
                "震惊吐槽": ["吃瓜", "问号脸", "托腮", "辣眼睛", "不是吧", "给你一拳", "裂开", "大怨种"],
                "情绪状态": ["笑哭", "坏笑", "微笑", "大哭", "流泪", "委屈", "捂脸", "emo", "头秃"],
            },
            "emojis": EMOJI_NAME_MAP,
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
