import os
import re
import sys
import time
import traceback
import threading
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = 'O6qWwRMnsiJGRyyKOUz284rryhltNQ2bR11LMh6gi9BRxdwalfERmfP4+CfmHByFNjtOT7X3MqBI/5CPBHvbyvnWN7RPPSRY50OHPpCiMa9TueTi2VqWYtp/6V3K7je8DFTl3FT78NI0qLCOEtxGlwdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '57bb757a0b33c516d75e0ca9d17d3de7'
LINE_EMAIL = 'jankong.sitthisak@gmail.com'
LINE_PASSWORD = 'Sakoversky@32'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None

tz_th = timezone(timedelta(hours=7))

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

def direct_api_booking(target_date, stadium_num, target_round):
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest'
    })

    base_url = "https://hatyaicity.go.th/reservesport/reserve_service/step1/3"
    print("🌐 Getting Session Cookies...")
    session.get(base_url, timeout=15)

    round_url = "https://hatyaicity.go.th/reservesport/reserve_service/round_ajax"
    payload = {
        'service_cid': '3',
        'stadium_num': str(stadium_num),
        'choose_date': str(target_date)
    }

    print(f"📡 Fetching rounds for Date: {target_date}, Court: {stadium_num}...")
    res = session.post(round_url, data=payload, timeout=15)
    
    if res.status_code != 200:
        return False, f"ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์เทศบาลได้ (HTTP {res.status_code})"

    try:
        data = res.json()
        round_html = data.get('round', '')
    except Exception:
        round_html = res.text

    soup = BeautifulSoup(round_html, 'html.parser')
    clean_round_search = target_round.replace(" น.", "").strip()

    selected_value = None
    for element in soup.find_all(['label', 'div', 'span']):
        if clean_round_search in element.get_text():
            parent = element.find_parent()
            if parent:
                radio = parent.find('input', {'type': 'radio'}) or element.find('input', {'type': 'radio'})
                if radio and radio.get('value'):
                    selected_value = radio.get('value')
                    break

    if not selected_value:
        for input_tag in soup.find_all('input', {'type': 'radio'}):
            val = input_tag.get('value', '')
            if clean_round_search in val:
                selected_value = val
                break

    if not selected_value:
        print(f"❌ Could not find round value. Raw HTML: {round_html[:500]}")
        return False, f"ไม่พบรอบเวลา {target_round} หรือสนามเต็มแล้ว"

    submit_url = "https://hatyaicity.go.th/reservesport/reserve_service/save_round"
    booking_payload = {
        'service_cid': '3',
        'stadium_num': str(stadium_num),
        'choose_date': str(target_date),
        'round_time': selected_value,
        'round_id': selected_value
    }

    print(f"⚡ Submitting booking request with Value: {selected_value}...")
    save_res = session.post(submit_url, data=booking_payload, timeout=15)

    if save_res.status_code == 200:
        return True, f"🎉 บอททำรายการจองสำเร็จแล้ว!\n📅 วันที่: {target_date}\n🏸 สนาม: {stadium_num}\n⏰ รอบ: {target_round}\nโปรดเข้าสู่ระบบเทศบาลนครหาดใหญ่เพื่อชำระเงิน"
    else:
        return False, f"เกิดข้อผิดพลาดในการส่งข้อมูลจอง (HTTP {save_res.status_code})"

def scheduled_booking_task(user_id, run_time_str, target_date, stadium_num, target_round):
    if run_time_str.lower() != 'now':
        try:
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

    print(f"🚀 Executing Direct API Task for User: {user_id}")
    success, result_msg = direct_api_booking(target_date, stadium_num, target_round)

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
