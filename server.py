#!/usr/bin/env python3
"""
SnowLuma Remote MCP Server (Streamable HTTP / SSE)
Designed for RikkaHub Android Agent & Claude MCP Protocol.
Directly communicates with SnowLuma OneBot v11 HTTP API on localhost:3000.
"""

from __future__ import annotations

import asyncio
import datetime
import os
import re
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
    "笑翻": 128516,
    "😄": 128516,
    "大笑": 128516,
    "🤣": 129315,
    "笑倒": 182,
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


# ---------------- 现代 Emoji 平替映射与白名单体系 ----------------
# 全局运行模式：默认 mapping (自动平替并警告)，可设为 strict / ban (严格拦截)
EMOJI_REACTION_MODE = os.getenv("EMOJI_REACTION_MODE", "mapping").lower()

# Unicode 9.0+ 高频现代 Emoji 精准语义与视觉平替映射字典 (Emoji -> (目标ID, 目标表情官方名称))
EMOJI_MODERN_FALLBACK_MAP: dict[str, tuple[int, str]] = {
    "🤣": (182, "笑哭"),
    "🥺": (111, "可怜"),
    "🤡": (286, "魔鬼笑"),
    "🥳": (320, "庆祝"),
    "🤮": (19, "吐"),
    "🤫": (33, "嘘"),
    "🫠": (482, "热化了"),
    "🤤": (339, "舔屏"),
    "🤧": (97, "擦汗"),
    "🤯": (357, "裂开"),
    "🤠": (16, "酷"),
    "🤪": (12, "调皮"),
    "🧐": (314, "仔细分析"),
    "🤬": (31, "咒骂"),
    "🥰": (472, "心动"),
    "🥵": (482, "热化了"),
    "🥶": (96, "冷汗"),
    "🥱": (104, "哈欠"),
    "🥲": (460, "硬撑"),
    "🤭": (20, "偷笑"),
    "🤨": (268, "问号脸"),
    "🤩": (318, "崇拜"),
    "🤙": (311, "打call"),
    "🤞": (12951, "㊗"),
    "🤦": (264, "捂脸"),
    "🤷": (174, "无奈"),
    "🫂": (49, "拥抱"),
    "🫶": (319, "比心"),
    "🤌": (477, "你懂的"),
    "🫡": (282, "敬礼"),
}

# 经真机实测 100% 兼容的 Unicode <= 8.0 常用字符及官方面板原生 Emoji 码点白名单
SAFE_UNICODE_CODEPOINTS = {
    9728, 9749, 9786, 9889, 9996, 10024, 10068, 10084, 127539, 127568, 127569,
    127769, 127801, 127817, 127822, 127827, 127836, 127838, 127847, 127866,
    127867, 127881, 127978, 128014, 128020, 128027, 128046, 128051, 128053,
    128054, 128055, 128056, 128064, 128070, 128074, 128076, 128077, 128078,
    128079, 128098, 128102, 128103, 128123, 128128, 128137, 128147, 128148,
    128157, 128163, 128164, 128166, 128168, 128169, 128170, 128175, 128184,
    128235, 128293, 128299, 128513, 128514, 128516, 128522, 128524, 128525,
    128526, 128527, 128530, 128531, 128532, 128536, 128538, 128540, 128541,
    128557, 128560, 128561, 128563, 128591, 128684, 129296, 129299, 129300,
    129302, 129303, 12951, 12953
}


def resolve_emoji_id(emoji: str | int, strict: bool | None = None) -> tuple[int, str | None]:
    """将表情名、别名、ID 或 Unicode Emoji 解析为安全的 emoji_id，并根据模式处理高版本 Emoji。
    
    返回: (resolved_id, warning_message_or_None)
    """
    is_strict = strict if strict is not None else (EMOJI_REACTION_MODE in ("strict", "ban"))
    
    if isinstance(emoji, int):
        return emoji, None
    
    stripped = str(emoji or "").strip().lstrip("/")
    if not stripped:
        return 76, None
    if stripped.isdigit():
        return int(stripped), None
    
    # 查找官方系统表情别名表
    if stripped in EMOJI_NAME_MAP:
        return EMOJI_NAME_MAP[stripped], None
    lower_s = stripped.lower()
    if lower_s in EMOJI_NAME_MAP:
        return EMOJI_NAME_MAP[lower_s], None
    
    # 支持带方括号的表情，如 [呲牙]
    bracket_stripped = stripped.strip("[]")
    if bracket_stripped in EMOJI_NAME_MAP:
        return EMOJI_NAME_MAP[bracket_stripped], None

    # 清洗 Unicode 变异选择符
    clean = stripped.replace("️", "")

    # 1. 检查现代高频 Emoji 平替映射表 (Unicode 9.0+)
    if clean in EMOJI_MODERN_FALLBACK_MAP:
        target_id, target_name = EMOJI_MODERN_FALLBACK_MAP[clean]
        if is_strict:
            raise ValueError(f"表情 '{clean}' (Unicode 9.0+) 不在手机 QQ 原生 Reaction 支持白名单中（会导致手机端空白方块）。当前为 strict 拦截模式，已阻止发送。")
        warning = f"表情 '{clean}' 属于手机 QQ 原生不支持的现代 Unicode Emoji（会导致空白方块），已自动平替重定向为原生表情 '{target_name}' (ID: {target_id})。建议调用方优先使用原生表情名称或 ID。"
        return target_id, warning

    # 2. 单个 Unicode 字符白名单校验 (Unicode <= 8.0)
    if len(clean) == 1:
        cp = ord(clean)
        if cp in SAFE_UNICODE_CODEPOINTS:
            return cp, None
        else:
            if is_strict:
                raise ValueError(f"表情 '{clean}' 不在手机 QQ 原生 Reaction 白名单中。当前为 strict 拦截模式，已阻止发送以防出现空白方块。")
            warning = f"表情 '{clean}' 属于未知或手机 QQ 不支持的 Unicode 表情（会导致空白方块），已自动兜底为原生表情 '点赞' (ID: 76)。建议使用受支持的官方表情。"
            return 76, warning

    # 3. 模糊匹配别名
    for k, v in EMOJI_NAME_MAP.items():
        if k in stripped or stripped in k:
            return v, None

    if is_strict:
        raise ValueError(f"无法识别表情 '{stripped}'，当前为 strict 模式已拦截。")
    return 76, f"未能识别表情 '{stripped}'，已自动兜底为原生表情 '点赞' (ID: 76)。"


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


