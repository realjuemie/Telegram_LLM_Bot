# Telegram Local LLM Bot (Vision Edition)

🚀 **你的本地大模型智能助手**

这是一个功能强大的 Telegram 机器人，专为接入本地运行的大语言模型（通过 **LM Studio**）而设计。
它不仅支持流畅的文本对话，更具备**视觉识别能力**，可以“看懂”你发送或引用的图片，并支持完善的权限管理和动态人设配置。

## ✨ 核心亮点

### 👁️ 多模态视觉支持 (Vision)
* **直接识图**：发送一张图片并附上文字（如“这张图里有什么？”），机器人即刻分析。
* **引用识图**：**这是杀手级功能！** 在群里看到别人发的图，直接**回复**那张图并 @机器人（或说唤醒词），机器人会自动抓取原图进行回答，且**智能回复给原图发送者**。

### 🧠 智能对话系统
* **上下文记忆**：支持多轮对话（记忆最近 10 轮），聊天不费劲。
* **灵活唤醒**：
    * **@提及**：`@BotName 帮我写个代码`
    * **引用回复**：回复机器人的消息继续追问。
    * **自定义唤醒词**：设置“小助手”为唤醒词，句子**任意位置**包含该词即可触发（例如：“小助手帮我看下这个”、“天气怎么样啊小助手”）。

### 🛡️ 企业级权限管理
* **白名单机制**：只有授权的用户和群组才能使用，防止资源被滥用。
* **动态管理**：无需重启，通过指令即可添加管理员、授权群组。

### ⚙️ 易用性设计
* **纯文本输出**：避免 Markdown 解析错误导致的“消息发送失败”，稳定第一。
* **Docker 部署**：一键启动，数据持久化，环境隔离。

---

## 🛠️ 前期准备

1.  **Telegram Bot**：
    * 找 `@BotFather` 创建机器人。
    * **关键设置**：发送 `/setprivacy` ➜ 选择你的机器人 ➜ **Disable** (关闭隐私模式)。
    * *注意：必须关闭隐私模式，否则“唤醒词”和“引用检测”在群组无法生效。*
2.  **LM Studio**：
    * 下载并安装 [LM Studio](https://lmstudio.ai/)。
    * **模型选择**：
        * **聊天**：推荐 Llama 3, Mistral 等。
        * **识图**：必须加载支持 Vision 的模型（如 `Llava`, `Qwen-VL`, `BakLLaVA`）。
    * **启动服务**：Start Local Server，端口默认为 `1234`。
3.  **环境**：安装 Docker 和 Docker Compose。

---

## 📂 目录结构

```text
tg_llm_bot/
├── data/                  # 数据目录 (自动生成/持久化)
│   ├── permissions.json   # 权限名单
│   ├── system_prompt.txt  # 系统提示词 (人设)
│   └── trigger_word.txt   # 自定义唤醒词
├── bot.py                 # 核心源码
├── Dockerfile             # 构建文件
├── docker-compose.yml     # 编排文件
└── requirements.txt       # 依赖库

```

---

## 🚀 部署指南

### 1. 配置管理员

在 `data/permissions.json` 中填入你的 Telegram ID（可通过 `@userinfobot` 获取）：

```json
{
  "admin_users": [123456789],
  "allowed_users": [123456789],
  "allowed_groups": []
}

```

### 2. 配置 Token

编辑 `docker-compose.yml`：

```yaml
    environment:
      - TG_BOT_TOKEN=你的_TELEGRAM_BOT_TOKEN
      - LM_STUDIO_URL=[http://host.docker.internal:1234/v1](http://host.docker.internal:1234/v1)

```

### 3. 一键启动

```bash
docker-compose up -d --build

```

*更新代码后，也请运行此命令重构镜像。*

---

## 📖 使用手册

### 📸 视觉功能怎么用？

| 场景 | 操作方法 |
| --- | --- |
| **私聊发图** | 直接发送图片，在“添加说明”中输入问题。 |
| **群聊发图** | 发送图片，并在说明中带上唤醒词或 @机器人。 |
| **引用问图** | **(推荐)** 长按别人的图片 -> 点击回复 -> 输入“@Bot 这图里有几个人？” -> 机器人会自动下载原图分析。 |

### 🗣️ 自定义唤醒词

管理员发送 `/set_trigger 贾维斯`。
设置后：

* “**贾维斯** 给我讲个笑话” -> ✅ 触发
* “这道题怎么做 **贾维斯**” -> ✅ 触发
* 无需空格，无需 @，机器人会自动提取指令。

### 🎮 指令列表 (BotFather)

建议发送给 `@BotFather` 进行菜单配置：

```text
start - 检查状态
reset - 清除记忆 (重开)
auth_group - 👑 授权当前群组
auth_user - 👑 授权私聊用户(需回复)
add_admin - 👑 添加管理员
set_system - 👑 设置人设 (例: /set_system 你是猫娘)
get_system - 👑 查看人设
reset_system - 👑 重置人设
set_trigger - 👑 设置唤醒词 (例: /set_trigger 小助手)
get_trigger - 👑 查看唤醒词
reset_trigger - 👑 清除唤醒词

```

---

## ❓ 常见问题 (FAQ)

**Q: 发送图片后机器人提示“当前模型不支持视觉输入”？**
A: 这是因为 LM Studio 当前加载的是纯文本模型（如 Llama 3）。请去 LM Studio 搜索并加载 `Llava` 或 `Qwen-VL` 等带有 "Vision" 标签的模型。

**Q: 群里叫它不理我？**
A: 1. 检查群组是否已授权 (`/auth_group`)。 2. 检查 BotFather 的 Privacy Mode 是否已关闭 (`Disable`)。

**Q: 为什么它回复了图片发送者，而不是回复我？**
A: 这是特意设计的。当你引用别人的消息提问时，机器人认为你在针对那条消息进行讨论，为了保持上下文连贯，它会“指哪打哪”，直接回复给被引用的原消息。

**Q: 重启 Docker 会丢失数据吗？**
A: **权限、人设、唤醒词**不会丢失（保存在 `data/`）。**对话记忆**会重置（保存在内存中），这有助于清理长时间运行积累的上下文垃圾。

---

## 📝 License

MIT License

```

```
