import logging
import json
import os
import asyncio
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from openai import AsyncOpenAI

# --- 配置部分 ---
TOKEN = os.getenv("TG_BOT_TOKEN")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://host.docker.internal:1234/v1")

# 数据文件路径
DATA_DIR = "/app/data"
PERMISSIONS_FILE = os.path.join(DATA_DIR, "permissions.json")
SYSTEM_PROMPT_FILE = os.path.join(DATA_DIR, "system_prompt.txt")

# [新配置] 记忆设置
MAX_HISTORY_LENGTH = 10  # 记住最近 10 轮对话 (User + AI = 1轮)
HISTORY_LIMIT = MAX_HISTORY_LENGTH * 2 

# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. If the user provides context, analyze it based on their instructions."

# 初始化 OpenAI 客户端
aclient = AsyncOpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")

# [新增] 内存中的对话历史存储
# 格式: { chat_id: [ {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."} ] }
chat_histories = {}

# 日志设置
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 辅助函数 ---
def load_system_prompt():
    if not os.path.exists(SYSTEM_PROMPT_FILE):
        return DEFAULT_SYSTEM_PROMPT
    try:
        with open(SYSTEM_PROMPT_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            return content if content else DEFAULT_SYSTEM_PROMPT
    except Exception as e:
        logger.error(f"读取提示词失败: {e}")
        return DEFAULT_SYSTEM_PROMPT

def save_system_prompt(content):
    try:
        with open(SYSTEM_PROMPT_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"保存提示词失败: {e}")
        return False

# --- 权限管理类 (保持不变) ---
class PermissionManager:
    def __init__(self, filepath):
        self.filepath = filepath
        self.data = self._load()

    def _load(self):
        if not os.path.exists(self.filepath):
            return {"admin_users": [], "allowed_users": [], "allowed_groups": []}
        try:
            with open(self.filepath, 'r') as f:
                return json.load(f)
        except Exception:
            return {"admin_users": [], "allowed_users": [], "allowed_groups": []}

    def save(self):
        with open(self.filepath, 'w') as f:
            json.dump(self.data, f, indent=4)

    def is_admin(self, user_id):
        return user_id in self.data.get("admin_users", [])

    def is_user_allowed(self, user_id):
        return user_id in self.data.get("allowed_users", []) or self.is_admin(user_id)

    def is_group_allowed(self, chat_id):
        return chat_id in self.data.get("allowed_groups", [])

    def add_user(self, user_id):
        if user_id not in self.data["allowed_users"]:
            self.data["allowed_users"].append(user_id)
            self.save()
            return True
        return False
    
    def add_admin(self, user_id):
        if user_id not in self.data["admin_users"]:
            self.data["admin_users"].append(user_id)
            self.save()
            return True
        return False

    def add_group(self, chat_id):
        if chat_id not in self.data["allowed_groups"]:
            self.data["allowed_groups"].append(chat_id)
            self.save()
            return True
        return False

pm = PermissionManager(PERMISSIONS_FILE)

# --- [核心修改] LLM 调用逻辑 (支持记忆) ---
async def chat_with_lm_studio(chat_id, user_prompt):
    current_system_prompt = load_system_prompt()
    
    # 1. 获取该聊天的历史记录，如果没有则初始化为空列表
    history = chat_histories.get(chat_id, [])
    
    # 2. 构建完整的消息链：System + History + Current User Input
    messages_payload = [{"role": "system", "content": current_system_prompt}]
    messages_payload.extend(history)
    messages_payload.append({"role": "user", "content": user_prompt})

    try:
        response = await aclient.chat.completions.create(
            model="local-model",
            messages=messages_payload,
            temperature=0.7,
        )
        ai_reply = response.choices[0].message.content
        
        # 3. [新增] 更新历史记录
        # 将本次问答加入历史
        history.append({"role": "user", "content": user_prompt})
        history.append({"role": "assistant", "content": ai_reply})
        
        # 4. 裁剪历史 (防止超出 Token 限制)
        # 如果超过限制，去掉最前面的几条 (保留最近的)
        if len(history) > HISTORY_LIMIT:
            chat_histories[chat_id] = history[-HISTORY_LIMIT:]
        else:
            chat_histories[chat_id] = history
            
        return ai_reply
    except Exception as e:
        logger.error(f"LM Studio API Error: {e}")
        return f"⚠️ 模型调用出错: {e}"

# --- 指令处理器 ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("机器人已启动。\n使用 /reset 可以清除对话记忆。")

# [新增] 清除记忆指令
async def reset_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_histories:
        del chat_histories[chat_id]
        await update.message.reply_text("🧹 记忆已清除，我们重新开始吧！")
    else:
        await update.message.reply_text("✨ 当前没有记忆需要清除。")

async def add_admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id
    if not pm.is_admin(sender_id):
        await update.message.reply_text("🚫 只有管理员可以使用此命令。")
        return
    target_id = None
    target_name = "指定用户"
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
        target_name = target_user.full_name
    elif context.args:
        try:
            target_id = int(context.args[0])
            target_name = f"ID:{target_id}"
        except ValueError:
            await update.message.reply_text("⚠️ ID 格式错误。")
            return
    if target_id:
        if pm.add_admin(target_id):
            await update.message.reply_text(f"✅ 已将 {target_name} 设为管理员！")
        else:
            await update.message.reply_text(f"ℹ️ {target_name} 已经是管理员了。")
    else:
        await update.message.reply_text("⚠️ 请回复消息或输入ID。")

async def auth_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if not pm.is_admin(user_id):
        await update.message.reply_text("🚫 您没有管理员权限。")
        return
    if update.effective_chat.type in ['group', 'supergroup']:
        if pm.add_group(chat_id):
            await update.message.reply_text(f"✅ 群组已授权 (ID: {chat_id})。")
        else:
            await update.message.reply_text(f"ℹ️ 该群组已在白名单中。")
    else:
        await update.message.reply_text("⚠️ 此命令仅在群组中使用。")

async def auth_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not pm.is_admin(user_id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ 请回复一条消息来授权发送者。")
        return
    target_user = update.message.reply_to_message.from_user
    if pm.add_user(target_user.id):
        await update.message.reply_text(f"✅ 用户 {target_user.full_name} 已获授权。")
    else:
        await update.message.reply_text("ℹ️ 用户已在白名单中。")

# --- 系统提示词指令 ---
async def set_system_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pm.is_admin(update.effective_user.id):
        return
    new_prompt = " ".join(context.args).strip()
    if not new_prompt:
        await update.message.reply_text("⚠️ 请输入提示词内容。")
        return
    if save_system_prompt(new_prompt):
        # 修改提示词后，建议清除所有群的记忆，防止逻辑冲突，这里为了简单只提示
        await update.message.reply_text(f"✅ 系统提示词已更新！\n建议运行 /reset 清除旧记忆。\n\n{new_prompt}")
    else:
        await update.message.reply_text("❌ 保存失败。")

async def get_system_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pm.is_admin(update.effective_user.id):
        return
    current = load_system_prompt()
    await update.message.reply_text(f"📝 当前系统提示词:\n\n{current}")

async def reset_system_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pm.is_admin(update.effective_user.id):
        return
    if save_system_prompt(DEFAULT_SYSTEM_PROMPT):
        await update.message.reply_text("🔄 系统提示词已重置。")
    else:
        await update.message.reply_text("❌ 重置失败。")

# --- 消息处理逻辑 ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_type = update.effective_chat.type
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_input = update.message.text
    bot_username = context.bot.username

    quoted_content = ""
    reply_obj = update.message.reply_to_message
    
    if reply_obj:
        quoted_content = reply_obj.text or reply_obj.caption or "[非文本消息]"
        quoted_user = reply_obj.from_user.full_name
    
    final_prompt = user_input
    if quoted_content:
        clean_instruction = user_input.replace(f"@{bot_username}", "").strip()
        final_prompt = (
            f"请根据以下【引用内容】回答我的问题或执行指令。\n\n"
            f"【引用内容】(来自用户 {quoted_user}):\n"
            f"{quoted_content}\n\n"
            f"【我的指令】:\n"
            f"{clean_instruction}"
        )

    should_reply = False
    if chat_type == 'private':
        if pm.is_user_allowed(user_id):
            should_reply = True
        else:
            await update.message.reply_text("🚫 无权使用。")
    elif chat_type in ['group', 'supergroup']:
        is_mentioned = f"@{bot_username}" in user_input or (reply_obj and reply_obj.from_user.id == context.bot.id)
        if is_mentioned:
            if pm.is_group_allowed(chat_id):
                if not quoted_content:
                    final_prompt = user_input.replace(f"@{bot_username}", "").strip()
                should_reply = True
            else:
                await update.message.reply_text(f"🚫 群组未授权 (ID: {chat_id})。")

    if should_reply and final_prompt:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        
        # 调用带记忆的聊天函数，传入 chat_id
        reply = await chat_with_lm_studio(chat_id, final_prompt)
        
        target_msg_id = update.message.message_id
        if reply_obj and reply_obj.from_user.id != context.bot.id:
            target_msg_id = reply_obj.message_id
            
        await update.message.reply_text(reply, reply_to_message_id=target_msg_id)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("auth_group", auth_group))
    application.add_handler(CommandHandler("auth_user", auth_user))
    application.add_handler(CommandHandler("add_admin", add_admin_handler))
    
    # 新增清除记忆指令
    application.add_handler(CommandHandler("reset", reset_history_handler))
    
    application.add_handler(CommandHandler("set_system", set_system_prompt_handler))
    application.add_handler(CommandHandler("get_system", get_system_prompt_handler))
    application.add_handler(CommandHandler("reset_system", reset_system_prompt_handler))
    
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot is running with MEMORY...")
    application.run_polling()
