import os
import json
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from supabase import create_client, Client
import google.generativeai as genai

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

SUPABASE_URL = "https://vfieyjxlrpziiksyccdt.supabase.co"
SUPABASE_KEY = "sb_publishable_udkJwGJ8zjXlEOlYszDRUg_yVD4g7ie" 

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    
    if not user_text.startswith("บันทึกตลาด"):
        reply_msg = "พิมพ์ 'บันทึกตลาด' ขึ้นต้นข้อความ ตามด้วยโพสต์ประกาศขาย เพื่อสกัดข้อมูลลงระบบครับ"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))
        return

    prompt = f"""
    สกัดข้อมูลอสังหาริมทรัพย์พื้นที่ปากช่องจากข้อความนี้ ให้อยู่ในรูปแบบ JSON เท่านั้น:
    "{user_text}"
    
    รูปแบบที่ต้องการ:
    {{
        "property_type": "ประเภททรัพย์ (เช่น ที่ดิน, บ้าน, พูลวิลล่า, คอนโด) ถ้าไม่มีใส่ 'ไม่ระบุ'",
        "location_zone": "ชื่อตำบลในปากช่อง (ปากช่อง, หมูสี, กลางดง, จันทึก, วังกะทะ, หนองน้ำแดง, หนองสาหร่าย, ขนงพระ, โป่งตาลอง, คลองม่วง, วังไทร, พญาเย็น) ถ้าไม่มีใส่ 'ไม่ระบุ'",
        "price": ตัวเลขราคาขายรวมเป็นบาท (ถ้าไม่มีใส่ null),
        "size_sq_wah": ตัวเลขขนาดพื้นที่รวมเป็นตารางวา (เช่น 2 ไร่ = 800) (ถ้าไม่มีใส่ null),
        "source_url": "URL ที่พบในข้อความ (ถ้าไม่มีใส่ null)"
    }}
    """
    
    try:
        # ใช้ชื่อโมเดลมาตรฐาน หากอัปเดตไลบรารีแล้วจะไม่ติด Error 404
        model = genai.GenerativeModel('gemini-3.6-flash')
        response = model.generate_content(prompt)
        
        raw_text = response.text.strip()
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].strip()
            
        data = json.loads(raw_text)
        
        price = data.get('price')
        size = data.get('size_sq_wah')
        
        price_per_sq_wah = None
        if price and size and float(size) > 0:
            price_per_sq_wah = float(price) / float(size)
            
        insert_data = {
            "property_type": data.get('property_type', 'ไม่ระบุ'),
            "location_zone": data.get('location_zone', 'ไม่ระบุ'),
            "price": price,
            "size_sq_wah": size,
            "price_per_sq_wah": price_per_sq_wah,
            "source_url": data.get('source_url'),
            "status": "ใหม่"
        }
        
        # ชี้เป้าไปที่ตารางใหม่
        supabase.table("pakchong_market_scout").insert(insert_data).execute()
        
        reply_msg = (
            f"✅ บันทึกลงตาราง pakchong_market_scout สำเร็จ!\n\n"
            f"📌 ประเภท: {insert_data['property_type']}\n"
            f"📍 ทำเล: ต.{insert_data['location_zone']}\n"
            f"💰 ราคา: {f'{price:,.0f}' if price else 'ไม่ระบุ'} บาท\n"
            f"📐 ขนาด: {size if size else 'ไม่ระบุ'} ตร.ว.\n"
            f"📊 ราคา/ตร.ว.: {f'{price_per_sq_wah:,.0f}' if price_per_sq_wah else 'ไม่ระบุ'} บาท"
        )
                    
    except Exception as e:
        reply_msg = f"❌ เกิดข้อผิดพลาด: {str(e)}"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)