```markdown
# Telegram Local LLM Bot (LM Studio 版)

这是一个功能强大的 Telegram 机器人，专为接入本地大语言模型（通过 LM Studio）而设计。它不仅实现了基础的对话功能，还具备**上下文记忆**、**自定义唤醒词**、**智能引用分析**以及完善的**权限管理系统**。

## ✨ 核心功能

* **🧠 短期记忆 (Context Awareness)**：支持多轮对话，机器人能记住最近 10 轮的聊天内容，让对话更流畅自然。
* **🗣️ 自定义唤醒词 (Trigger Word)**：除了 `@机器人`，支持设置如“Siri”、“贾维斯”等自定义唤醒词触发回复。
* **💬 智能引用回复**：在群里回复某人的消息并 @机器人，模型会读取原消息作为背景信息，并直接回复给原消息的发送者。
* **🔌 本地模型对接**：通过 OpenAI 兼容接口连接 LM Studio，数据完全掌控在本地。
* **🛡️ 权限管理系统**：
    * **白名单机制**：严格控制私聊用户和群组的访问权限。
    * **动态管理员**：通过指令直接任命新管理员。
* **🎭 动态人设**：管理员可随时修改系统提示词 (System Prompt)，让机器人扮演不同角色。
* **🐳 Docker 部署**：一键部署，数据持久化存储。

## 🛠️ 前期准备

1.  **Telegram Bot Token**：
    * 找 `@BotFather` 创建机器人。
    * **关键设置**：发送 `/setprivacy` -> 选择你的机器人 -> **Disable**。
    * *注意：必须关闭隐私模式，否则“唤醒词”和“引用检测”功能在群组中无法正常工作。*
2.  **LM Studio**：
    * 启动 Local Server，端口默认为 `1234`。
    * 确保开启 **CORS** (Cross-Origin Resource Sharing)。
3.  **Docker**：本机安装 Docker 和 Docker Compose。

## 📂 目录结构

```text
tg_llm_bot/
├── data/                  # 数据持久化目录 (自动生成/更新)
│   ├── permissions.json   # 权限名单
│   ├── system_prompt.txt  # 系统提示词
│   └── trigger_word.txt   # 自定义唤醒词
├── bot.py                 # 核心代码
├── Dockerfile             # 镜像构建文件
├── docker-compose.yml     # 容器编排配置
└── requirements.txt       # 依赖库

```

## 🚀 部署流程

### 1. 初始化配置

在 `data/permissions.json` 中填入你的 Telegram ID 作为初始管理员：

```json
{
  "admin_users": [123456789],
  "allowed_users": [123456789],
  "allowed_groups": []
}

```

### 2. 修改环境变量

编辑 `docker-compose.yml`，填入你的 Token：

```yaml
    environment:
      - TG_BOT_TOKEN=你的_BOT_TOKEN
      - LM_STUDIO_URL=[http://host.docker.internal:1234/v1](http://host.docker.internal:1234/v1)

```

### 3. 启动服务

```bash
docker-compose up -d --build

```

---

## 📖 使用指南

### 🕹️ 交互方式

该机器人支持三种交互模式：

1. **私聊模式**：直接发送消息（需在白名单内）。
2. **群组 @ 模式**：在群里发送 `@BotName 你好`。
3. **群组唤醒词模式**：
* 管理员设置唤醒词：`/set_trigger 贾维斯`
* 用户直接发送：`贾维斯 帮我写个代码`（无需 @，无需空格，自动识别）。



### 🧠 关于“记忆”与“重置”

* **记忆机制**：机器人会记住每个群组（或私聊）最近的 **10 轮对话**。
* **共享记忆**：在同一个群组内，所有成员共享一份记忆（机器人知道 A 刚才说了什么，B 接着问是能接上的）。
* **清除记忆**：如果话题聊偏了，或者机器人逻辑混乱，发送 `/reset` 即可清空当前会话的记忆，重新开始。

### 📋 指令列表 (BotFather)

建议在 `@BotFather` 中注册以下指令：

| 指令 | 权限 | 作用 |
| --- | --- | --- |
| `/start` | 所有人 | 检查机器人状态 |
| `/reset` | 所有人 | **清除对话记忆 (重开)** |
| `/auth_group` | 👑 管理员 | 授权当前群组 |
| `/auth_user` | 👑 管理员 | 授权私聊用户 (需回复对方消息) |
| `/add_admin` | 👑 管理员 | 添加管理员 (需回复，或后接ID) |
| `/set_system` | 👑 管理员 | 设置系统人设 (例: `/set_system 你是猫娘`) |
| `/get_system` | 👑 管理员 | 查看当前人设 |
| `/reset_system` | 👑 管理员 | 重置人设为默认 |
| `/set_trigger` | 👑 管理员 | 设置唤醒词 (例: `/set_trigger 小助手`) |
| `/get_trigger` | 👑 管理员 | 查看当前唤醒词 |
| `/reset_trigger` | 👑 管理员 | 关闭唤醒词功能 |

---

## ❓ 常见问题 (FAQ)

**Q1: 设置了唤醒词，但在群里叫它没反应？**
A: 请务必检查 **BotFather** 的设置。

* 进入 `@BotFather` -> `/mybots` -> Bot Settings -> **Group Privacy**。
* 确保状态是 **Turned off** (Disabled)。
* 如果设置后无效，尝试把机器人踢出群组重新拉入。

**Q2: 机器人回复别人时，为什么引用的是我的消息？**
A: 正常逻辑是：你回复 A 的消息并 @机器人，机器人会通过分析 A 的话，生成回复，并**直接 Reply 给 A**（为了保持对话连贯性）。如果是你自己直接问机器人，它会回复你。

**Q3: 重启 Docker 后记忆还在吗？**
A: 不在。为了节省资源和保持逻辑清晰，对话记忆（Context）存储在内存中，重启后会丢失。但**权限、人设、唤醒词**等配置保存在 `data/` 目录中，重启**不会丢失**。

**Q4: 我引用了机器人的话，它为什么回复我而不是回复它自己？**
A: 这是一个防嵌套优化。如果回复目标是机器人自己，它会自动改为回复“当前发送指令的用户”，避免聊天界面出现无限层级的引用楼梯。

---

## 📝 License

MIT License

```

```
