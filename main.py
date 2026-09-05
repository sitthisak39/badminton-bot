import os
import sys
import threading
import subprocess
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from playwright.sync_api import sync_playwright

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('O6qWwRMnsiJGRyyKOUz284rryhltNQ2bR11LMh6gi9BRxdwalfERmfP4+CfmHByFNjtOT7X3MqBI/5CPBHvbyvnWN7RPPSRY50OHPpCiMa9TueTi2VqWYtp/6V3K7je8DFTl3FT78NI0qLCOEtxGlwdB04t89/1O/w1cDnyilFU=')
LINE_CHANNEL_SECRET = os.environ.get('f343f78d02fbd5045282a9899cb5b248')
LINE_EMAIL = os.environ.get('jankong.sitthisak@gmail.com')
LINE_PASSWORD = os.environ.get('Sakoversky@32')

import os
import sys
import threading
import subprocess
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from playwright.sync_api import sync_playwright

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('O6qWwRMnsiJGRyyKOUz284rryhltNQ2bR11LMh6gi9BRxdwalfERmfP4+CfmHByFNjtOT7X3MqBI/5CPBHvbyvnWN7RPPSRY50OHPpCiMa9TueTi2VqWYtp/6V3K7je8DFTl3FT78NI0qLCOEtxGlwdB04t89/1O/w1cDnyilFU=')
LINE_CHANNEL_SECRET = os.environ.get('f343f78d02fbd5045282a9899cb5b248')
LINE_EMAIL = os.environ.get('jankong.sitthisak@gmail.com')
LINE_PASSWORD = os.environ.get('Sakoversky@32')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None

def install_playwright_browsers():
    try:
        print("🌐 Checking & Installing Playwright Chromium...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        print("✅ Chromium installed successfully!")
    except Exception as e:
        print(f"⚠️ Failed to install browser: {e}")

@app.route("/callback", methods=['POST'])
def callback():
    if not handler:
        return 'LINE Channel Secret Not Configured', 500
        
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

def async_booking_task(user_id, target_date, stadium_num, target_round):
    install_playwright_browsers()
    
    print(f"🚀 Starting Playwright Automation for User: {user_id}")
    result_msg = ""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = browser.new_context()
            page = context.new_page()

            print("🌐 Navigating to Hat Yai Booking Site...")
            page.goto("https://hatyaicity.go.th/reservesport/reserve_service/step1/3", timeout=60000)

            # พยายามเข้าสู่ระบบด้วย LINE
            line_btn = page.locator("a:has-text('LINE'), button:has-text('LINE'), .btn-line")
            if line_btn.count() > 0:
                line_btn.first.click()
                page.wait_for_timeout(2000)

            if "access.line.me" in page.url:
                print("🔑 Logging into LINE Account...")
                page.fill("input[name='tid']", LINE_EMAIL)
                page.fill("input[type='password']", LINE_PASSWORD)
                page.click("button[type='submit']")
                page.wait_for_timeout(3000)

                allow_btn = page.locator("button:has-text('Allow'), button:has-text('อนุญาต')")
                if allow_btn.count() > 0:
                    allow_btn.click()
                    page.wait_for_timeout(2000)

            print("📅 Selecting Date & Fetching Rounds...")
            page.evaluate(f"choose_date = '{target_date}';")
            page.evaluate(f"$('#choose_date').val('{target_date}');")

            # ดึงรอบเวลาผ่าน AJAX
            page.evaluate(f"""
                var url = "https://hatyaicity.go.th/reservesport/reserve_service/round_ajax";
                var param = {{
                    service_cid: '3',
                    stadium_num: '{stadium_num}',
                    choose_date: $("#choose_date").val(),
                }};
                $.post(url, param, function(data) {{
                    $('#booking_round').html(data['round']);
                    $(".btn-skip-round").hide();
                    $(".btn-choose-round").show();
                    $("#popup-round").show();
                }}, 'json');
            """)

            page.wait_for_timeout(2000)
            
            # คลิกเลือกรอบสนาม
            print(f"⏰ Selecting Round: {target_round}")
            target_locator = page.locator(f"text='{target_round}'")
            if target_locator.count() > 0:
                target_locator.first.click()
                page.evaluate("submitRound();")
                page.evaluate("submitStep1();")
                page.wait_for_timeout(2000)
                page.evaluate("submitStep2();")
                result_msg = f"🎉 บอททำรายการสำเร็จแล้ว!\nวันที่: {target_date}\nสนาม: {stadium_num}\nรอบ: {target_round}\nโปรดเข้าชำระเงินในระบบเว็บเทศบาลนครหาดใหญ่"
            else:
                result_msg = f"❌ ไม่พบรอบเวลา {target_round} หรือสนามเต็มแล้ว"

            browser.close()

        except Exception as e:
            print(f"❌ Error during booking: {str(e)}")
            result_msg = f"❌ เกิดข้อผิดพลาดขณะจอง: {str(e)}"

    # ส่งข้อความผลลัพธ์กลับไปยังแชต LINE
    if line_bot_api:
        try:
            line_bot_api.push_message(user_id, TextSendMessage(text=result_msg))
        except Exception as e:
            print(f"❌ Failed to send LINE Push Message: {e}")

@handler.add(MessageEvent, message=TextMessage) if handler else lambda x: None
def handle_message(event):
    text = event.message.text.strip()
    if text.startswith("จอง"):
        try:
            parts = text.split(" ")
            target_date = parts[1]
            stadium_num = parts[2]
            target_round = f"{parts[3]} {parts[4]} {parts[5]}"

            if line_bot_api:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"⏳ รับคำสั่งเรียบร้อยแล้ว!\n📅 วันที่: {target_date}\n🏸 สนาม: {stadium_num}\n⏰ รอบ: {target_round}\nกำลังดำเนินการจองแบบ Background Process...")
                )

            thread = threading.Thread(
                target=async_booking_task,
                args=(event.source.user_id, target_date, stadium_num, target_round)
            )
            thread.start()

        except Exception as e:
            if line_bot_api:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="❌ รูปแบบคำสั่งไม่ถูกต้อง!\nตัวอย่าง: จอง 2026-09-10 2 16:00 - 17:00 น.")
                )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
