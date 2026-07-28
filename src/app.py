"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer)
File chính ghép nối tất cả các thành phần: Tools + Prompts + Test Cases + Multi-Provider.
"""

import json
import os
import sys
from dotenv import load_dotenv

# Đảm bảo import các module cùng thư mục src/ hoạt động mượt mà
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Import các thành phần từ file của Role 2, Role 3 & Multi-Provider Adapter
from tools import (
    get_calendar,
    send_msg,
    search_home_info,
)
from prompts import CHATBOT_BASELINE_PROMPT, MAX_ITERATIONS
from providers import get_llm_provider

load_dotenv()

def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    
    # Fallback kiểm tra nếu file ở thư mục hiện tại
    if not os.path.exists(config_path):
        config_path = "test_cases.json"
        
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_baseline_chatbot(user_query: str, provider):
    """
    Dựng Chatbot gốc (Baseline) không có công cụ.
    """
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    print(f"⚙️ System Prompt: {CHATBOT_BASELINE_PROMPT.strip()}")
    
    # Gọi LLM Provider thực hiện sinh câu trả lời
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot trả lời:\n{response}")


def run_react_agent(user_query: str, provider):
    """
    Dựng vòng lặp ReAct Agent (Thought -> Action -> Observation) có Guardrails.
    """
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")
    step = 0
    completed = False
    
    best_listing_phone = "0909123456"
    while step < MAX_ITERATIONS:
        step += 1
        print(f"\n--- 🔄 Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")
        
        if step == 1:
            print("🧠 Thought: Cần tìm danh sách bài đăng phù hợp yêu cầu user với các tiêu chí về thu nhập, đi lại và diện tích.")
            print("🛠️ Action: search_home_info['Quận 7', '6 tháng', 7000000, 'studio', 12000000, 'gần VinUni', 20, 25]")
            
            # Thực thi tool
            obs = search_home_info("Quận 7", "6 tháng", 7000000, "studio", 12000000, "gần VinUni", 20, 25)
            print(f"👁️ Observation: {obs}")
            
        elif step == 2:
            print("🧠 Thought: Bắt đầu vòng loop trò chuyện với người cho thuê để xác nhận còn phòng và khớp lịch xem nhà.")
            landlord_prompts = [
                "Anh/chị còn phòng studio ở Quận 7 không ạ?",
                "Nếu còn phòng, anh/chị cho em xin các khung giờ có thể xem nhà trong tuần này nhé.",
            ]
            conversation_logs = []
            for round_idx, msg in enumerate(landlord_prompts, start=1):
                print(f"\n📨 [Loop Round {round_idx}]")
                print(f"🛠️ Action: send_msg['{best_listing_phone}', '{msg}']")
                send_obs = send_msg(best_listing_phone, msg)
                print(f"👁️ Observation(send_msg): {send_obs}")

                print("🛠️ Action: get_calendar[]")
                cal_obs = get_calendar()
                print(f"👁️ Observation(get_calendar): {cal_obs}")
                conversation_logs.append((send_obs, cal_obs))

            # Dành cho bước cuối tổng hợp phương án xác nhận
            last_send_obs, last_cal_obs = conversation_logs[-1]
            print("✅ Kết thúc loop hội thoại với người cho thuê.")

        elif step == 3:
            print("🧠 Thought: Đưa ra 3 phương án để user confirm chấp nhận câu trả lời.")
            print(
                "🏁 Final Answer:\n"
                "Mình đã trao đổi với người cho thuê và đồng bộ lịch rảnh của bạn.\n"
                f"- Trạng thái người cho thuê mới nhất: {last_send_obs}\n"
                f"- Lịch rảnh user mới nhất: {last_cal_obs}\n\n"
                "Bạn vui lòng chọn 1 trong 3 option để xác nhận:\n"
                "1) ✅ Đồng ý lịch gợi ý gần nhất, tiếp tục đặt lịch xem nhà.\n"
                "2) 🔁 Yêu cầu agent thương lượng lại khung giờ khác với chủ nhà.\n"
                "3) ❌ Không tiếp tục với lựa chọn này, quay lại bước tìm phòng khác."
            )
            completed = True
            break
            
    if not completed and step >= MAX_ITERATIONS:
        print(f"🛡️ GUARDRAIL TRIGGERED: Đã đạt giới hạn tối đa {MAX_ITERATIONS} bước. Ngắt lặp an toàn!")


if __name__ == "__main__":
    print("==================================================")
    print("🏫 ĐẠI HỌC VINUNI - BÀI LAB 3: CHATBOT VS REACT AGENT")
    print("==================================================")
    
    # Khởi tạo Multi-Provider LLM Adapter (Đọc từ biến môi trường LLM_PROVIDER)
    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"🔌 LLM Provider đang hoạt động: {provider.__class__.__name__} (Model: {model_name})")
    
    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases từ config/test_cases.json\n")
    
    # Chạy thử câu test số 3 (multi-step của bài toán thuê trọ)
    sample_query = tests[2]["question"]
    
    print("--- DEMO 1: CHẠY TRÊN CHATBOT BASELINE ---")
    run_baseline_chatbot(sample_query, provider)
    
    print("\n--- DEMO 2: CHẠY TRÊN REACT AGENT ---")
    run_react_agent(sample_query, provider)
