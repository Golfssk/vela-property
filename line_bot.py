import os
import json
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    QuickReply, QuickReplyButton, MessageAction
)
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

@app.route("/")
def home():
    return "Vela Property LINE Bot is running actively!"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

def parse_gemini_json(response_text):
    raw_text = response_text.strip()
    if "```json" in raw_text:
        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        raw_text = raw_text.split("```")[1].strip()
    return json.loads(raw_text)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    model = genai.GenerativeModel('gemini-3.6-flash')

    # ---------------- โมดูล 1: บันทึกตลาด ----------------
    if user_text == "[MENU] บันทึกตลาด":
        msg = "📍 **โหมดบันทึกตลาด**\n\nกรุณาพิมพ์คำว่า **บันทึกตลาด** ตามด้วยโพสต์ประกาศขายหรือพิกัดได้เลยครับ"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))

    elif user_text.startswith("บันทึกตลาด"):
        prompt = f"""
        สกัดข้อมูลอสังหาริมทรัพย์พื้นที่ปากช่องจากข้อความนี้ ให้อยู่ในรูปแบบ JSON เท่านั้น:
        "{user_text}"
        
        รูปแบบ:
        {{
            "property_type": "ประเภททรัพย์ ถ้าไม่มีใส่ 'ไม่ระบุ'",
            "location_zone": "ชื่อตำบลในปากช่อง ถ้าไม่มีใส่ 'ไม่ระบุ'",
            "price": ตัวเลขราคาขายรวมเป็นบาท (ถ้าไม่มีใส่ null),
            "size_sq_wah": ตัวเลขขนาดพื้นที่รวมเป็นตารางวา (ถ้าไม่มีใส่ null),
            "source_url": "URL ที่พบ (ถ้าไม่มีใส่ null)",
            "latitude": ตัวเลขพิกัดละติจูด (วิเคราะห์จากจุดสังเกต หรือ null),
            "longitude": ตัวเลขพิกัดลองจิจูด (วิเคราะห์จากจุดสังเกต หรือ null)
        }}
        """
        try:
            response = model.generate_content(prompt)
            data = parse_gemini_json(response.text)
            
            price = data.get('price')
            size = data.get('size_sq_wah')
            lat, lng = data.get('latitude'), data.get('longitude')
            
            price_per_sq_wah = float(price) / float(size) if price and size and float(size) > 0 else None
                
            insert_data = {
                "property_type": data.get('property_type', 'ไม่ระบุ'),
                "location_zone": data.get('location_zone', 'ไม่ระบุ'),
                "price": price,
                "size_sq_wah": size,
                "price_per_sq_wah": price_per_sq_wah,
                "source_url": data.get('source_url'),
                "latitude": lat,
                "longitude": lng,
                "status": "ใหม่"
            }
            supabase.table("pakchong_market_scout").insert(insert_data).execute()
            
            reply_msg = (f"✅ บันทึกตลาดสำเร็จ!\n📌 {insert_data['property_type']} | ต.{insert_data['location_zone']}\n"
                         f"💰 ราคา: {f'{price:,.0f}' if price else 'ไม่ระบุ'} บาท\n"
                         f"🗺️ พิกัด: {lat}, {lng}" if lat else "🗺️ พิกัด: ไม่ระบุ")
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ Error: {str(e)}"))

    # ---------------- โมดูล 2: CRM & Matching ----------------
    elif user_text == "[MENU] เพิ่มลูกค้า":
        msg = "👥 **โหมดเพิ่มลูกค้า / CRM**\n\nกรุณาพิมพ์คำว่า **เพิ่มลูกค้า**, **เพิ่มผู้ขาย** หรือ **เพิ่มนายหน้า** ตามด้วยรายละเอียดและงบประมาณครับ"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))

    elif user_text.startswith(("เพิ่มลูกค้า", "เพิ่มผู้ขาย", "เพิ่มนายหน้า")):
        contact_type = "ผู้ซื้อ" if user_text.startswith("เพิ่มลูกค้า") else "ผู้ขาย" if user_text.startswith("เพิ่มผู้ขาย") else "นายหน้า"
        prompt = f"""
        สกัดข้อมูล Lead จากข้อความนี้ให้อยู่ในรูปแบบ JSON เท่านั้น:
        "{user_text}"
        
        รูปแบบ:
        {{
            "name": "ชื่อบุคคล",
            "budget_max": ตัวเลขงบสูงสุดเป็นบาท (ถ้าไม่มีระบุให้เดาจากงบประเมิน หรือใส่ 0),
            "property_type": "ประเภททรัพย์ที่หา เช่น ที่ดิน, บ้าน (ถ้าไม่มีใส่ 'ไม่ระบุ')",
            "location_zone": "ทำเลที่หา ถ้าไม่มีใส่ 'ไม่ระบุ'",
            "contact_info": "เบอร์โทร หรือ Line",
            "note": "รายละเอียดเพิ่มเติม"
        }}
        """
        try:
            response = model.generate_content(prompt)
            data = parse_gemini_json(response.text)
            
            insert_data = {
                "contact_type": contact_type,
                "name": data.get('name', 'ไม่ระบุชื่อ'),
                "budget_max": data.get('budget_max', 0),
                "property_type": data.get('property_type', 'ไม่ระบุ'),
                "location_zone": data.get('location_zone', 'ไม่ระบุ'),
                "contact_info": data.get('contact_info', ''),
                "note": data.get('note', '')
            }
            supabase.table("pakchong_crm").insert(insert_data).execute()
            
            reply_msg = f"👤 บันทึก {contact_type} สำเร็จ: {insert_data['name']}\n🔎 หา: {insert_data['property_type']} โซน {insert_data['location_zone']}\n💰 งบสูงสุด: {f'{insert_data['budget_max']:,.0f}'} บาท\n"
            
            if contact_type == "ผู้ซื้อ" and insert_data['budget_max'] > 0:
                match_response = supabase.table("pakchong_market_scout").select("property_type, location_zone, price").lte("price", insert_data['budget_max']).ilike("location_zone", f"%{insert_data['location_zone']}%").order("price", desc=True).limit(3).execute()
                matches = match_response.data
                if matches:
                    reply_msg += "\n🔥 พบทรัพย์ที่อาจตรงสเปก:\n"
                    for i, m in enumerate(matches, 1):
                        reply_msg += f"{i}. {m['property_type']} ต.{m['location_zone']} - {m['price']:,.0f} บ.\n"
                else:
                    reply_msg += "\n*ยังไม่พบทรัพย์ในตลาดที่ตรงสเปกและอยู่ในงบ*"

            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))
        except Exception as e:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ Error CRM: {str(e)}"))

    # ---------------- โมดูล 3: สร้างโพสต์ขาย ----------------
    elif user_text == "[MENU] สร้างโพสต์ขาย":
        msg = "✍️ **โหมดสร้างโพสต์ขาย**\n\nกรุณาพิมพ์คำว่า **โพสต์** ตามด้วยรายละเอียดทรัพย์ หรือ รหัสทรัพย์ เช่น:\nโพสต์ ที่ดินหมูสี 2 ไร่ 5 ล้าน วิวเขา มีน้ำไฟพร้อม เน้นกลุ่มคนกรุงเทพ"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))

    elif user_text.startswith("โพสต์"):
        clean_text = user_text.replace("โพสต์", "").strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⏳ AI กำลังเรียบเรียงแคปชันและดึงจุดขาย กรุณารอสักครู่..."))
        prompt = f"""
        คุณคือนักการตลาดอสังหาริมทรัพย์มืออาชีพ จงเขียนแคปชัน Facebook/TikTok สำหรับขายทรัพย์นี้:
        ข้อมูล: "{clean_text}"
        
        กรุณาเขียนผลลัพธ์โดยแบ่งเป็น 3 ส่วน:
        1. 🎯 Headline: พาดหัวดึงดูดใจ 2 แบบ
        2. 📝 Caption: เนื้อหาที่อ่านง่าย แบ่งวรรคตอนชัดเจน เน้นจุดเด่น (ใช้ Emoji ประกอบพองาม)
        3. 🏷️ Hashtags: แฮชแท็กที่เกี่ยวข้องกับอสังหาฯ ปากช่อง/เขาใหญ่
        """
        try:
            response = model.generate_content(prompt)
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=response.text.strip()))
        except Exception as e:
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ Error Content: {str(e)}"))

    # ---------------- โมดูล 4: เมนูกฎหมายและสัญญา ----------------
    elif user_text == "[MENU] สัญญา":
        quick_reply_buttons = QuickReply(
            items=[
                QuickReplyButton(action=MessageAction(label="🆕 สร้างสัญญา", text="[CONTRACT] สร้าง")),
                QuickReplyButton(action=MessageAction(label="🔍 ตรวจสอบสัญญา", text="[CONTRACT] ตรวจสอบ")),
                QuickReplyButton(action=MessageAction(label="✏️ แก้ไขสัญญา", text="[CONTRACT] แก้ไข")),
                QuickReplyButton(action=MessageAction(label="❌ ยกเลิก", text="ยกเลิก"))
            ]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📑 **เมนูกฎหมายและสัญญาอสังหาฯ**\nกรุณาเลือกรายการที่ต้องการทำครับ:", quick_reply=quick_reply_buttons))

    elif user_text == "[CONTRACT] สร้าง":
        quick_reply_types = QuickReply(
            items=[
                QuickReplyButton(action=MessageAction(label="นายหน้าเปิด (Open)", text="[CREATE_PDF] นายหน้าเปิด")),
                QuickReplyButton(action=MessageAction(label="นายหน้าปิด (Exclusive)", text="[CREATE_PDF] นายหน้าปิด")),
                QuickReplyButton(action=MessageAction(label="สัญญาจะซื้อจะขาย", text="[CREATE_PDF] สัญญาจะซื้อจะขาย")),
                QuickReplyButton(action=MessageAction(label="❌ ยกเลิก", text="ยกเลิก"))
            ]
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📝 **เลือกประเภทสัญญาที่ต้องการสร้าง:**", quick_reply=quick_reply_types))

    elif user_text.startswith("[CREATE_PDF]"):
        contract_type = user_text.replace("[CREATE_PDF]", "").strip()
        msg = f"📄 **พร้อมสร้าง: {contract_type}**\n\nกรุณาพิมพ์คำว่า **ร่างสัญญา** ตามด้วยข้อมูล เช่น:\nร่างสัญญา ผู้ซื้อคุณเอ ผู้ขายคุณบี ที่ดินหมูสี 2 ไร่ ราคา 5 ล้าน มัดจำ 1 แสน"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))

    elif user_text == "[CONTRACT] ตรวจสอบ":
        msg = "🔍 **โหมดตรวจสอบสัญญา**\n\nกรุณาพิมพ์คำว่า **ตรวจสัญญา** ตามด้วยข้อความสัญญาที่ต้องการให้ AI เช็กความเสี่ยงทางกฎหมายครับ"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))

    elif user_text == "[CONTRACT] แก้ไข":
        msg = "✏️ **โหมดแก้ไขสัญญา**\n\nกรุณาพิมพ์คำว่า **แก้ไขสัญญา** ตามด้วยจุดที่ต้องการปรับแก้ครับ"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))

    elif user_text.startswith(("ร่างสัญญา", "ตรวจสัญญา", "แก้ไขสัญญา")):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"⏳ ได้รับข้อมูล {user_text.split(' ')[0]} แล้ว ระบบ AI PDF กำลังอยู่ระหว่างเชื่อมต่อครับ..."))

    # ---------------- โมดูล 5: คำนวณค่าโอน ----------------
    elif user_text == "[MENU] คำนวณค่าโอน":
        msg = "🧮 **โหมดคำนวณค่าโอนกรมที่ดิน**\n\nกรุณาพิมพ์คำว่า **ค่าโอน** ตามด้วยตัวเลข เช่น:\nค่าโอน ราคาขาย 5 ล้าน ประเมิน 4 ล้าน ถือครองมา 3 ปี บุคคลธรรมดา"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))

    elif user_text.startswith("ค่าโอน"):
        clean_text = user_text.replace("ค่าโอน", "").strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⏳ AI กำลังคำนวณภาษีและค่าธรรมเนียม กรุณารอสักครู่..."))
        prompt = f"""
        คุณคือเจ้าหน้าที่ประเมินอสังหาริมทรัพย์และผู้เชี่ยวชาญกรมที่ดิน
        จงคำนวณค่าใช้จ่ายวันโอนกรรมสิทธิ์เบื้องต้นจากข้อมูลนี้: "{clean_text}"
        
        เงื่อนไขพื้นฐาน (อ้างอิงกฎหมายไทย):
        - ค่าธรรมเนียมการโอน 2% ของราคาประเมิน
        - ภาษีธุรกิจเฉพาะ 3.3% ของราคาขายหรือประเมิน (ที่สูงกว่า) กรณีถือครองไม่เกิน 5 ปี หรือไม่มีชื่อในทะเบียนบ้านเกิน 1 ปี
        - อากรแสตมป์ 0.5% ของราคาขายหรือประเมิน (ที่สูงกว่า) กรณีไม่เสียภาษีธุรกิจเฉพาะ
        - ภาษีเงินได้หัก ณ ที่จ่าย (ประเมินคร่าวๆ ตามขั้นบันได)
        
        ให้สรุปผลลัพธ์เป็น Bullet Point ที่อ่านง่าย แยกรายการค่าใช้จ่ายชัดเจน และสรุปยอดรวมคร่าวๆ
        หมายเหตุตอนท้าย: "ตัวเลขนี้เป็นการประมาณการ ควรตรวจสอบกับสำนักงานที่ดินอีกครั้ง"
        """
        try:
            response = model.generate_content(prompt)
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=response.text.strip()))
        except Exception as e:
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ Error Tax: {str(e)}"))

    # ---------------- โมดูล 6: ประเมินราคา ----------------
    elif user_text == "[MENU] ประเมินราคา":
        msg = "📊 **โหมดประเมินราคา (Valuation)**\n\nพิมพ์คำว่า **ประเมิน** ตามด้วยทรัพย์ที่ต้องการเช็กราคา เช่น:\nประเมิน ที่ดินหมูสี 2 ไร่ ราคา 5 ล้านบาท"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))

    elif user_text.startswith("ประเมิน"):
        clean_text = user_text.replace("ประเมิน", "").strip()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⏳ AI กำลังสืบค้นราคาตลาดและวิเคราะห์ความคุ้มค่า..."))
        
        prompt_extract = f"""
        สกัดข้อมูลเพื่อประเมินราคา จากข้อความนี้ให้อยู่ในรูปแบบ JSON เท่านั้น:
        "{clean_text}"
        
        รูปแบบ:
        {{
            "property_type": "ประเภททรัพย์ (เช่น ที่ดิน, บ้าน) ถ้าไม่มีใส่ 'ไม่ระบุ'",
            "location_zone": "ทำเลที่ตั้ง (เช่น หมูสี, ปากช่อง) ถ้าไม่มีใส่ 'ไม่ระบุ'",
            "price": ตัวเลขราคาขายรวมเป็นบาท (ถ้าไม่มีใส่ 0),
            "size_sq_wah": ตัวเลขขนาดพื้นที่รวมเป็นตารางวา (ถ้าไม่มีใส่ 0)
        }}
        """
        try:
            ext_response = model.generate_content(prompt_extract)
            data = parse_gemini_json(ext_response.text)
            
            target_type = data.get('property_type', 'ไม่ระบุ')
            target_zone = data.get('location_zone', 'ไม่ระบุ')
            target_price = data.get('price', 0)
            target_size = data.get('size_sq_wah', 0)
            
            target_price_per_sqw = target_price / target_size if target_size and target_size > 0 else 0
            
            res = supabase.table("pakchong_market_scout").select("price, size_sq_wah, price_per_sq_wah").eq("property_type", target_type).ilike("location_zone", f"%{target_zone}%").execute()
            comparables = [c for c in res.data if c.get('price_per_sq_wah')]
            
            if comparables and len(comparables) > 0:
                avg_price_per_sqw = sum([c['price_per_sq_wah'] for c in comparables]) / len(comparables)
                min_price_per_sqw = min([c['price_per_sq_wah'] for c in comparables])
                max_price_per_sqw = max([c['price_per_sq_wah'] for c in comparables])
                count = len(comparables)
                
                analysis_prompt = f"""
                คุณคือนักประเมินราคามืออาชีพ จงสรุปความคุ้มค่าของทรัพย์นี้
                เป้าหมาย: {target_type} ต.{target_zone} ขนาด {target_size} ตร.ว. ราคา {target_price:,.0f} บาท (ตก {target_price_per_sqw:,.0f} บ./ตร.ว.)
                ข้อมูลตลาด ({count} แปลงในระบบ): ราคาเฉลี่ย {avg_price_per_sqw:,.0f} บ./ตร.ว. (ต่ำสุด {min_price_per_sqw:,.0f} - สูงสุด {max_price_per_sqw:,.0f})
                
                สิ่งที่ต้องการ:
                1. ทรัพย์เป้าหมายถูกหรือแพงกว่าตลาดกี่ %
                2. เป็น Good Deal หรือไม่ ควรต่อรองราคาเหลือเท่าไร
                """
                analysis = model.generate_content(analysis_prompt).text.strip()
                reply_msg = f"📊 **ผลประเมินราคา:** {target_type} ต.{target_zone}\n🔎 เทียบกับฐานข้อมูล {count} แปลงในพื้นที่\n\n{analysis}"
            else:
                reply_msg = f"📉 **ผลประเมินราคา:** {target_type} ต.{target_zone}\nราคาตก {target_price_per_sqw:,.0f} บ./ตร.ว.\n⚠️ ยังไม่มีข้อมูลเปรียบเทียบในระบบสำหรับพื้นที่นี้ครับ"
                
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=reply_msg))
            
        except Exception as e:
            line_bot_api.push_message(event.source.user_id, TextSendMessage(text=f"❌ Error Valuation: {str(e)}"))

    elif user_text in ("ยกเลิก", "[MENU] ยกเลิก"):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔄 ยกเลิกรายการเรียบร้อยครับ กลับสู่โหมดปกติ"))

    else:
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="💡 กรุณากดเลือกเมนูจาก Rich Menu ด้านล่างได้เลยครับ")
        )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)