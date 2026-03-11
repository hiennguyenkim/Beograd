"""
agent.py
========
Agent tối ưu lộ trình học tập dựa trên Neo4j Knowledge Graph.
Dùng llm7.io — OpenAI-compatible free API.

Chạy terminal : python agent.py
Chạy API      : uvicorn agent:app --reload --port 8000
"""

import os
import json
import time
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI

from neo4j_tools import (
    get_learning_path,
    check_prerequisites,
    optimize_semester_plan,
    query_program_info,
    close_driver,
)

# ── Config ────────────────────────────────────────────────────────────────────
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY  = os.environ.get("LLM_API_KEY",  "")           # lấy tại console.groq.com
LLM_MODEL    = os.environ.get("LLM_MODEL",    "llama-3.3-70b-versatile")

TOOL_FUNCTIONS = {
    "get_learning_path":      get_learning_path,
    "check_prerequisites":    check_prerequisites,
    "optimize_semester_plan": optimize_semester_plan,
    "query_program_info":     query_program_info,
}

SYSTEM_PROMPT = """Bạn là trợ lý tư vấn học tập thông minh của trường HCMUE -
Khoa Công nghệ thông tin. Bạn có khả năng truy cập Knowledge Graph chương trình
đào tạo để:
1. Gợi ý lộ trình học phù hợp với mục tiêu nghề nghiệp của sinh viên
2. Kiểm tra điều kiện tiên quyết trước khi đăng ký môn học
3. Lên kế hoạch học tập tối ưu theo số tín chỉ mong muốn
4. Trả lời mọi câu hỏi về chương trình đào tạo

Hãy luôn trả lời bằng tiếng Việt, thân thiện và dễ hiểu.
Dùng tool để lấy dữ liệu thực từ hệ thống trước khi trả lời.
Nếu thiếu thông tin (ví dụ danh sách môn đã học), hãy hỏi lại người dùng."""

