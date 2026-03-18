import time
import asyncio
import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# التوكن الخاص بك يا عمر
TOKEN = "8537430970:AAGHMgTYpG5U3vKHC3P8Kr28ZQyp4qOC1tU"

async def clear_webhook():
    """حذف أي Webhook قديم لضمان عمل Polling بدون تعارض"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True"
            async with session.get(url) as response:
                data = await response.json()
                print(f"🔄 تنظيف جلسات البوت: {data.get('description', 'تم بنجاح')}")
    except Exception as e:
        print(f"⚠️ خطأ أثناء تنظيف الجلسات: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية"""
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"أهلاً بك يا {user_name} في بوت اختبار BRO HOST! 🚀\n\n"
        "لقد تم تحسين سرعة البوت الآن.\n"
        "استخدم أمر /ping لاختبار السرعة الجديدة."
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر قياس سرعة الاستجابة (Ping) المحسن"""
    start_time = time.time()
    # إرسال رسالة أولية بأقل حجم بيانات ممكن
    message = await update.message.reply_text("⚡")
    end_time = time.time()
    
    # حساب الفرق بالملي ثانية
    ping_ms = round((end_time - start_time) * 1000)
    
    # تحديد الحالة بناءً على السرعة
    status = "ممتاز 🟢" if ping_ms < 300 else "جيد 🟡" if ping_ms < 600 else "بطيء 🔴"
    
    # تحديث الرسالة بالنتيجة النهائية
    await message.edit_text(
        f"📊 **نتائج اختبار السرعة (المحسن):**\n\n"
        f"🚀 سرعة الاستجابة: `{ping_ms}ms`\n"
        f"⚡ الحالة: {status}\n"
        f"🖥️ السيرفر: Render (BRO HOST)\n"
        f"✅ الحالة: مستقر وشغال 24/7"
    )

async def main():
    print("🧹 جاري تنظيف الجلسات القديمة...")
    await clear_webhook()
    
    print("🚀 جاري تشغيل بوت الاختبار المحسن...")
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('ping', ping))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    
    # إبقاء البوت يعمل
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
