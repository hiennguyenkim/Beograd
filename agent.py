"""
agent.py
~~~~~~~~~~~~~~~~
AI Academic Advisor Agent — Production Grade

Kiến trúc: LangGraph ReAct Agent + 7 Tools chuyên biệt
  - 6 Structured tools  → truy vấn Neo4j Knowledge Graph
  - 1 RAW Data RAG tool → đọc thẳng curriculum_extracted.json bằng LLM
    (fallback khi câu hỏi nằm ngoài schema graph: chuẩn đầu ra, quy định...)

Schema Neo4j: Course, AcademicProgram, Khoa, PLO
Relationships: THUOC_KHOA, TIEN_QUYET, HOC_TRUOC, SONG_HANH, DAP_UNG_PLO

Cách chạy:
    python -X utf8 agent.py            # Chạy chế độ Chat tương tác trực tiếp
    python -X utf8 test_advisor.py     # Chạy bộ câu hỏi Smoke Test
"""

import logging
import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from tools import ALL_TOOLS

# ──────────────────────────────────────────────────────────────────────────
# Cấu hình
# ──────────────────────────────────────────────────────────────────────────
load_dotenv()
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except AttributeError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("agent")

SYSTEM_PROMPT = """Bạn là **AI Academic Advisor** (Cố vấn học tập) thông minh và nhiệt tình \
của Trường Đại học Sư phạm TP.HCM — Chuyên ngành Công nghệ thông tin.

## NGUYÊN TẮC LÀM VIỆC
1. Luôn xưng hô thân thiện: "Chào em", "Theo mình thấy...", "Bạn nên..."
2. **KHÔNG bịa** thông tin môn học — chỉ dùng dữ liệu từ các tools.
3. Gọi tools theo thứ tự logic:
   - Biết học kỳ → `tim_mon_theo_ky`
   - Biết kỹ năng/ngôn ngữ → `tim_mon_theo_cong_cu`
   - Biết mã môn → `xem_dieu_kien_tien_quyet` + `xem_mo_ta_mon`
   - Muốn đăng ký → `kiem_tra_mo_lop`
   - Hỏi lộ trình đến 1 môn → `tim_lo_trinh_den_mon`
4. Sau khi có kết quả tools, **tổng hợp thành câu trả lời rõ ràng**, có cấu trúc.
5. Nếu môn học hết chỗ hoặc không mở, gợi ý môn thay thế hoặc lên kế hoạch kỳ sau.

## ĐỊNH DẠNG TRẢ LỜI
- Dùng emoji nhẹ nhàng để phân mục (📘 🗓️ ✅ ⚠️)
- Liệt kê môn học theo thứ tự từ dễ đến khó / từ học kỳ nhỏ đến lớn
- Kết thúc bằng gợi ý hoặc câu hỏi thêm nếu cần làm rõ nhu cầu sinh viên
"""


# ──────────────────────────────────────────────────────────────────────────
# AGENT CLASS ENCAPSULATION
# ──────────────────────────────────────────────────────────────────────────

class AcademicAdvisorAgent:
    """
    Stateful AI Academic Advisor Agent sử dụng LangGraph và Neo4j.
    Hỗ trợ bộ nhớ theo phiên (session_id) để duy trì mạch hội thoại với sinh viên.
    """
    
    def __init__(self):
        self.model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        self.api_key = os.getenv("LLM_API_KEY")
        if not self.api_key:
            raise EnvironmentError("Thiếu LLM_API_KEY trong file .env")

        logger.info(f"Khởi tạo AcademicAdvisorAgent — Model: {self.model_name}")
        
        # Khởi tạo LLM
        self.llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            google_api_key=self.api_key,
            temperature=0.1,
        )

        # Đăng ký danh sách tools (từ tools.py)
        self.tools = ALL_TOOLS

        # Bộ nhớ để track lịch sử trò chuyện (có thể dùng RedisSaver / PostgresSaver trên prod)
        self.memory = MemorySaver()

        self.agent = create_react_agent(
            model=self.llm, 
            tools=self.tools, 
            checkpointer=self.memory,
            prompt=SYSTEM_PROMPT
        )

    def chat(self, session_id: str, message: str) -> str:
        """
        Gửi tin nhắn đến Agent và trả về câu trả lời.
        Bộ nhớ hội thoại được tự động lưu dựa theo session_id.
        
        Args:
            session_id: Cấp bởi ứng dụng (VD: UUID hoặc MSSV của user).
            message: Câu hỏi của sinh viên.
        """
        config = {"configurable": {"thread_id": session_id}}
        
        try:
            # invoke() tự động lấy config thread_id để load memory cũ + lưu memory mới
            response = self.agent.invoke(
                {"messages": [("user", message)]},
                config=config
            )
            
            # Trích xuất dạng text cuối cùng
            last_msg = response["messages"][-1]
            content = last_msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text").strip()
            return str(content)
            
        except Exception as e:
            logger.error(f"Agent lỗi ({session_id}): {e}", exc_info=True)
            return f"Xin lỗi bạn, HT nhận diện đã xảy ra sự cố trong quá trình tư vấn: {e}"


# ──────────────────────────────────────────────────────────────────────────
# INTERACTIVE CLI / TEST
# ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*65)
    print("  ⏳ Đang khởi tạo AI ACADEMIC ADVISOR...")
    print("="*65)
    
    agent_app = AcademicAdvisorAgent()
    
    print("\n" + "="*65)
    print("  ✅ AI ACADEMIC ADVISOR — Tư vấn học tập CNTT (Stateful Mode)")
    print("  Gõ 'exit' hoặc 'thoat' để kết thúc.")
    print("="*65 + "\n")
    
    # Tạo session mặc định cho Terminal
    session_id = "terminal_session_01"
    
    while True:
        try:
            user_msg = input("🎓 Sinh viên: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTạm biệt!")
            break
            
        if not user_msg: continue
        if user_msg.lower() in ["exit", "quit", "thoat"]:
            print("Tạm biệt! Chúc bạn học tốt.")
            break
        
        answer = agent_app.chat(session_id, user_msg)
        print(f"\n🤖 Advisor:\n{answer}\n")
        print("-" * 65)