# ── Tool schema (OpenAI format) ───────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_learning_path",
            "description": (
                "Gợi ý lộ trình học tập theo mục tiêu nghề nghiệp. "
                "Dùng khi người dùng muốn trở thành lập trình viên, kỹ sư AI, "
                "quản trị mạng, v.v."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Mục tiêu nghề nghiệp, ví dụ: 'lập trình viên', 'AI', 'mạng'",
                    }
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_prerequisites",
            "description": (
                "Kiểm tra điều kiện tiên quyết của một môn học. "
                "Dùng khi hỏi có thể đăng ký môn X không, cần học gì trước môn X."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {
                        "type": "string",
                        "description": "Mã môn học, ví dụ: 'COMP1001'",
                    },
                    "completed_courses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Danh sách mã các môn đã hoàn thành",
                    },
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "optimize_semester_plan",
            "description": (
                "Tối ưu kế hoạch học các môn còn lại theo số tín chỉ mỗi học kỳ. "
                "Dùng khi muốn sắp xếp lịch học dựa trên môn đã hoàn thành."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "completed_courses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Danh sách mã các môn đã hoàn thành",
                    },
                    "target_credits_per_semester": {
                        "type": "integer",
                        "description": "Số tín chỉ mục tiêu mỗi học kỳ (mặc định 18)",
                    },
                    "max_credits_per_semester": {
                        "type": "integer",
                        "description": "Số tín chỉ tối đa mỗi học kỳ (mặc định 21)",
                    },
                },
                "required": ["completed_courses"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_program_info",
            "description": (
                "Hỏi đáp tự do về chương trình đào tạo: môn học, PLO, "
                "học kỳ, vị trí việc làm, tổng tín chỉ, môn tự chọn, v.v."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Câu hỏi về chương trình đào tạo",
                    }
                },
                "required": ["question"],
            },
        },
    },
]


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  LEARNING PATH AGENT                                                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class LearningPathAgent:

    def __init__(self):
        self.client  = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        print(f"✓ LearningPathAgent sẵn sàng ({LLM_MODEL} via Groq)")

    def _execute_tool(self, tool_name: str, tool_args: dict) -> str:
        fn = TOOL_FUNCTIONS.get(tool_name)
        if not fn:
            return json.dumps({"error": f"Tool '{tool_name}' không tồn tại"})
        try:
            return json.dumps(fn(**tool_args), ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def chat(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})

        # Vòng lặp agentic
        while True:
            # Retry khi bị rate limit
            for attempt in range(3):
                try:
                    response = self.client.chat.completions.create(
                        model=LLM_MODEL,
                        messages=self.history,
                        tools=TOOLS,
                        tool_choice="auto",
                        temperature=0.2,
                    )
                    break
                except Exception as e:
                    if "429" in str(e) and attempt < 2:
                        wait = 15 * (attempt + 1)
                        print(f"   ⏳ Rate limit, chờ {wait}s...")
                        time.sleep(wait)
                    else:
                        raise

            msg        = response.choices[0].message
            tool_calls = msg.tool_calls

            if not tool_calls:
                # Câu trả lời cuối
                self.history.append({"role": "assistant", "content": msg.content})
                return msg.content or ""

            # Lưu assistant turn
            self.history.append(msg)

            # Thực thi từng tool
            for tc in tool_calls:
                tool_name = tc.function.name
                tool_args = json.loads(tc.function.arguments)
                print(f"   🔧 Tool: {tool_name}({list(tool_args.keys())})")

                result = self._execute_tool(tool_name, tool_args)
                self.history.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result,
                })

    def reset(self):
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        print("✓ Đã reset lịch sử hội thoại")


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TERMINAL CHAT                                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def run_terminal():
    print("\n" + "=" * 60)
    print("  TRỢ LÝ TƯ VẤN HỌC TẬP — HCMUE CNTT")
    print("  Gõ 'quit' để thoát | 'reset' để bắt đầu lại")
    print("=" * 60)

    agent = LearningPathAgent()

    print("\nXin chào! Tôi có thể giúp bạn:")
    print("  • Gợi ý lộ trình học theo mục tiêu nghề nghiệp")
    print("  • Kiểm tra điều kiện tiên quyết môn học")
    print("  • Lên kế hoạch học tập tối ưu")
    print("  • Trả lời câu hỏi về chương trình đào tạo\n")

    while True:
        try:
            user_input = input("Bạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Tạm biệt!")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("👋 Tạm biệt!")
            break
        if user_input.lower() == "reset":
            agent.reset()
            continue

        print("Agent: ", end="", flush=True)
        try:
            print(agent.chat(user_input))
        except Exception as e:
            print(f"❌ Lỗi: {e}")
        print()

    close_driver()


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  FASTAPI                                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    app = FastAPI(
        title="Learning Path Agent API",
        description="API tư vấn lộ trình học tập HCMUE CNTT",
        version="1.0.0",
    )
    app.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["*"], allow_headers=["*"])

    _sessions: dict[str, LearningPathAgent] = {}

    class ChatRequest(BaseModel):
        session_id: str = "default"
        message:    str

    class ChatResponse(BaseModel):
        session_id: str
        message:    str
        response:   str

    @app.post("/chat", response_model=ChatResponse)
    async def chat_endpoint(req: ChatRequest):
        if req.session_id not in _sessions:
            _sessions[req.session_id] = LearningPathAgent()
        try:
            resp = _sessions[req.session_id].chat(req.message)
            return ChatResponse(session_id=req.session_id,
                                message=req.message, response=resp)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/chat/{session_id}")
    async def reset_session(session_id: str):
        if session_id in _sessions:
            _sessions[session_id].reset()
        return {"status": "ok", "session_id": session_id}

    @app.get("/health")
    async def health():
        return {"status": "ok", "model": LLM_MODEL, "provider": "groq"}

    @app.get("/tools")
    async def list_tools():
        return {"tools": list(TOOL_FUNCTIONS.keys())}

except ImportError:
    app = None


if __name__ == "__main__":
    run_terminal()