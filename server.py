#!/usr/bin/env python3
"""
SnowLuma Remote MCP Server (Streamable HTTP / SSE)
Designed for RikkaHub Android Agent & Claude MCP Protocol.
Directly communicates with SnowLuma OneBot v11 HTTP API on localhost:3000.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import re
import html
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import TextContent
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

# 模块级 logger：set_msg_emoji_like 里原本直接用了 logger.warning 却没定义，
# 一触发 warning 就 NameError，把「表情其实已经贴成功」的一次调用报成失败。
logger = logging.getLogger("snowluma-mcp")

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


ID_TO_FACE_NAME: dict[int, str] = {}
for _name, _fid in EMOJI_NAME_MAP.items():
    if _fid not in ID_TO_FACE_NAME:
        ID_TO_FACE_NAME[_fid] = _name


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


# 引用回复片段的最大字符数（超出部分截断为 …）
REPLY_SNIPPET_LENGTH = 24


# 控制字符：真实消息正文里不会有，出现了就说明这段数据是二进制/加密块
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _looks_binary(text: Any) -> bool:
    """reply 段偶尔把二进制块塞在 text 字段里，这种不能当引用内容渲染。"""
    return bool(_CONTROL_CHARS.search(str(text or "")))


def _reply_snippet(text: str, limit: int = REPLY_SNIPPET_LENGTH) -> str:
    """把被引用消息压成单行短片段，用于 [回复 昵称: 片段] 的渲染。"""
    flat = re.sub(r"\s+", " ", _CONTROL_CHARS.sub("", str(text or ""))).strip()
    if limit > 0 and len(flat) > limit:
        return flat[:limit] + "…"
    return flat


# ---------------- 媒体段（图片 / 动画表情 / 商城表情） ----------------
#
# SnowLuma（NTQQ）不会发 mface 段：QQ 的所有媒体都落在 type=image 里，靠 sub_type
# 和 emoji_id 区分。实测分布：
#   sub_type=0，无 emoji_id                  → 普通图片（summary 恒为 [图片]）
#   sub_type=0，带 emoji_id/emoji_package_id → 老式商城表情，url 在 gxh.vip.qq.com，summary 是表情名
#   sub_type=1                               → 动画表情（GIF/动图表情，summary 恒为 [动画表情]）
#   sub_type=7                               → 商城表情包，summary 就是中文名（[迷你世界] 之类）
#   sub_type=13                              → 同样标 [动画表情]，按动画表情处理
#
# 这三类在聊天里含义完全不同（普通图片是内容，动画表情是语气，商城表情带名字），
# 占位必须分开，否则模型会把"发了个表情"读成"发了张图"。
IMAGE_SUBTYPE_STICKER = (1, 13)
IMAGE_SUBTYPE_MFACE = (7,)

# summary 里这类名字没有信息量，不能当表情名用
_GENERIC_MEDIA_SUMMARIES = {"[图片]", "[动画表情]", "[表情包]", "[动图]", ""}


def _unescape_cq(value: str) -> str:
    """还原 CQ 码里的实体转义（[ ] , & 在 CQ 码里必须写成实体）。"""
    for entity, char in (("&#91;", "["), ("&#93;", "]"), ("&#44;", ","), ("&amp;", "&")):
        value = value.replace(entity, char)
    return value


def _parse_cq_params(raw: str) -> dict[str, str]:
    """把 CQ 码里 CQ:xxx,a=1,b=2 的逗号参数段拆成字典。

    summary 里会再套一层 [动画表情] 这种方括号（写成 &#91;动画表情&#93;），
    所以先按逗号切分，再还原实体，免得把值里的逗号也切掉。
    """
    params: dict[str, str] = {}
    for chunk in str(raw or "").split(","):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        params[key.strip().lower()] = _unescape_cq(value.strip())
    return params


def _media_name(summary: Any) -> str:
    """从 summary 里取表情名：只认 [名字] 这种带方括号、且不是通用占位的内容。"""
    text = str(summary or "").strip()
    if text in _GENERIC_MEDIA_SUMMARIES:
        return ""
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return "" if inner in ("图片", "动画表情", "表情包", "动图") else inner
    return ""


def classify_media(seg_type: Any, data: dict[str, Any]) -> tuple[str, str]:
    """判断一个媒体段到底是什么，返回 (类别, 占位文本)。

    类别取 "image" / "sticker" / "mface"，去重时按类别 + 身份键分组。
    """
    stype = str(seg_type or "").lower()
    try:
        sub_type: int | None = int(data.get("sub_type"))
    except (TypeError, ValueError):
        sub_type = None
    name = _media_name(data.get("summary"))

    if stype == "mface":
        # 其他 OneBot 实现会单独发 mface 段（QQ 商城表情）
        return "mface", f"[表情包:{name}]" if name else "[表情包]"
    if sub_type in IMAGE_SUBTYPE_MFACE or data.get("emoji_id") or data.get("emoji_package_id"):
        return "mface", f"[表情包:{name}]" if name else "[表情包]"
    if sub_type in IMAGE_SUBTYPE_STICKER:
        return "sticker", "[动画表情]"
    return "image", "[图片]"


def media_identity(data: dict[str, Any]) -> str:
    """同一张图/表情的稳定身份。

    QQ 段里的 file 字段就是图片字节的 MD5（大写），不用下载就能拿到，直接当去重键；
    别的实现给 file_id/md5 时一并兜住。取不到就返回空串（不做去重）。
    """
    for key in ("file", "file_id", "md5"):
        value = str(data.get(key) or "").strip()
        if value:
            return value.rsplit("/", 1)[-1].lower()
    return ""


def _append_media_ref(label: str, ref: int) -> str:
    """给重复出现的媒体占位补一个"同#N"，指向同一张图第一次出现的那条消息编号。"""
    if label.endswith("]"):
        return f"{label[:-1]} 同#{ref}]"
    return f"{label} 同#{ref}"


# CQ 码段类型 / 段数组的 type → 可读占位。主路径（段数组）和兜底路径（CQ 字符串）
# 共用同一张表，免得同一条消息在两种格式下读起来不一样。
# image / mface 走 classify_media()，这里只留作最终兜底。
SEGMENT_PLACEHOLDERS: dict[str, str] = {
    "image": "[图片]",
    "mface": "[表情包]",
    "record": "[语音]",
    "video": "[视频]",
    "json": "[卡片消息]",
    "xml": "[XML卡片]",
    "markdown": "[Markdown]",
    "poke": "[戳一戳]",
    "dice": "[骰子]",
    "rps": "[猜拳]",
    "file": "[文件]",
    "location": "[位置]",
    "contact": "[名片]",
    "music": "[音乐]",
    "share": "[链接分享]",
    "node": "[合并转发]",
}


def decode_cq_message(raw: str, reply_index: dict[str, tuple[str, str]]) -> str:
    """把 CQ 码字符串解成可读文本。

    什么时候会走到这里：message 字段本身是字符串（取决于 OneBot 实现的配置），
    或者段数组解析完正文是空的、只剩 raw_message 可救。
    段数组主路径对未知段给 [类型] 占位，这里用同一套占位表，保持两种格式口径一致。
    """
    # 注意：html.unescape 要放在最后。CQ 码把 [ ] 写成实体，提前还原的话
    # summary=&#91;动画表情&#93; 里的 ] 会把 CQ 段的正则提前截断，尾巴多出一个 ]。
    decoded = str(raw or "")

    def _face(mo: re.Match) -> str:
        raw_id = mo.group(1)
        try:
            return f"[{ID_TO_FACE_NAME.get(int(raw_id), f'表情:{raw_id}')}]"
        except Exception:
            return f"[表情:{raw_id}]"

    def _reply(mo: re.Match) -> str:
        target = reply_index.get(mo.group(1).strip())
        if target:
            return f"[回复 {target[0]}: {_reply_snippet(target[1])}]"
        return "[回复]"

    def _media(mo: re.Match) -> str:
        _, label = classify_media(mo.group(1), _parse_cq_params(mo.group(2) or ""))
        return label

    def _generic(mo: re.Match) -> str:
        seg = mo.group(1).lower()
        return SEGMENT_PLACEHOLDERS.get(seg, f"[{seg}]")

    decoded = re.sub(r'\[CQ:face,id=([0-9]+)[^\]]*\]', _face, decoded)
    decoded = re.sub(r'\[CQ:at,qq=([0-9]+)[^\]]*\]', r'@\1', decoded)
    decoded = re.sub(r'\[CQ:reply,id=([^\]]+)\]', _reply, decoded)
    # 图片 / 表情包要在通用兜底之前处理，否则会被压成 [image] / [mface]
    decoded = re.sub(r'\[CQ:(image|mface)(?:,([^\]]*))?\]', _media, decoded)
    decoded = re.sub(r'\[CQ:forward,id=([^\]]+)\]', r'[合并转发: \1]', decoded)
    # 其余 [CQ:xxx,...] 一律换占位，别把原始 CQ 码丢给模型
    decoded = re.sub(r'\[CQ:([A-Za-z_]+)(?:,[^\]]*)?\]', _generic, decoded)
    return html.unescape(decoded).strip()


def clean_message_history(raw_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """清洗 OneBot 历史消息列表，剥离冗余协议字段，智能提取纯文本、格式化时间与合并转发 ID"""
    clean_msgs = []
    # message_id -> (发送者昵称, 已清洗正文)，用于把引用回复还原成 [回复 谁: 说了什么]
    reply_index: dict[str, tuple[str, str]] = {}
    # 媒体身份键 -> (类别, 首次出现的消息编号)，用于把同一张图的重复出现标成 同#N
    seen_media: dict[str, tuple[str, int]] = {}
    for ordinal, m in enumerate(raw_messages, 1):
        forward_id = None
        text_segments = []
        msg_list = m.get("message", [])
        # QQ 发商城表情时会额外补一段文字 "[表情名]" 作为兜底显示，和段数组里的
        # 表情重复；这里用它来吃掉紧跟在后面的那段同名字面量。
        pending_dup = ""
        if isinstance(msg_list, list):
            for seg in msg_list:
                stype = seg.get("type")
                sdata = seg.get("data", {})
                if stype == "text":
                    text_value = str(sdata.get("text", ""))
                    if pending_dup and text_value.strip() == pending_dup:
                        pending_dup = ""
                        continue
                    pending_dup = ""
                    text_segments.append(text_value)
                elif stype in ("image", "mface"):
                    kind, label = classify_media(stype, sdata)
                    name = _media_name(sdata.get("summary"))
                    pending_dup = f"[{name}]" if (kind == "mface" and name) else ""
                    identity = media_identity(sdata)
                    if identity:
                        first = seen_media.get(identity)
                        if first is not None:
                            label = _append_media_ref(label, first[1])
                        else:
                            seen_media[identity] = (kind, ordinal)
                    text_segments.append(label)
                elif stype == "forward":
                    fid = sdata.get("id")
                    forward_id = fid
                    text_segments.append(f"[合并转发: {fid}]")
                elif stype == "face":
                    fid_raw = sdata.get("id")
                    try:
                        fid_int = int(fid_raw)
                        face_name = ID_TO_FACE_NAME.get(fid_int, f"表情:{fid_raw}")
                        text_segments.append(f"[{face_name}]")
                    except Exception:
                        text_segments.append(f"[表情:{fid_raw}]")
                elif stype == "reply":
                    target = reply_index.get(str(sdata.get("id") or "").strip())
                    quoted = sdata.get("text")
                    if target:
                        text_segments.append(f"[回复 {target[0]}: {_reply_snippet(target[1])}]")
                    elif quoted and not _looks_binary(quoted):
                        snip = _reply_snippet(quoted)
                        text_segments.append(f"[回复 {snip}]" if snip else "[回复]")
                    else:
                        # 被引用的消息不在本次窗口里，且 text 是二进制块：只能标个 [回复]
                        text_segments.append("[回复]")
                elif stype == "at":
                    qq = sdata.get("qq", "")
                    text_segments.append(f"@{qq}")
                elif stype == "record":
                    text_segments.append("[语音]")
                elif stype == "video":
                    text_segments.append("[视频]")
                else:
                    text_segments.append(SEGMENT_PLACEHOLDERS.get(str(stype), f"[{stype}]"))

        raw_msg = m.get("raw_message", "")
        # message 偶尔直接是 CQ 字符串而不是段数组（取决于实例配置）。这时它本身
        # 就是可解析的来源；两者都空，这一条才真的没有可读内容。
        msg_str = msg_list if isinstance(msg_list, str) else ""
        cq_source = raw_msg or msg_str
        if not forward_id and cq_source:
            match = re.search(r'\[CQ:forward,id=([^\]]+)\]', cq_source)
            if match:
                forward_id = match.group(1)

        content_str = "".join(text_segments).strip()
        if not content_str and cq_source:
            content_str = decode_cq_message(cq_source, reply_index)

        sender = m.get("sender", {})
        sender_id = m.get("user_id") or sender.get("user_id")
        nickname = sender.get("nickname") or ""
        card = sender.get("card") or ""
        sender_name = card or nickname or str(sender_id or "未知")

        ts = m.get("time")
        time_str = ""
        if ts:
            try:
                time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            except Exception:
                time_str = str(ts)

        mid = m.get("message_id")
        if mid is not None:
            reply_index[str(mid)] = (sender_name, content_str)

        entry = {
            "message_id": m.get("message_id"),
            "sender_id": sender_id,
            # 群名片优先（没有则退回昵称）：agent 眼里的"这个人现在叫什么"
            "sender_name": sender_name,
            # 原始昵称：群名片存在时它与 sender_name 不同，用于跟记忆里的名字对齐
            "nickname": nickname or card or sender_name,
            "time": ts,
            "time_str": time_str,
            "text": content_str,
        }
        if forward_id:
            entry["forward_id"] = forward_id
        # raw_message 在转发包里基本都是空串，空就不占位
        if raw_msg:
            entry["raw_message"] = raw_msg
        clean_msgs.append(entry)
    return clean_msgs


def collect_message_ids(clean_msgs: list[dict[str, Any]]) -> list[int | None]:
    """按消息顺序取出 message_id，与 rendered_text 的每一条逐一对应（取不到的位置为 null）。

    只放 ID，不放其它字段：调用方拿它去引用回复 / 撤回 / 贴表情，不必为此再拉一次 compact。
    对应关系是"第 N 条 → message_ids[N-1]"，第 N 条在渲染文本里就以 N. 开头，不需要数行。
    """
    return [m.get("message_id") for m in clean_msgs]


def build_text_payload(rendered_doc: str, clean_msgs: list[dict[str, Any]]) -> list[TextContent]:
    """text 模式的返回体：两个纯文本块，而不是一个 JSON 对象。

    为什么不能是 JSON：JSON 里的换行会被转义成字面的 \\n。客户端把工具结果当字符串渲染时
    （RikkaHub 的 ToolUI.kt 就是这么做的），整段剧本会挤成一行，人没法核对解析结果。
    返回纯文本块时换行是真换行，客户端会原样排版。

    第一块 = 带序号的可读剧本；第二块 = 只装 count 与 message_ids 的紧凑 JSON
    （不缩进、不换行，省 token；需要好看的客户端会自己格式化）。
    """
    meta = json.dumps(
        {"count": len(clean_msgs), "message_ids": collect_message_ids(clean_msgs)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return [
        TextContent(type="text", text=rendered_doc),
        TextContent(type="text", text=meta),
    ]


def format_chat_message_item(index: int, sender_name: str, time_str: str, text: str) -> str:
    """将单条聊天记录格式化为有序列表项，行首编号即这条消息在本次结果中的序号。

    编号的用处：message_ids[index - 1] 就是这一条的 message_id，不必去数渲染后的行数
    （多行消息会占好几行，数行必然数错）。人工核对解析结果时也能直接按编号指认"第几条不对"。

    多行消息的处理：
    - 首行前缀: N. [HH:MM:SS] **昵称**: 第一行
    - 后续各行按 3 个空格悬挂缩进（与 "N. " 等宽）并在行尾补 Markdown 硬换行标记，
      保证在各类 Markdown 引擎里都留在同一条列表项内部，不破坏列表结构、不突兀顶格。
    """
    t_prefix = f"[{time_str}] " if time_str else ""
    prefix = f"{index}. {t_prefix}**{sender_name}**: "

    if not text:
        return f"{prefix}"

    lines = text.split("\n")
    if not lines:
        return f"{prefix}"

    if len(lines) == 1:
        return f"{prefix}{lines[0]}"

    formatted = [f"{prefix}{lines[0]}  "]
    for i, subline in enumerate(lines[1:], 1):
        tail = "  " if i != len(lines) - 1 else ""
        formatted.append(f"   {subline}{tail}")
    return "\n".join(formatted)


def render_chat_transcript(title: str, clean_msgs: list[dict[str, Any]]) -> str:
    """将清洗后的消息列表渲染为完整的 Markdown 对话剧本（带序号，便于人核对与精确定位）。"""
    lines = []
    for index, m in enumerate(clean_msgs, 1):
        sname = m.get("sender_name") or m.get("nickname") or str(m.get("sender_id", "未知"))
        tstr = m.get("time_str", "")
        txt = m.get("text", "")
        lines.append(format_chat_message_item(index, sname, tstr, txt))

    body = "\n".join(lines)
    return f"{title}\n{body}"


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
            "历史记录里的媒体以占位呈现：[图片] 普通图片、[动画表情] 动图表情、[表情包:名字] 商城表情。"
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
        format: str = "text",
    ) -> Any:
        """获取指定群的最近历史消息记录。count 默认为 20 条，便于理解上下文。
        
        参数:
        - group_id: 目标群号
        - count: 获取条数（1~100，默认 20）
        - message_seq: 起始消息序号（用于向前翻页查询历史）
        - format: 输出格式，可选:
            - 'text' (默认): 返回两段纯文本块（不是 JSON，所以换行不会被转义成 \\n）：第一段是带序号的可读剧本（多行消息自动悬挂缩进），第二段是 {count, message_ids}，剧本第 N 条对应 message_ids[N-1]，供引用/撤回/贴表情时精确取用
            - 'compact': 结构化精简 JSON 数组，已剥离冗余协议字段、CDN 长链接与同值别名字段（不再输出 sender / content）
            - 'raw': 原始 OneBot 数据（仅供底层调试）

        媒体占位（历史记录不回传图片内容）：[图片] 普通图片；[动画表情] 动图/自制动图表情；
        [表情包:名字] QQ 商城表情（名字取自 QQ 侧，可能缺失）。同一张图在同一次结果里重复出现时，
        第 2 次起标成 [.. 同#N]，N 是它第一次出现的那条消息编号。
        """
        params: dict[str, Any] = {"group_id": int(group_id), "count": min(max(int(count), 1), 100)}
        if message_seq is not None:
            params["message_seq"] = int(message_seq)
        res = await call_snowluma("get_group_msg_history", params)
        if not res.get("ok"):
            return res

        if format == "raw":
            return res

        raw_messages = res.get("data", {}).get("messages", [])
        clean_msgs = clean_message_history(raw_messages)

        if format == "compact":
            return {
                "ok": True,
                "group_id": int(group_id),
                "count": len(clean_msgs),
                "messages": clean_msgs,
            }

        rendered_doc = render_chat_transcript(
            f"### 群聊历史记录 (群号: {group_id}，共 {len(clean_msgs)} 条消息)",
            clean_msgs,
        )
        return build_text_payload(rendered_doc, clean_msgs)

    @mcp.tool()
    async def get_friend_msg_history(
        user_id: int,
        count: int = 20,
        message_seq: int | None = None,
        format: str = "text",
    ) -> Any:
        """获取指定好友/私聊对象的最近历史消息记录。
        
        参数:
        - user_id: 目标好友 QQ 号
        - count: 获取条数（1~100，默认 20）
        - message_seq: 起始消息序号（用于向前翻页查询历史）
        - format: 输出格式，可选:
            - 'text' (默认): 返回两段纯文本块（不是 JSON，所以换行不会被转义成 \\n）：第一段是带序号的可读剧本（多行消息自动悬挂缩进），第二段是 {count, message_ids}，剧本第 N 条对应 message_ids[N-1]，供引用/撤回/贴表情时精确取用
            - 'compact': 结构化精简 JSON 数组，已剥离冗余协议字段、CDN 长链接与同值别名字段（不再输出 sender / content）
            - 'raw': 原始 OneBot 数据（仅供底层调试）

        媒体占位（历史记录不回传图片内容）：[图片] 普通图片；[动画表情] 动图/自制动图表情；
        [表情包:名字] QQ 商城表情（名字取自 QQ 侧，可能缺失）。同一张图在同一次结果里重复出现时，
        第 2 次起标成 [.. 同#N]，N 是它第一次出现的那条消息编号。
        """
        params: dict[str, Any] = {"user_id": int(user_id), "count": min(max(int(count), 1), 100)}
        if message_seq is not None:
            params["message_seq"] = int(message_seq)
        res = await call_snowluma("get_friend_msg_history", params)
        if not res.get("ok"):
            return res

        if format == "raw":
            return res

        raw_messages = res.get("data", {}).get("messages", [])
        clean_msgs = clean_message_history(raw_messages)

        if format == "compact":
            return {
                "ok": True,
                "user_id": int(user_id),
                "count": len(clean_msgs),
                "messages": clean_msgs,
            }

        rendered_doc = render_chat_transcript(
            f"### 私聊历史记录 (QQ: {user_id}，共 {len(clean_msgs)} 条消息)",
            clean_msgs,
        )
        return build_text_payload(rendered_doc, clean_msgs)

    @mcp.tool()
    async def get_forward_msg(
        forward_id: str,
        format: str = "text",
    ) -> Any:
        """获取并解析合并转发聊天记录（将臃肿的底层 OneBot 数据结构清洗转换为高信噪比对话内容）。
        
        参数:
        - forward_id: 合并转发 ID（来自 CQ 码 [CQ:forward,id=...] 或 get_friend_msg_history 中的 forward_id 字段）
        - format: 输出格式，可选:
            - 'text' (默认): 返回两段纯文本块（不是 JSON，所以换行不会被转义成 \\n）：第一段是带序号的可读剧本（多行消息自动悬挂缩进），第二段是 {count, message_ids}，剧本第 N 条对应 message_ids[N-1]，供引用/撤回/贴表情时精确取用
            - 'compact': 结构化精简 JSON 数组，已剥离冗余字段、CDN 长链接与同值别名字段（不再输出 sender / content）
            - 'raw': 原始 OneBot 数据（仅供底层调试）

        媒体占位（历史记录不回传图片内容）：[图片] 普通图片；[动画表情] 动图/自制动图表情；
        [表情包:名字] QQ 商城表情（名字取自 QQ 侧，可能缺失）。同一张图在同一次结果里重复出现时，
        第 2 次起标成 [.. 同#N]，N 是它第一次出现的那条消息编号。
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
        clean_msgs = clean_message_history(raw_messages)

        if format == "compact":
            return {
                "ok": True,
                "forward_id": clean_id,
                "count": len(clean_msgs),
                "messages": clean_msgs,
            }

        rendered_doc = render_chat_transcript(
            f"### 合并转发记录（共 {len(clean_msgs)} 条消息）",
            clean_msgs,
        )
        return build_text_payload(rendered_doc, clean_msgs)

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
            "version": "1.2.5",
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

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    print(f"[SnowLuma MCP] Starting on {HOST}:{PORT}, target OneBot: {SNOWLUMA_API_BASE}")
    asgi_app = create_asgi_app()
    uvicorn.run(asgi_app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()