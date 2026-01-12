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
TRIGGER_WORD_FILE = os.path.join(DATA_DIR, "trigger_word.txt")

# 记忆设置
MAX_HISTORY_LENGTH = 10
HISTORY_LIMIT = MAX_HISTORY_LENGTH * 2 

# 默认设置
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. If the user provides context, analyze it based on their instructions."

# 初始化 OpenAI 客户端
aclient = AsyncOpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")

# 内存中的对话历史存储
chat_histories = {}

# 日志设置
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 文件读写辅助函数 ---
def load_file_content(filepath, default=""):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            return content if content else default
    except Exception as e:
        logger.error(f"读取文件 {filepath} 失败: {e}")
        return default

def save_file_content(filepath, content):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        logger.error(f"保存文件 {filepath} 失败: {e}")
        return False

# 封装具体的加载函数
def load_system_prompt():
    return load_file_content(SYSTEM_PROMPT_FILE, DEFAULT_SYSTEM_PROMPT)

def load_trigger_word():
    return load_file_content(TRIGGER_WORD_FILE, "")

# --- 权限管理类 ---
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

# --- LLM 调用 ---
async def chat_with_lm_studio(chat_id, user_prompt):
    current_system_prompt = load_system_prompt()
    history = chat_histories.get(chat_id, [])
    
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
        
        history.append({"role": "user", "content": user_prompt})
        history.append({"role": "assistant", "content": ai_reply})
        
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
    await update.message.reply_text("机器人已启动。")

async def reset_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_histories:
        del chat_histories[chat_id]
        await update.message.reply_text("🧹 记忆已清除。")
    else:
        await update.message.reply_text("✨ 当前没有记忆。")

async def add_admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id
    if not pm.is_admin(sender_id): return
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
    if target_id and pm.add_admin(target_id):
        await update.message.reply_text(f"✅ {target_name} 已设为管理员。")
    else:
        await update.message.reply_text(f"ℹ️ 操作无效或已存在。")

async def auth_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pm.is_admin(update.effective_user.id): return
    if pm.add_group(update.effective_chat.id):
        await update.message.reply_text("✅ 群组已授权。")
    else:
        await update.message.reply_text("ℹ️ 已在白名单中。")

async def auth_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pm.is_admin(update.effective_user.id): return
    if not update.message.reply_to_message: return
    target_user = update.message.reply_to_message.from_user
    if pm.add_user(target_user.id):
        await update.message.reply_text(f"✅ {target_user.full_name} 已获授权。")

async def set_system_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pm.is_admin(update.effective_user.id): return
    new_prompt = " ".join(context.args).strip()
    if save_file_content(SYSTEM_PROMPT_FILE, new_prompt):
        await update.message.reply_text(f"✅ 系统提示词更新。\n\n{new_prompt}")

async def get_system_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pm.is_admin(update.effective_user.id): return
    await update.message.reply_text(f"📝 Prompt:\n{load_system_prompt()}")

async def reset_system_prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pm.is_admin(update.effective_user.id): return
    save_file_content(SYSTEM_PROMPT_FILE, DEFAULT_SYSTEM_PROMPT)
    await update.message.reply_text("🔄 Prompt 已重置。")

async def set_trigger_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pm.is_admin(update.effective_user.id): return
    trigger = " ".join(context.args).strip()
    if not trigger:
        await update.message.reply_text("⚠️ 请输入唤醒词。")
        return
    save_file_content(TRIGGER_WORD_FILE, trigger)
    await update.message.reply_text(f"✅ 唤醒词已设置: 「{trigger}」 (支持句中触发)")

async def get_trigger_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pm.is_admin(update.effective_user.id): return
    trigger = load_trigger_word()
    await update.message.reply_text(f"🔔 当前唤醒词: 「{trigger}」" if trigger else "🔕 未设置唤醒词。")

async def reset_trigger_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pm.is_admin(update.effective_user.id): return
    save_file_content(TRIGGER_WORD_FILE, "")
    await update.message.reply_text("🔄 唤醒词已清除。")

# --- 消息处理核心 ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return

    chat_type = update.effective_chat.type
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    user_input = update.message.text.strip()
    bot_username = context.bot.username

    quoted_content = ""
    reply_obj = update.message.reply_to_message
    if reply_obj:
        quoted_content = reply_obj.text or reply_obj.caption or "[非文本消息]"
        quoted_user = reply_obj.from_user.full_name
    
    trigger_word = load_trigger_word()
    clean_prompt = user_input
    should_reply = False

    # 1. 私聊
    if chat_type == 'private':
        if pm.is_user_allowed(user_id):
            should_reply = True
        else:
            await update.message.reply_text("🚫 无权使用。")

    # 2. 群聊
    elif chat_type in ['group', 'supergroup']:
        is_mentioned = f"@{bot_username}" in user_input
        is_reply_to_bot = (reply_obj and reply_obj.from_user.id == context.bot.id)
        
        # [核心修改]：只要包含唤醒词即可触发，不要求必须在开头
        is_triggered_by_word = False
        if trigger_word and trigger_word in user_input:
            is_triggered_by_word = True
            # [核心修改]：替换掉唤醒词，无论它在哪里
            clean_prompt = user_input.replace(trigger_word, "").strip()

        if is_mentioned or is_reply_to_bot or is_triggered_by_word:
            if pm.is_group_allowed(chat_id):
                if is_mentioned and not quoted_content:
                    clean_prompt = clean_prompt.replace(f"@{bot_username}", "").strip()
                should_reply = True
            else:
                if is_mentioned or is_reply_to_bot:
                    await update.message.reply_text(f"🚫 群组未授权 (ID: {chat_id})。")

    if should_reply and not clean_prompt and not quoted_content:
        return

    final_prompt = clean_prompt
    if quoted_content:
        final_prompt = (
            f"请根据以下【引用内容】回答我的问题或执行指令。\n\n"
            f"【引用内容】(来自用户 {quoted_user}):\n"
            f"{quoted_content}\n\n"
            f"【我的指令】:\n"
            f"{clean_prompt}"
        )

    if should_reply:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
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
    application.add_handler(CommandHandler("reset", reset_history_handler))
    
    application.add_handler(CommandHandler("set_system", set_system_prompt_handler))
    application.add_handler(CommandHandler("get_system", get_system_prompt_handler))
    application.add_handler(CommandHandler("reset_system", reset_system_prompt_handler))
    
    application.add_handler(CommandHandler("set_trigger", set_trigger_handler))
    application.add_handler(CommandHandler("get_trigger", get_trigger_handler))
    application.add_handler(CommandHandler("reset_trigger", reset_trigger_handler))
    
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot is running...")
    application.run_polling()
