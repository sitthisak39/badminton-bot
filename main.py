import os
import time
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# Config ค่าต่างๆ (นำค่าจาก LINE Developers มาใส่ที่นี่)
LINE_CHANNEL_ACCESS_TOKEN = 'O6qWwRMnsiJGRyyKOUz284rryhltNQ2bR11LMh6gi9BRxdwalfERmfP4+CfmHByFNjtOT7X3MqBI/5CPBHvbyvnWN7RPPSRY50OHPpCiMa9TueTi2VqWYtp/6V3K7je8DFTl3FT78NI0qLCOEtxGlwdB04t89/1O/w1cDnyilFU='  
LINE_CHANNEL_SECRET = 'f343f78d02fbd5045282a9899cb5b248'

# บัญชี LINE ที่ใช้เข้าสู่ระบบเว็บจองสนาม
LINE_EMAIL = 'jankong.sitthisak@gmail.com'
LINE_PASSWORD = 'Sakoversky@32'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

def run_playwright_line_login(target_date, stadium_num, target_round, target_time):
    """ฟังก์ชันล็อกอินผ่าน LINE และทำการจอง"""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, # รันเบื้องหลังบน Cloud
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context()
        page = context.new_page()

        print("🌐 กำลังเข้าสู่หน้าเว็บจองสนาม...")
        page.goto("https://hatyaicity.go.th/reservesport/reserve_service/step1/3")

        # 1. คลิกปุ่ม "เข้าสู่ระบบด้วย LINE" บนหน้าเว็บ
        try:
            # ค้นหาและกดปุ่ม LINE Login บนเว็บ
            line_login_btn = page.locator("a:has-text('LINE'), button:has-text('LINE'), .btn-line")
            if line_login_btn.count() > 0:
                line_login_btn.first.click()
                page.wait_for_timeout(2000)

            # 2. กรอก Email และ Password ของ LINE ในหน้า LINE Auth
            if "access.line.me" in page.url:
                page.fill("input[name='tid']", LINE_EMAIL)
                page.fill("input[value='']", LINE_PASSWORD) # ช่องรหัสผ่าน
                page.click("button[type='submit']")
                page.wait_for_timeout(3000)

                # หากมีปุ่มกดกดยินยอม (Allow/Authorize)
                allow_btn = page.locator("button:has-text('Allow'), button:has-text('อนุญาต')")
                if allow_btn.count() > 0:
                    allow_btn.click()
                    page.wait_for_timeout(2000)
        except Exception as e:
            print(f"⚠️ เกิดข้อผิดพลาดในการล็อกอิน LINE: {e}")

        # 3. ตั้งเวลารอให้ถึงเวลาจองจริง
        if target_time:
            h, m, s = map(int, target_time.split(':'))
            while True:
                now = datetime.now()
                if now.hour == h and now.minute == m and now.second == s:
                    break
                time.sleep(0.01)

        # 4. ดำเนินการกดจองสนาม
        try:
            page.evaluate(f"choose_date = '{target_date}';")
            page.evaluate(f"$('#choose_date').val('{target_date}');")

            # ดึงรอบสนาม
            max_retries = 30
            for i in range(max_retries):
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

                try:
                    target_locator = page.locator(f"input[name='radio_check'] >> xpath=../.. >> text='{target_round}'")
                    target_locator.wait_for(state="visible", timeout=500)
                    target_locator.click()
                    break
                except:
                    time.sleep(0.2)

            page.evaluate("submitRound();")
            page.evaluate("submitStep1();")
            page.wait_for_selector("button[onclick='submitStep2();']", timeout=5000)
            page.evaluate("submitStep2();")
            
            browser.close()
            return "🎉 บอททำรายการสำเร็จแล้ว! โปรดเข้าไปชำระเงินในระบบ"
        except Exception as e:
            browser.close()
            return f"❌ เกิดข้อผิดพลาดขณะจอง: {str(e)}"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    
    # รูปแบบคำสั่งในไลน์: จอง [วันที่] [สนาม] [รอบเวลา] [เวลาเริ่มยิง]
    # ตัวอย่าง: จอง 2026-06-16 2 16:00 - 17:00 น. 00:00:00
    if text.startswith("จอง"):
        try:
            parts = text.split(" ")
            target_date = parts[1]        # 2026-06-16
            stadium_num = parts[2]        # 2
            target_round = f"{parts[3]} {parts[4]} {parts[5]}" # 16:00 - 17:00 น.
            target_time = parts[6] if len(parts) > 6 else None # 00:00:00

            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"⏳ รับคำสั่งจองแล้ว!\n📅 วันที่: {target_date}\n🏸 สนาม: {stadium_num}\n⏰ รอบ: {target_round}\nบอทกำลังเตรียมการล็อกอินผ่าน LINE...")
            )

            # รันกระบวนการจอง
            result_msg = run_playwright_line_login(target_date, stadium_num, target_round, target_time)
            
            # ส่งข้อความแจ้งผลกลับไปในไลน์ผู้ใช้
            line_bot_api.push_message(
                event.source.user_id,
                TextSendMessage(text=result_msg)
            )

        except Exception as e:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"❌ รูปแบบคำสั่งไม่ถูกต้อง! กรุณาใช้รูปแบบ:\nจอง [YYYY-MM-DD] [เลขสนาม] [รอบเวลา] [เวลาเริ่มจอง]\n\nตัวอย่าง:\nจอง 2026-06-16 2 16:00 - 17:00 น. 00:00:00")
            )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
