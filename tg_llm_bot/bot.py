import logging
import json
import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from openai import AsyncOpenAI

# --- 配置部分 ---
TOKEN = os.getenv("TG_BOT_TOKEN")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://host.docker.internal:1234/v1")

# 数据文件路径
DATA_DIR = "/app/data"
PERMISSIONS_FILE = os.path.join(DATA_DIR, "permissions.json")
SYSTEM_PROMPT_FILE = os.path.join(DATA_DIR, "system_prompt.txt")

# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. If the user provides context, analyze it based on their instructions."

# 初始化 OpenAI 客户端
aclient = AsyncOpenAI(base_url=LM_STUDIO_URL, api_key="lm-studio")

# 日志设置
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 提示词管理函数 ---
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
async def chat_with_lm_studio(user_prompt):
    current_system_prompt = load_system_prompt()
    try:
        response = await aclient.chat.completions.create(
            model="local-model",
            messages=[
                {"role": "system", "content": current_system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LM Studio API Error: {e}")
        return f"⚠️ 模型调用出错: {e}"

# --- 指令处理器 ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("机器人已启动。")

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
        await update.message.reply_text(f"✅ 系统提示词已更新！\n\n{new_prompt}")
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
    
    # 获取引用内容
    if reply_obj:
        quoted_content = reply_obj.text or reply_obj.caption or "[非文本消息]"
        quoted_user = reply_obj.from_user.full_name
    
    # 构造 Prompt
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

    # 权限检查
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
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        reply = await chat_with_lm_studio(final_prompt)
        
        # --- 核心修改：智能判断回复目标 ---
        
        # 默认：回复当前发指令的用户
        target_msg_id = update.message.message_id
        
        if reply_obj:
            # 只有当引用的消息【不是】机器人自己发的时，才去回复那条引用消息
            if reply_obj.from_user.id != context.bot.id:
                target_msg_id = reply_obj.message_id
            
            # 如果 reply_obj.from_user.id == context.bot.id
            # 代码会跳过上面的 if，保持 target_msg_id 为当前用户的消息 ID
            # 从而实现“引用机器人时，回复我”的效果
            
        await update.message.reply_text(reply, reply_to_message_id=target_msg_id)

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("auth_group", auth_group))
    application.add_handler(CommandHandler("auth_user", auth_user))
    application.add_handler(CommandHandler("add_admin", add_admin_handler))
    
    application.add_handler(CommandHandler("set_system", set_system_prompt_handler))
    application.add_handler(CommandHandler("get_system", get_system_prompt_handler))
    application.add_handler(CommandHandler("reset_system", reset_system_prompt_handler))
    
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot is running...")
    application.run_polling()