def clean_message_history(raw_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清洗 OneBot 历史消息列表，剥离冗余字段，智能提取纯文本与合并转发 ID"""
    clean_msgs = []
    for m in raw_messages:
        forward_id = None
        text_segments = []
        msg_list = m.get("message", [])
        if isinstance(msg_list, list):
            for seg in msg_list:
                stype = seg.get("type")
                sdata = seg.get("data", {})
                if stype == "text":
                    text_segments.append(sdata.get("text", ""))
                elif stype == "image":
                    text_segments.append("[图片]")
                elif stype == "forward":
                    fid = sdata.get("id")
                    forward_id = fid
                    text_segments.append(f"[合并转发: {fid}]")
                elif stype == "face":
                    fid = sdata.get("id")
                    text_segments.append(f"[表情:{fid}]")
                elif stype == "reply":
                    text_segments.append("[回复]")
                else:
                    text_segments.append(f"[{stype}]")

        raw_msg = m.get("raw_message", "")
        if not forward_id and raw_msg:
            match = re.search(r'\[CQ:forward,id=([^\]]+)\]', raw_msg)
            if match:
                forward_id = match.group(1)

        entry = {
            "message_id": m.get("message_id"),
            "sender_id": m.get("sender", {}).get("user_id"),
            "nickname": m.get("sender", {}).get("nickname") or m.get("sender", {}).get("card"),
            "time": m.get("time"),
            "text": "".join(text_segments).strip() or raw_msg,
            "raw_message": raw_msg,
        }
        if forward_id:
            entry["forward_id"] = forward_id
        clean_msgs.append(entry)
    return clean_msgs


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
            "SnowLuma QQ 机器人控制网关。支持收发群聊与私聊消息（支持@群友和引用回复）、查看群聊与私聊历史、智能解析合并转发聊天记录、"
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
        clean_msgs = clean_message_history(raw_messages)
        return {
            "ok": True,
            "group_id": int(group_id),
            "count": len(clean_msgs),
            "messages": clean_msgs,
        }

    @mcp.tool()
    async def get_friend_msg_history(
        user_id: int,
        count: int = 20,
        message_seq: int | None = None,
    ) -> dict[str, Any]:
        """获取指定好友/私聊对象的最近历史消息记录。
        
        参数:
        - user_id: 目标好友 QQ 号
        - count: 获取条数（1~100，默认 20）
        - message_seq: 起始消息序号（用于向前翻页查询历史）
        """
        params: dict[str, Any] = {"user_id": int(user_id), "count": min(max(int(count), 1), 100)}
        if message_seq is not None:
            params["message_seq"] = int(message_seq)
        res = await call_snowluma("get_friend_msg_history", params)
        if not res.get("ok"):
            return res

        raw_messages = res.get("data", {}).get("messages", [])
        clean_msgs = clean_message_history(raw_messages)
        return {
            "ok": True,
            "user_id": int(user_id),
            "count": len(clean_msgs),
            "messages": clean_msgs,
        }

    @mcp.tool()
    async def get_forward_msg(
        forward_id: str,
        format: str = "text",
    ) -> dict[str, Any]:
        """获取并解析合并转发聊天记录（将臃肿的底层 OneBot 数据结构清洗转换为高信噪比对话内容）。
        
        参数:
        - forward_id: 合并转发 ID（来自 CQ 码 [CQ:forward,id=...] 或 get_friend_msg_history 中的 forward_id 字段）
        - format: 输出格式，可选:
            - 'text' (默认): 生成易读的 Markdown 对话剧本，极大节省 Token 且模型可直接阅读
            - 'compact': 结构化精简 JSON 数组，已剥离所有冗余字段与 CDN 长链接
            - 'raw': 原始 OneBot 数据（仅供底层调试）
        """
        clean_id = str(forward_id).strip()
        if clean_id.startswith("[CQ:forward,id=") and clean_id.endswith("]"):
            clean_id = clean_id[len("[CQ:forward,id="):-1]

        res = await call_snowluma("get_forward_msg", {"id": clean_id})
        if not res.get("ok"):
            return res

        if format == "raw":
            return res

        raw_messages = res.get("data", {}).get("messages", [])
        
        # 建立 Face ID -> 中文表情名称映射
        id_to_face = {}
        for name, fid in EMOJI_NAME_MAP.items():
            if fid not in id_to_face:
                id_to_face[fid] = name

        parsed_msgs = []
        text_lines = []

        for idx, m in enumerate(raw_messages, 1):
            sender = m.get("sender", {})
            sender_name = sender.get("card") or sender.get("nickname") or str(m.get("user_id", "未知"))
            sender_id = m.get("user_id") or sender.get("user_id")
            
            ts = m.get("time")
            time_str = ""
            if ts:
                try:
                    time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                except Exception:
                    time_str = str(ts)

            parts = []
            msg_elements = m.get("message", [])
            if isinstance(msg_elements, list):
                for elem in msg_elements:
                    etype = elem.get("type")
                    edata = elem.get("data", {})
                    if etype == "text":
                        parts.append(edata.get("text", ""))
                    elif etype == "image":
                        parts.append("[图片]")
                    elif etype == "face":
                        fid_raw = edata.get("id")
                        try:
                            fid_int = int(fid_raw)
                            parts.append(f"[{id_to_face.get(fid_int, f'表情:{fid_raw}')}]")
                        except Exception:
                            parts.append(f"[表情:{fid_raw}]")
                    elif etype == "reply":
                        parts.append("[回复]")
                    elif etype == "forward":
                        parts.append(f"[嵌套转发: {edata.get('id', '')}]")
                    elif etype == "at":
                        parts.append(f"@{edata.get('qq', '')}")
                    else:
                        parts.append(f"[{etype}]")

            content = "".join(parts).strip() or m.get("raw_message", "")
            
            parsed_msgs.append({
                "index": idx,
                "sender": sender_name,
                "user_id": sender_id,
                "time": time_str,
                "content": content,
            })
            
            t_prefix = f"[{time_str}] " if time_str else ""
            text_lines.append(f"- {t_prefix}**{sender_name}**: {content}")

        if format == "compact":
            return {
                "ok": True,
                "forward_id": clean_id,
                "count": len(parsed_msgs),
                "messages": parsed_msgs,
            }

        lines_joined = "\n".join(text_lines)
        rendered_doc = f"### 合并转发记录（共 {len(parsed_msgs)} 条消息）\n{lines_joined}"
        return {
            "ok": True,
            "forward_id": clean_id,
            "count": len(parsed_msgs),
            "rendered_text": rendered_doc,
        }


    @mcp.tool()
    async def set_msg_emoji_like(
        message_id: int,
        emoji: str | int,
        strict: bool | None = None,
    ) -> dict[str, Any]:
        """为指定的群消息贴表情反应（Reaction）。
        
        参数:
        - message_id: 目标消息 ID
        - emoji: 表情名称、网络热梗、官方系统表情 ID（0~488）或常用 Unicode Emoji。
        - strict: 可选，是否启用严格拦截模式。若为 True，当传入手机 QQ 原生不支持的高版本 Emoji（Unicode >= 9.0，会导致空白方块）时将直接拒绝拦截；默认为 None（使用全局配置 EMOJI_REACTION_MODE，默认进行智能平替重定向并返回 warning 警告）。
        """
        try:
            emoji_id, warning = resolve_emoji_id(emoji, strict=strict)
        except ValueError as e:
            return {
                "ok": False,
                "error": str(e),
                "data": None,
            }

        res = await call_snowluma("set_msg_emoji_like", {
            "message_id": int(message_id),
            "emoji_id": emoji_id,
            "set": True,
        })

        if res.get("ok"):
            res["applied_emoji_id"] = emoji_id
            if warning:
                res["warning"] = warning
                logger.warning(f"[EmojiReaction] {warning}")
        return res

    @mcp.tool()
    async def list_supported_emojis() -> dict[str, Any]:
        """获取贴表情反应（Reaction）所支持的表情清单、高频现代 Emoji 平替映射表与当前运行模式。"""
        return {
            "ok": True,
            "current_mode": EMOJI_REACTION_MODE,
            "mode_description": "当前模式：'mapping' (默认自动平替并返回 warning 警告) / 'strict' (严格拦截)",
            "count": len(EMOJI_NAME_MAP),
            "unique_ids_count": len(set(EMOJI_NAME_MAP.values())),
            "modern_emoji_fallbacks": {k: {"target_id": v[0], "target_name": v[1]} for k, v in EMOJI_MODERN_FALLBACK_MAP.items()},
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
