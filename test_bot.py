import time
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# التوكن الخاص بك يا عمر
TOKEN = "8537430970:AAGHMgTYpG5U3vKHC3P8Kr28ZQyp4qOC1tU"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية"""
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"أهلاً بك يا {user_name} في بوت اختبار BRO HOST! 🚀\n\n"
        "لقد تم تشغيل هذا البوت بنجاح على سيرفرك.\n"
        "استخدم أمر /ping لاختبار سرعة الاستجابة."
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر قياس سرعة الاستجابة (Ping)"""
    start_time = time.time()
    # إرسال رسالة أولية
    message = await update.message.reply_text("⚡ جاري قياس السرعة...")
    end_time = time.time()
    
    # حساب الفرق بالملي ثانية
    ping_ms = round((end_time - start_time) * 1000)
    
    # تحديث الرسالة بالنتيجة
    await message.edit_text(
        f"📊 **نتائج اختبار السرعة:**\n\n"
        f"🚀 سرعة الاستجابة: `{ping_ms}ms`\n"
        f"🖥️ السيرفر: Render (BRO HOST)\n"
        f"✅ الحالة: مستقر وشغال 24/7"
    )

if __name__ == '__main__':
    print("🚀 جاري تشغيل بوت الاختبار...")
    application = ApplicationBuilder().token(TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    ping_handler = CommandHandler('ping', ping)
    
    application.add_handler(start_handler)
    application.add_handler(ping_handler)
    
    application.run_polling()
