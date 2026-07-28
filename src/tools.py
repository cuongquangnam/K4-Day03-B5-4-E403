"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
Nơi khai báo tất cả các "món đồ nghề" mà ReAct Agent có thể gọi.
"""


import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import requests


def _missing_env_error(tool_name: str, missing_keys: List[str], user_hint: str) -> str:
    """
    Chuẩn hóa lỗi khi thiếu cấu hình môi trường cho tool.
    """
    joined = ", ".join(missing_keys)
    return (
        f"[{tool_name} ERROR] Thiếu cấu hình môi trường: {joined}. "
        f"Vui lòng cập nhật file .env và thử lại. "
        f"Nếu chưa có giá trị, hãy nhập từ người dùng: {user_hint}"
    )


def _validate_non_empty(value: str, field_name: str) -> Tuple[bool, str]:
    """
    Kiểm tra chuỗi đầu vào bắt buộc.
    """
    if not isinstance(value, str) or not value.strip():
        return False, (
            f"[INPUT ERROR] '{field_name}' đang thiếu. "
            f"Vui lòng yêu cầu người dùng nhập '{field_name}' rồi thực hiện lại."
        )
    return True, ""


def _truncate(text: str, max_len: int) -> str:
    text = text or ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _price_match_to_vnd(number_str: str, unit_str: str) -> float | None:
    """
    Chuyển chuỗi số + đơn vị (triệu/tỷ) sang VND.
    Best-effort: không đảm bảo 100% vì HTML/text từng nguồn khác nhau.
    """
    try:
        s = (number_str or "").replace(",", ".").strip()
        value = float(s)
    except Exception:
        return None

    unit = (unit_str or "").lower().strip()
    if unit in {"triệu", "trieu", "tr"}:
        return value * 1_000_000
    if unit in {"tỷ", "ty"}:
        return value * 1_000_000_000
    return None


def _extract_price_vnd(text: str) -> float | None:
    """
    Trích xuất giá dạng 'X triệu' hoặc 'X tỷ' từ text.
    Trả về giá đầu tiên tìm được (best-effort).
    """
    if not text:
        return None
    m = re.search(
        r"(\d+(?:[.,]\d+)*)\s*(triệu|tỷ|ty|trieu|tr)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    return _price_match_to_vnd(m.group(1), m.group(2))


def _batdongsan_district_slug(location: str) -> str | None:
    """
    Map "Quận 7" -> "quan-7" để build URL Batdongsan.
    Chỉ best-effort cho các quận đánh số (1..n).
    """
    t = (location or "").lower()
    # "quận 7" hoặc "quan 7"
    m = re.search(r"(quận|quan)\s*(\d+)", t)
    if m:
        return f"quan-{m.group(2)}"
    # "q7"
    m = re.search(r"\bq\s*(\d+)\b", t)
    if m:
        return f"quan-{m.group(1)}"
    return None


def _batdongsan_bedroom_slug(room_info: str) -> str | None:
    """
    Map "1 phòng ngủ" / "1PN" -> "1pn" (theo URL Batdongsan).
    Nếu không nhận ra, trả None để dùng trang tổng.
    """
    t = (room_info or "").lower()
    if "1pn" in t or "1 phòng" in t or "1 phòng" in t:
        return "1pn"
    if "2pn" in t or "2 phòng" in t or "2 phòng" in t:
        return "2pn"
    if "3pn" in t or "3 phòng" in t or "3 phỏng" in t:
        return "3pn"
    return None


def search_home_info(
    location: str,
    rent_duration: str,
    budget: float,
    room_info: str,
    monthly_income: float | None = None,
    commute_preference: str | None = None,
    max_commute_minutes: int | None = None,
    min_area_m2: float | None = None,
) -> str:
    """
    Tìm danh sách bài đăng cho thuê phù hợp với nhu cầu người dùng.

    Args:
        location (str): Khu vực muốn thuê (ví dụ: "Q7, TP.HCM").
        rent_duration (str): Thời gian thuê dự kiến (ví dụ: "6 tháng").
        budget (float): Ngân sách tối đa mỗi tháng (VND).
        room_info (str): Nhu cầu số phòng/loại phòng.
        monthly_income (float | None): Thu nhập hàng tháng của người dùng.
        commute_preference (str | None): Mô tả mục tiêu đi lại như "gần trường", "gần công ty".
        max_commute_minutes (int | None): Thời gian đi lại tối đa mong muốn.
        min_area_m2 (float | None): Diện tích tối thiểu mong muốn.

    Returns:
        str: Danh sách gợi ý gồm nguồn đăng, liên hệ và giá, kèm nhận xét về khả năng chi trả và phù hợp đi lại.
    """
    for value, name in [
        (location, "location"),
        (rent_duration, "rent_duration"),
        (room_info, "room_info"),
    ]:
        is_valid, err = _validate_non_empty(value, name)
        if not is_valid:
            return err
    if not isinstance(budget, (int, float)) or budget <= 0:
        return (
            "[INPUT ERROR] 'budget' không hợp lệ. "
            "Vui lòng yêu cầu người dùng nhập ngân sách dạng số dương (VND)."
        )

    if monthly_income is not None and (not isinstance(monthly_income, (int, float)) or monthly_income <= 0):
        return (
            "[INPUT ERROR] 'monthly_income' không hợp lệ. "
            "Vui lòng yêu cầu người dùng nhập thu nhập hàng tháng dạng số dương."
        )

    if max_commute_minutes is not None and (not isinstance(max_commute_minutes, (int, float)) or max_commute_minutes <= 0):
        return (
            "[INPUT ERROR] 'max_commute_minutes' không hợp lệ. "
            "Vui lòng yêu cầu người dùng nhập thời gian đi lại tối đa dạng số dương."
        )

    if min_area_m2 is not None and (not isinstance(min_area_m2, (int, float)) or min_area_m2 <= 0):
        return (
            "[INPUT ERROR] 'min_area_m2' không hợp lệ. "
            "Vui lòng yêu cầu người dùng nhập diện tích tối thiểu dạng số dương."
        )

    # ----------------------------
    # Facebook Graph API
    # ----------------------------
    # Env tối thiểu để gọi Facebook:
    # - FACEBOOK_ACCESS_TOKEN
    # - FACEBOOK_GROUP_OR_PAGE_ID
    # (nhóm/page có quyền đọc feed/tin nhắn đăng công khai tùy grant của token)
    missing_fb = [
        key
        for key in ["FACEBOOK_ACCESS_TOKEN", "FACEBOOK_GROUP_OR_PAGE_ID"]
        if not os.getenv(key)
    ]

    fb_items: List[Dict[str, str]] = []
    fb_errors: List[str] = []
    if not missing_fb:
        fb_version = os.getenv("FACEBOOK_GRAPH_API_VERSION", "v19.0")
        fb_limit = int(os.getenv("FACEBOOK_MAX_RESULTS", "10"))
        fb_id = os.getenv("FACEBOOK_GROUP_OR_PAGE_ID")
        fb_token = os.getenv("FACEBOOK_ACCESS_TOKEN")
        query = {
            "fields": "message,permalink_url,created_time",
            "limit": str(fb_limit),
            "access_token": fb_token,
        }
        feed_url = f"https://graph.facebook.com/{fb_version}/{fb_id}/feed"

        try:
            res = requests.get(feed_url, params=query, timeout=20)
            if res.status_code != 200:
                fb_errors.append(
                    f"Facebook API HTTP {res.status_code}: {res.text[:300]}"
                )
            else:
                data = res.json().get("data", []) if res.text else []
                if not isinstance(data, list):
                    data = []

                normalized_location = location.lower()
                normalized_room = room_info.lower()
                for post in data:
                    message = (post.get("message") or "").strip()
                    if not message:
                        continue
                    msg_l = message.lower()
                    # Filter theo từ khóa đơn giản (lab):
                    if normalized_location not in msg_l and normalized_room not in msg_l:
                        continue

                    # Price extraction (best-effort)
                    phone_candidates = re.findall(r"\b(0\d{8,9})\b", message)
                    phone = phone_candidates[0] if phone_candidates else "N/A"

                    price_vnd = _extract_price_vnd(message)
                    if price_vnd is None:
                        continue
                    if price_vnd > float(budget):
                        continue

                    fb_items.append(
                        {
                            "title": _truncate(message.replace("\n", " "), 80),
                            "price_vnd": str(int(price_vnd)),
                            "source": "facebook",
                            "contact_name": "N/A",
                            "phone": phone,
                            "profile": post.get("permalink_url") or "N/A",
                        }
                    )
        except Exception as e:
            fb_errors.append(f"Facebook request exception: {str(e)[:200]}")
    else:
        fb_errors.append(
            "Thiếu env Facebook: " + ", ".join(missing_fb)
        )

    # ----------------------------
    # Batdongsan.com.vn
    # ----------------------------
    # Cách 1 (khuyến nghị production): dùng scraper service của bạn
    # Env:
    # - BDS_SCRAPE_API_URL (endpoint trả về JSON list listing)
    # Cách 2 (fallback lab): scrape trực tiếp HTML từ BDS_SEARCH_URL_TEMPLATE/BDS_SEARCH_URL
    bds_items: List[Dict[str, str]] = []
    bds_errors: List[str] = []

    bds_scrape_url = os.getenv("BDS_SCRAPE_API_URL")
    if bds_scrape_url:
        payload = {
            "location": location,
            "rent_duration": rent_duration,
            "budget": budget,
            "room_info": room_info,
        }
        try:
            res = requests.post(
                bds_scrape_url, json=payload, timeout=25
            )
            if res.status_code != 200:
                bds_errors.append(
                    f"BDS scraper HTTP {res.status_code}: {res.text[:300]}"
                )
            else:
                data = res.json()
                if isinstance(data, dict) and "items" in data:
                    data = data["items"]
                if not isinstance(data, list):
                    data = []
                for item in data[:10]:
                    if not isinstance(item, dict):
                        continue
                    price_vnd = item.get("price_vnd")
                    if price_vnd is None:
                        continue
                    try:
                        price_vnd_f = float(price_vnd)
                    except Exception:
                        continue
                    if price_vnd_f > float(budget):
                        continue
                    bds_items.append(
                        {
                            "title": str(item.get("title", "N/A"))[:200],
                            "price_vnd": str(int(price_vnd_f)),
                            "source": "batdongsan",
                            "contact_name": str(item.get("contact_name", "N/A")),
                            "phone": str(item.get("phone", "N/A")),
                            "profile": str(item.get("profile", item.get("permalink_url", "N/A"))),
                        }
                    )
        except Exception as e:
            bds_errors.append(f"BDS scraper request exception: {str(e)[:200]}")
    else:
        # direct HTML scrape fallback (best-effort; parsing có thể không ổn định)
        direct_scrape_allowed = os.getenv("BDS_DIRECT_SCRAPE", "0").lower().strip() in {
            "1",
            "true",
            "yes",
        }

        if not direct_scrape_allowed:
            bds_errors.append(
                "Batdongsan.com.vn có cơ chế chống bot (ví dụ Cloudflare). "
                "Vui lòng dùng BDS_SCRAPE_API_URL (scraper service) hoặc bật BDS_DIRECT_SCRAPE=1 nếu bạn có proxy/cookie/giải pháp vượt bot."
            )
        else:
            template = os.getenv("BDS_SEARCH_URL_TEMPLATE")
            direct_url = os.getenv("BDS_SEARCH_URL")

            if not direct_url and not template:
                # Auto build URL by research pattern:
                #   - Base: https://batdongsan.com.vn/cho-thue-can-ho-chung-cu-quan-7
                #   - Bedroom filter: /1pn /2pn /3pn
                district_slug = _batdongsan_district_slug(location)
                bedroom_slug = _batdongsan_bedroom_slug(room_info)
                if not district_slug:
                    bds_errors.append(
                        "Không auto-build được URL Batdongsan từ location. "
                        "Vui lòng cung cấp BDS_SEARCH_URL/BDS_SEARCH_URL_TEMPLATE."
                    )
                else:
                    direct_url = f"https://batdongsan.com.vn/cho-thue-can-ho-chung-cu-{district_slug}"
                    if bedroom_slug:
                        direct_url = f"{direct_url}/{bedroom_slug}"
            elif not direct_url and template:
                # Ví dụ template: "https://batdongsan.com.vn/cho-thue-can-ho-chung-cu-{district_slug}/{bedroom_slug}"
                direct_url = template.format(location=location, room_info=room_info)

            if direct_url:
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (compatible; HomeSearchBot/1.0)"
                    }
                    res = requests.get(direct_url, headers=headers, timeout=25)
                    if res.status_code != 200:
                        bds_errors.append(
                            f"BDS HTML HTTP {res.status_code}: {res.text[:200]}"
                        )
                    else:
                        html = res.text or ""
                        # Very rough extraction: find phones, prices, and nearest title-ish fragments.
                        phones = re.findall(r"\b(0\d{8,9})\b", html)
                        price_matches = list(
                            re.finditer(
                                r"(\d+(?:[.,]\d+)*)\s*(triệu|ty|tỷ)\s*đ?",
                                html,
                                flags=re.IGNORECASE,
                            )
                        )
                        if not price_matches:
                            bds_errors.append(
                                "Không parse được giá từ trang batdongsan (best-effort)."
                            )
                        else:
                            title_candidates: List[str] = []
                            for m in re.finditer(
                                r"<h3[^>]*>(.*?)</h3>",
                                html,
                                flags=re.IGNORECASE | re.DOTALL,
                            ):
                                txt = re.sub(r"<[^>]+>", "", m.group(1))
                                txt = re.sub(r"\s+", " ", txt).strip()
                                if not txt:
                                    continue
                                title_candidates.append(txt)
                                if len(title_candidates) >= 5:
                                    break

                            for i in range(min(5, len(price_matches))):
                                p = price_matches[i]
                                price_vnd = _price_match_to_vnd(p.group(1), p.group(2))
                                if price_vnd is None or price_vnd > float(budget):
                                    continue
                                phone = (
                                    phones[i] if i < len(phones) else "N/A"
                                )
                                bds_items.append(
                                    {
                                        "title": title_candidates[i]
                                        if i < len(title_candidates)
                                        else f"BDS listing {i+1}",
                                        "price_vnd": str(int(price_vnd)),
                                        "source": "batdongsan",
                                        "contact_name": "N/A",
                                        "phone": phone,
                                        "profile": direct_url,
                                    }
                                )
                except Exception as e:
                    bds_errors.append(f"BDS HTML request exception: {str(e)[:200]}")

    matched_items = sorted(
        fb_items + bds_items,
        key=lambda x: float(x.get("price_vnd", 0)),
    )

    if not matched_items:
        details = []
        if fb_errors:
            details.append("Facebook: " + " | ".join(fb_errors[:2]))
        if bds_errors:
            details.append("Batdongsan: " + " | ".join(bds_errors[:2]))
        return (
            f"Không tìm thấy tin phù hợp cho {location}, {room_info}, budget {budget:,.0f} VND. "
            + (" (" + " ; ".join(details) + ") " if details else "")
            + "Vui lòng nới ngân sách/đổi khu vực hoặc cung cấp thêm env API để tool truy cập nguồn dữ liệu."
        )

    summary_lines = []
    for item in matched_items[:5]:
        price_vnd_i = item.get("price_vnd", 0)
        try:
            price_vnd_f = float(price_vnd_i)
        except Exception:
            price_vnd_f = 0
        summary_lines.append(
            f"- {item.get('title', 'N/A')} | {price_vnd_f:,.0f} VND/tháng | "
            f"Nguồn: {item.get('source', 'N/A')} | "
            f"Liên hệ: {item.get('contact_name', 'N/A')} ({item.get('phone', 'N/A')}) | "
            f"Profile: {item.get('profile', 'N/A')}"
        )

    criteria_parts = []
    if monthly_income is not None:
        criteria_parts.append(f"thu nhập hiện có {monthly_income:,.0f} VND")
    if max_commute_minutes is not None:
        criteria_parts.append(f"thời gian đi lại tối đa {max_commute_minutes} phút")
    if min_area_m2 is not None:
        criteria_parts.append(f"diện tích tối thiểu {min_area_m2} m²")
    if commute_preference:
        criteria_parts.append(f"ưu tiên đi lại gần {commute_preference}")

    affordability_note = ""
    if monthly_income is not None and budget is not None:
        ratio = budget / monthly_income
        if ratio > 0.4:
            affordability_note = (
                f"\n⚠️ Chi phí thuê chiếm khoảng {ratio:.0%} thu nhập, cao hơn mức khuyến nghị nên cần cân nhắc kỹ."
            )
        else:
            affordability_note = (
                f"\n✅ Chi phí thuê chiếm khoảng {ratio:.0%} thu nhập, ở mức hợp lý so với thu nhập hiện có."
            )

    criteria_text = ", ".join(criteria_parts) if criteria_parts else "không có tiêu chí bổ sung"
    return (
        "Kết quả tìm kiếm (best-effort) từ Facebook + Batdongsan theo yêu cầu "
        f"(location={location}, rent_duration={rent_duration}, budget={budget}, room_info={room_info}):\n"
        + "\n".join(summary_lines)
        + f"\n\nTiêu chí đánh giá bổ sung: {criteria_text}."
        + affordability_note
    )


def get_calendar() -> str:
    """
    Lấy các khung giờ rảnh của người dùng để đề xuất lịch đi xem nhà.

    Returns:
        str: Các mốc giờ khả dụng trong 7 ngày tới.
    """
    calendar_user = os.getenv("CALENDAR_USER_ID")
    timezone = os.getenv("CALENDAR_TIMEZONE")
    calendar_provider = os.getenv("CALENDAR_PROVIDER", "api")

    if not calendar_user or not timezone:
        missing_env = [k for k in ["CALENDAR_USER_ID", "CALENDAR_TIMEZONE"] if not os.getenv(k)]
        return _missing_env_error(
            "get_calendar",
            missing_env,
            "calendar user id, và timezone",
        )

    # Prefer production-style call:
    calendar_api_url = os.getenv("CALENDAR_API_URL")
    if calendar_api_url:
        start_iso = datetime.now().isoformat(timespec="seconds")
        end_iso = (datetime.now() + timedelta(days=7)).isoformat(timespec="seconds")

        payload = {
            "user_id": calendar_user,
            "timezone": timezone,
            "start": start_iso,
            "end": end_iso,
        }
        try:
            res = requests.post(calendar_api_url, json=payload, timeout=25)
            if res.status_code != 200:
                return f"[get_calendar ERROR] Calendar API HTTP {res.status_code}: {res.text[:250]}"
            data = res.json()
            slots = data.get("slots", data.get("items", data))
        except Exception as e:
            return f"[get_calendar ERROR] Calendar API request exception: {str(e)[:200]}"
    else:
        # Fallback for lab: slots come from env JSON
        raw_slots = os.getenv("CALENDAR_SLOTS_JSON")
        if not raw_slots:
            return _missing_env_error(
                "get_calendar",
                ["CALENDAR_API_URL", "CALENDAR_SLOTS_JSON"],
                "endpoint calendar API hoặc danh sách slot rảnh (JSON)",
            )
        try:
            slots = json.loads(raw_slots)
        except json.JSONDecodeError:
            return (
                "[get_calendar ERROR] CALENDAR_SLOTS_JSON không đúng định dạng JSON. "
                "Vui lòng nhập lại danh sách slot rảnh hợp lệ."
            )

    if not isinstance(slots, list) or not slots:
        return (
            "[get_calendar ERROR] Không có slot rảnh từ calendar. "
            "Vui lòng yêu cầu người dùng cung cấp thời gian rảnh để tiếp tục."
        )

    formatted_slots: List[str] = []
    for slot in slots[:5]:
        start = slot.get("start")
        end = slot.get("end")
        if not start or not end:
            continue
        formatted_slots.append(f"{start} -> {end}")

    if not formatted_slots:
        return (
            "[get_calendar ERROR] Dữ liệu slot rảnh thiếu trường start/end. "
            "Vui lòng nhập đầy đủ thời gian bắt đầu và kết thúc."
        )

    return (
        f"Lịch rảnh từ {calendar_provider} của user {calendar_user} (timezone {timezone}, "
        f"đồng bộ lúc {datetime.now().isoformat(timespec='seconds')}): "
        + "; ".join(formatted_slots)
    )


def send_msg(destination: str, msg: str) -> str:
    """
    Gửi tin nhắn qua Zalo (mô phỏng).
    Hàm này cũng được dùng để nhắn chủ nhà kiểm tra availability.

    Args:
        destination (str): Người nhận. Ví dụ: số điện thoại chủ nhà hoặc "user_zalo".
        msg (str): Nội dung tin nhắn cần gửi.

    Returns:
        str: Trạng thái gửi và phản hồi mô phỏng.
    """
    is_valid_dest, err_dest = _validate_non_empty(destination, "destination")
    if not is_valid_dest:
        return err_dest
    is_valid_msg, err_msg = _validate_non_empty(msg, "msg")
    if not is_valid_msg:
        return err_msg

    missing_env = [k for k in ["ZALO_SEND_API_URL"] if not os.getenv(k)]
    if missing_env:
        return _missing_env_error(
            "send_msg",
            missing_env,
            "ZALO_SEND_API_URL (endpoint gửi tin qua Zalo)",
        )

    zalo_send_api_url = os.getenv("ZALO_SEND_API_URL")
    zalo_mode = os.getenv("ZALO_MODE", "sandbox")
    zalo_oa_id = os.getenv("ZALO_OA_ID", "")
    zalo_access_token = os.getenv("ZALO_ACCESS_TOKEN", "")

    payload = {
        "oa_id": zalo_oa_id,
        "to": destination,
        "message": msg,
        "mode": zalo_mode,
    }
    headers = {"Authorization": f"Bearer {zalo_access_token}"} if zalo_access_token else {}

    try:
        res = requests.post(zalo_send_api_url, json=payload, headers=headers, timeout=25)
        if res.status_code != 200:
            return f"[send_msg ERROR] Zalo API HTTP {res.status_code}: {res.text[:250]}"
        data = res.json() if res.text else {}
        return f"[{zalo_mode}] Đã gửi Zalo tới {destination}. Response: {str(data)[:180]}"
    except Exception as e:
        return f"[send_msg ERROR] Zalo API request exception: {str(e)[:200]}"

# Danh sách các tool được đăng ký để Agent sử dụng
AVAILABLE_TOOLS = {
    "search_home_info": search_home_info,
    "get_calendar": get_calendar,
    "send_msg": send_msg,
}
