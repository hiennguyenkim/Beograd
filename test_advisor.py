"""
test_advisor.py
~~~~~~~~~~~~~~~
Script chạy thử (Smoke Test) cho AcademicAdvisorAgent.
"""
import logging
from agent import AcademicAdvisorAgent

# Thiết lập log mức INFO để theo dõi quá trình chạy
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_advisor")

def run_smoke_test():
    logger.info("Đang khởi động AcademicAdvisorAgent cho Smoke Test...")
    agent_app = AcademicAdvisorAgent()
    
    test_session = "smoke_test_01"
    
    print("\n" + "="*65)
    print("  BẮT ĐẦU SMOKE TEST AI ACADEMIC ADVISOR")
    print("="*65)

    # Câu 1: RAG Pipeline (Hỏi về quy định chung - Cần Query Transform + Rerank)
    q1 = "Tổng số tín chỉ cần để ra trường là bao nhiêu?"
    print(f"\n❓ Sinh viên: {q1}")
    print(f"🤖 Advisor: {agent_app.chat(test_session, q1)}")
    
    # Câu 2: Context test (Agent phải nhớ session_id dựa vào câu hỏi 1)
    q2 = "Vậy chuẩn đầu ra tiếng Anh thì thế nào?"
    print(f"\n❓ Sinh viên: {q2} (Test bộ nhớ Context)")
    print(f"🤖 Advisor: {agent_app.chat(test_session, q2)}")
    
    # Câu 3: Neo4j tool test (Hỏi về cấu trúc môn học)
    q3 = "Em muốn học môn Cấu trúc dữ liệu thì cần học gì trước?"
    print(f"\n❓ Sinh viên: {q3} (Test KG Database)")
    print(f"🤖 Advisor: {agent_app.chat(test_session, q3)}")
    
    print("\n" + "="*65)
    print("  Hoàn thành Smoke Test.")
    print("="*65)

if __name__ == "__main__":
    run_smoke_test()
