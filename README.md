# SnowLuma Remote MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![MCP Protocol](https://img.shields.io/badge/MCP-2024--11--05-purple.svg)](https://modelcontextprotocol.io)
[![SnowLuma](https://img.shields.io/badge/SnowLuma-OneBot%20v11-orange.svg)](https://github.com/SnowLuma/SnowLuma)

> **Next-Gen Remote MCP (Streamable HTTP / SSE) Gateway for SnowLuma OneBot v11.**  
> Native Claude MCP Server crafted for Android [RikkaHub](https://github.com/rikkahub/rikkahub) & Remote AI Agents.

---

## 💡 Why This Project?

The official and community MCP solutions for [SnowLuma](https://github.com/SnowLuma/SnowLuma) (such as `@snowluma/mcp`) primarily target desktop environments (Claude Desktop, Cline, DSH) using **local `stdio` process pipes**.

However, when running AI agents on mobile devices (e.g. **RikkaHub on Android**) or remote cloud containers, clients cannot spawn local processes inside your server. They require a **Remote MCP endpoint (Streamable HTTP / SSE)** over public HTTPS.

Instead of wrapping bloated subprocess gateways like `supergateway` (which suffer from process stalls, high memory consumption, and zombie pipes during mobile network switches), **SnowLuma Remote MCP** provides an ultra-lightweight, native **Python + FastMCP** server.

### Key Highlights
- 🚀 **Native Remote Architecture**: Zero subprocess wrappers, zero pipe stalls.
- 🪶 **Extremely Lightweight**: Built on Python 3.12 + official `mcp` SDK; resident memory is only **~15 MB** (vs 100MB+ for Node.js suites).
- 💬 **Tailored for AI Agents**: Flat, intuitive tooling for messaging, history retrieval, group management, and quotation replies.
- ✨ **Unique QQ Reaction Support**: First-class support for `set_msg_emoji_like` (text alias matching + full access to 390+ QQ system reactions).
- 🛡️ **Hardened Production Security**: Bearer Token authentication, DNS-rebinding protection bypass for reverse proxies, and single-port HTTPS multiplexing.
- ⚡ **Universal OneBot Pass-through**: Includes `call_onebot_action` to access all 170+ native OneBot v11 actions without writing extra code.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────┐
│  Mobile Client (RikkaHub on Android) │
└──────────────────┬───────────────────┘
                   │  HTTPS POST + Bearer Token
                   │  (Streamable HTTP: /mcp)
                   ▼
       ┌────────────────────────┐
       │   Nginx (Reverse Proxy)│
       └───────────┬────────────┘
                   │  HTTP (127.0.0.1:8766)
                   ▼
┌──────────────────────────────────────────────┐
│  SnowLuma Remote MCP Server (FastMCP ASGI)   │
│  - BearerAuthMiddleware                      │
│  - 17 Standard Agent Tools + Emoji Mapper    │
└──────────────────┬───────────────────────────┘
                   │  HTTP POST (127.0.0.1:3000)
                   ▼
┌──────────────────────────────────────────────┐
│  SnowLuma Runtime (NTQQ + OneBot v11 HTTP)   │
└──────────────────────────────────────────────┘
```

---

## 🛠️ Tool Catalog (17 Tools)

### 1. Messaging & Interaction
| Tool | Description | Highlights |
|---|---|---|
| `send_group_msg` | Send group message | Supports `at_user_id` parameter and `reply_to_message_id` |
| `send_private_msg` | Send private message | Supports plain text and CQ codes |
| `send_msg` | Universal message sender | Unified interface for both group and private |
| `delete_msg` | Recall message | Recalls a message within timeout |
| `get_msg` | Get message detail | Retrieves sender and raw content by message ID |
| `get_group_msg_history` | Read recent group history | Strips redundant fields to save LLM tokens |
| `set_msg_emoji_like` | Set message Reaction | Supports Chinese names (e.g. `点赞`, `狗头`, `贴贴`) & numeric IDs |
| `list_supported_emojis` | List reaction emojis | Quick dictionary lookup for available reactions |

### 2. Group & Profile Management
| Tool | Description |
|---|---|
| `get_login_info` | Get bot QQ number and nickname |
| `get_status` | Get SnowLuma service and online status |
| `get_friend_list` | List all friends |
| `get_group_list` | List all joined groups |
| `get_group_info` | Get group name, member count, and metadata |
| `get_group_member_list`| Get complete member list of a group |
| `set_group_ban` | Mute/unmute group member |
| `set_group_card` | Change member group card/nickname |
| `set_group_kick` | Kick member from group |

### 3. Escape Hatch
| Tool | Description |
|---|---|
| `call_onebot_action` | Direct pass-through to call any of SnowLuma's 170+ OneBot v11 actions |

---

## 🚀 Quick Start

### 1. Clone & Install
```bash
git clone https://github.com/MorphieEndless/snowluma-remote-mcp.git
cd snowluma-remote-mcp

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```
Edit `.env`:
```env
MCP_HOST=127.0.0.1
MCP_PORT=8766
MCP_AUTH_TOKEN=generate_a_secure_token_here

SNOWLUMA_API_BASE=http://127.0.0.1:3000
SNOWLUMA_API_TOKEN=your_snowluma_onebot_token_here
SNOWLUMA_TIMEOUT=30.0
```

### 3. Run
```bash
python server.py
```
Health check:
```bash
curl http://127.0.0.1:8766/health
```

---

## 🌐 Production Deployment

### Systemd Daemon
```bash
sudo cp systemd/snowluma-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now snowluma-mcp.service
```

### Nginx Reverse Proxy
Add the following locations into your HTTPS `server` block:
```nginx
# Remote MCP Endpoint
location /mcp {
    proxy_pass http://127.0.0.1:8766/mcp;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # Disable buffering for streamable transport
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding on;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

# Health Probe (Exempt from auth)
location /mcp-health {
    proxy_pass http://127.0.0.1:8766/health;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

---

## 📱 Connecting with RikkaHub (Android)

In [RikkaHub](https://github.com/rikkahub/rikkahub):
1. Navigate to **Settings → MCP → Add (+)**
2. Select **Streamable HTTP** protocol
3. Fill in:
   - **Name**: `SnowLuma`
   - **URL**: `https://your-domain.com/mcp`
   - **Authorization**: `Bearer <your_MCP_AUTH_TOKEN>`
4. Save and verify that your tools appear in your Agent's tool palette!

---

## 🎭 Reaction Emojis Cheat Sheet

When using `set_msg_emoji_like`, you can pass either the **Chinese Name** or the **QQ Face ID**:

| Name | ID | Name | ID | Name | ID |
|---|---|---|---|---|---|
| `点赞` / `赞` | 76 | `爱心` / `心` | 66 | `OK` / `好的` | 124 |
| `狗头` | 277 | `摸鱼` | 285 | `贴贴` / `蹭蹭` | 350 |
| `菜狗` | 317 | `便便` | 59 | `大哭` | 9 |
| `流泪` | 5 | `心碎` | 67 | `玫瑰` | 63 |
| `炸弹` | 11 | `骷髅` | 37 | `微笑` | 14 |
| `喵喵` | 175 | `斜眼笑` / `滑稽` | 178 | `幽灵` | 187 |
| `打call` | 311 | `大怨种` | 344 | `庆祝` | 147 |

---

## 📄 License

Distributed under the [MIT License](LICENSE).
