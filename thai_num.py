# thai_num.py
"""แปลงจำนวนเงินเป็นคำอ่านภาษาไทย สำหรับใช้ในเอกสารสัญญา"""

THAI_DIGITS = ["", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
THAI_UNITS = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]


def _read_integer(num_str: str) -> str:
    """อ่านจำนวนเต็มเป็นคำไทย รองรับหลักล้านซ้อน"""
    num_str = num_str.lstrip("0") or "0"
    if num_str == "0":
        return "ศูนย์"

    # ตัดเป็นก้อนละ 6 หลักจากขวา เพื่อรองรับ "ล้าน" ซ้อนชั้น
    chunks = []
    while len(num_str) > 6:
        chunks.append(num_str[-6:])
        num_str = num_str[:-6]
    chunks.append(num_str)
    chunks.reverse()

    result = ""
    for idx, chunk in enumerate(chunks):
        part = _read_chunk(chunk)
        if part:
            result += part
            if idx < len(chunks) - 1:
                result += "ล้าน"
    return result


def _read_chunk(chunk: str) -> str:
    """อ่านตัวเลขไม่เกิน 6 หลัก"""
    chunk = chunk.lstrip("0")
    if not chunk:
        return ""

    result = ""
    length = len(chunk)
    for i, ch in enumerate(chunk):
        digit = int(ch)
        position = length - i - 1
        if digit == 0:
            continue
        if position == 0:
            if digit == 1 and length > 1:
                result += "เอ็ด"
            else:
                result += THAI_DIGITS[digit]
        elif position == 1:
            if digit == 1:
                result += "สิบ"
            elif digit == 2:
                result += "ยี่สิบ"
            else:
                result += THAI_DIGITS[digit] + "สิบ"
        else:
            result += THAI_DIGITS[digit] + THAI_UNITS[position]
    return result


def baht_text(amount) -> str:
    """
    แปลงจำนวนเงินเป็นคำอ่านไทยแบบเอกสารราชการ
    >>> baht_text(50000)      -> 'ห้าหมื่นบาทถ้วน'
    >>> baht_text(1250000.50) -> 'หนึ่งล้านสองแสนห้าหมื่นบาทห้าสิบสตางค์'
    """
    try:
        amount = float(str(amount).replace(",", "").strip())
    except (ValueError, TypeError):
        return ""

    negative = amount < 0
    amount = abs(amount)

    baht = int(amount)
    satang = int(round((amount - baht) * 100))
    if satang == 100:
        baht += 1
        satang = 0

    text = _read_integer(str(baht)) + "บาท"
    text += _read_integer(str(satang)) + "สตางค์" if satang else "ถ้วน"

    return ("ลบ" + text) if negative else text


def fmt_money(value) -> str:
    """จัดรูปแบบตัวเลขเงินให้มี comma เช่น 1,250,000"""
    try:
        return f"{float(str(value).replace(',', '')):,.0f}"
    except (ValueError, TypeError):
        return str(value) if value else ""