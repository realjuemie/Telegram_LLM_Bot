# Telegram Local LLM Bot (LM Studio 版)

这是一个基于 Python 的 Telegram 机器人，旨在将本地运行的大语言模型（通过 LM Studio）接入 Telegram。它具备完善的权限管理系统、上下文引用对话能力以及动态人设配置功能，非常适合个人或小团队使用。

## ✨ 主要功能

* **🔌 本地模型对接**：通过 OpenAI 兼容接口连接 LM Studio，无需 API 费用，数据更隐私。
* **🛡️ 权限管理**：
    * **私聊白名单**：只有被授权的用户才能与机器人私聊。
    * **群组白名单**：机器人仅在被授权的群组内响应。
    * **管理员系统**：支持动态添加管理员，无需重启服务。
* **🧠 智能上下文**：
    * **引用回复**：在群组中回复某人的消息并 @机器人，模型会自动读取原消息作为上下文进行回答。
    * **智能回复指向**：机器人会直接回复“原消息的发送者”，保持对话层级清晰（如果引用的是机器人自己，则回复当前指令发送者）。
* **🎭 动态人设**：管理员可随时通过指令修改 System Prompt（系统提示词），让机器人扮演不同角色，且设置持久化保存。
* **🐳 Docker 部署**：一键容器化部署，环境隔离，稳定运行。

## 🛠️ 前期准备

1.  **Telegram Bot Token**：
    * 在 Telegram 搜索 `@BotFather`，发送 `/newbot` 创建机器人并获取 Token。
    * **重要设置**：在 BotFather 中对机器人发送 `/setprivacy` -> 选择你的机器人 -> `Disable`。**必须关闭隐私模式**，否则机器人无法读取群组中的引用消息。
2.  **LM Studio**：
    * 安装并启动 [LM Studio](https://lmstudio.ai/)。
    * 加载任意 LLM 模型。
    * 启动 **Local Server**，确保端口为 `1234`（默认），并开启 **CORS** 选项。
3.  **Docker 环境**：确保本机已安装 Docker 和 Docker Compose。

## 📂 目录结构

建议项目目录结构如下：

```text
tg_llm_bot/
├── data/                  # 数据挂载目录
│   ├── permissions.json   # 权限配置文件
│   └── system_prompt.txt  # 系统提示词存储
├── bot.py                 # 核心代码
├── Dockerfile             # 镜像构建文件
├── docker-compose.yml     # 容器编排文件
└── requirements.txt       # Python 依赖

```

## 🚀 部署指南

### 1. 配置文件初始化

在 `data` 目录下新建 `permissions.json`，填入你的 Telegram ID 作为初始管理员（可通过 `@userinfobot` 获取 ID）：

```json
{
  "admin_users": [123456789],
  "allowed_users": [123456789],
  "allowed_groups": []
}

```

### 2. 配置环境变量

打开 `docker-compose.yml`，修改 `TG_BOT_TOKEN`：

```yaml
version: '3.8'
services:
  tg-bot:
    build: .
    restart: unless-stopped
    environment:
      - TG_BOT_TOKEN=你的_TELEGRAM_BOT_TOKEN
      - LM_STUDIO_URL=[http://host.docker.internal:1234/v1](http://host.docker.internal:1234/v1)
    volumes:
      - ./data:/app/data
    extra_hosts:
      - "host.docker.internal:host-gateway"

```

### 3. 启动服务

在项目根目录下运行终端命令：

```bash
docker-compose up -d --build

```

查看日志确认运行正常：

```bash
docker-compose logs -f

```

---

## 📖 使用指南

### 🤖 基础指令列表

建议在 `@BotFather` 的 `Edit Commands` 中注册以下指令以便快捷调用：

| 指令 | 权限 | 描述 |
| --- | --- | --- |
| `/start` | 所有人 | 检查机器人是否在线。 |
| `/auth_group` | 👑 管理员 | **(仅群组可用)** 授权当前群组使用机器人。 |
| `/auth_user` | 👑 管理员 | **(需回复消息)** 授权被回复的用户私聊权限。 |
| `/add_admin` | 👑 管理员 | 添加新管理员。支持回复某人消息，或直接加 ID (`/add_admin 12345`)。 |
| `/set_system` | 👑 管理员 | 设置系统提示词。例：`/set_system 你是一只猫`。 |
| `/get_system` | 👑 管理员 | 查看当前的系统提示词。 |
| `/reset_system` | 👑 管理员 | 重置系统提示词为默认值。 |

### 💬 对话交互模式

#### 1. 私聊模式

* 前提：用户 ID 需在 `permissions.json` 的 `allowed_users` 中。
* 操作：直接发送消息，机器人即时回复。

#### 2. 群组模式

* 前提：
* 群组 ID 需在 `permissions.json` 的 `allowed_groups` 中（在群里发 `/auth_group` 激活）。
* **必须 @机器人** 才能触发回复（避免在群里随便插话）。



#### 3. 引用与上下文（核心功能）

* **场景**：群友 A 说了一段话，你想让机器人评价。
* **操作**：回复 A 的那条消息，并输入 `@Bot 评价一下`。
* **效果**：
1. 机器人会读取 A 的原话作为背景信息。
2. 读取你的指令“评价一下”。
3. **回复目标**：机器人会直接回复给 **群友 A**（让对话看起来更自然），而不是回复给你。



---

## ❓ 常见问题 (FAQ)

**Q: 机器人在群里不回复，也不报错？**
A: 请检查是否在 `@BotFather` 中关闭了 **Group Privacy**（Privacy mode needs to be DISABLED）。修改后如果未生效，请尝试将机器人踢出群组再重新拉入。

**Q: Docker 报错 Connection Refused？**
A: 请确保 LM Studio 的 Server 已经点击 **Start Server**。如果是 Linux 系统，可能需要检查防火墙或调整 `docker-compose.yml` 中的 `extra_hosts` 设置。

**Q: 修改了 `bot.py` 代码没生效？**
A: 修改代码文件后，必须执行构建命令来更新镜像：`docker-compose up -d --build`。

**Q: 重启 Docker 后权限会丢失吗？**
A: 不会。权限数据和系统提示词都保存在 `./data` 目录中，该目录挂载到了容器外部，数据持久化。

---

## 📝 License

MIT License

```

```
