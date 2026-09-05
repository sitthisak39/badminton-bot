import os
import re
import sys
import time
import traceback
import threading
import subprocess
from datetime import datetime, timedelta, timezone
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from playwright.sync_api import sync_playwright

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = 'O6qWwRMnsiJGRyyKOUz284rryhltNQ2bR11LMh6gi9BRxdwalfERmfP4+CfmHByFNjtOT7X3MqBI/5CPBHvbyvnWN7RPPSRY50OHPpCiMa9TueTi2VqWYtp/6V3K7je8DFTl3FT78NI0qLCOEtxGlwdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '57bb757a0b33c516d75e0ca9d17d3de7'
LINE_EMAIL = 'jankong.sitthisak@gmail.com'
LINE_PASSWORD = 'Sakoversky@32'
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None

# กำหนด Timezone Thailand (UTC+7)
tz_th = timezone(timedelta(hours=7))

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

    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        print(f"❌ ERROR in callback: {e}")
        traceback.print_exc()
        return 'Internal Error', 500

    return 'OK'

def scheduled_booking_task(user_id, run_time_str, target_date, stadium_num, target_round):
    if run_time_str.lower() != 'now':
        try:
            # ใช้เวลาตาม Timezone ไทย (UTC+7)
            now_th = datetime.now(tz_th)
            time_parts = list(map(int, run_time_str.split(':')))
            target_h = time_parts[0]
            target_m = time_parts[1]
            target_s = time_parts[2] if len(time_parts) > 2 else 0

            run_datetime = now_th.replace(hour=target_h, minute=target_m, second=target_s, microsecond=0)
            
            if run_datetime < now_th:
                run_datetime += timedelta(days=1)
                
            delay_seconds = (run_datetime - now_th).total_seconds()
            print(f"⏳ Scheduled booking at {run_datetime.strftime('%H:%M:%S')} (TH Time). Waiting {delay_seconds:.1f} seconds...")
            time.sleep(delay_seconds)
        except Exception as e:
            print(f"⚠️ Time parsing error ({e}), running immediately...")

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

            print("📅 Setting Date & Triggering Round Fetch...")
            page.evaluate(f"$('#choose_date').val('{target_date}');")
            page.evaluate(f"choose_date = '{target_date}';")

            page.evaluate(f"""
                var url = "https://hatyaicity.go.th/reservesport/reserve_service/round_ajax";
                var param = {{
                    service_cid: '3',
                    stadium_num: '{stadium_num}',
                    choose_date: '{target_date}',
                }};
                $.post(url, param, function(data) {{
                    $('#booking_round').html(data['round']);
                    $(".btn-skip-round").hide();
                    $(".btn-choose-round").show();
                    $("#popup-round").show();
                }}, 'json');
            """)

            page.wait_for_timeout(3000)

            clean_round_search = target_round.replace(" น.", "").strip()
            print(f"⏰ Searching for locator with text: '{clean_round_search}'")

            target_locator = page.locator(f"#booking_round :text('{clean_round_search}')")
            if target_locator.count() == 0:
                target_locator = page.locator(f":text('{clean_round_search}')")

            if target_locator.count() > 0:
                print("✅ Found round element! Clicking...")
                target_locator.first.click()
                page.wait_for_timeout(1000)

                page.evaluate("if(typeof submitRound === 'function') submitRound();")
                page.wait_for_timeout(1000)
                page.evaluate("if(typeof submitStep1 === 'function') submitStep1();")
                page.wait_for_timeout(2000)
                page.evaluate("if(typeof submitStep2 === 'function') submitStep2();")
                
                result_msg = f"🎉 บอททำรายการสำเร็จแล้ว!\nวันที่: {target_date}\nสนาม: {stadium_num}\nรอบ: {target_round}\nโปรดเข้าชำระเงินในระบบเว็บเทศบาลนครหาดใหญ่"
            else:
                print("❌ Round element not found in DOM.")
                result_msg = f"❌ ไม่พบรอบเวลา {target_round} หรือสนามเต็มแล้ว"

            browser.close()

        except Exception as e:
            print(f"❌ Error during booking: {str(e)}")
            result_msg = f"❌ เกิดข้อผิดพลาดขณะจอง: {str(e)}"

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
            pattern = r"^จอง\s+(now|\d{1,2}:\d{2}(?::\d{2})?)\s+(\d{4}-\d{2}-\d{2})\s+(\d+)\s+(.+)$"
            match = re.match(pattern, text, re.IGNORECASE)

            if match:
                run_time_str = match.group(1)
                target_date = match.group(2)
                stadium_num = match.group(3)
                target_round = match.group(4).strip()

                time_info = "ทันที" if run_time_str.lower() == 'now' else f"เวลา {run_time_str} น."

                if line_bot_api:
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=f"⏳ รับคำสั่งเรียบร้อยแล้ว!\n⏰ ตั้งเวลารันบอท: {time_info}\n📅 วันที่: {target_date}\n🏸 สนาม: {stadium_num}\n⏰ รอบสนาม: {target_round}\nบอทกำลังรอทำรายการตามเวลาที่กำหนด...")
                    )

                thread = threading.Thread(
                    target=scheduled_booking_task,
                    args=(event.source.user_id, run_time_str, target_date, stadium_num, target_round)
                )
                thread.start()
            else:
                raise ValueError("Invalid Format")

        except Exception:
            if line_bot_api:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="❌ รูปแบบคำสั่งไม่ถูกต้อง!\n\nตัวอย่างรันทันที:\nจอง now 2026-09-06 2 16:00 - 17:00 น.\n\nตัวอย่างตั้งเวลา:\nจอง 00:00:00 2026-09-06 2 16:00 - 17:00 น.")
                )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

