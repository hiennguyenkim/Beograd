"""
extraction.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Module trích xuất dữ liệu từ file PDF Chương trình đào tạo
và xây dựng Knowledge Graph chi tiết trên Neo4j.

Pipeline 3 giai đoạn:
  Stage 1 – Mapping  : Đọc bảng kế hoạch → danh sách mã môn + thông số định lượng.
  Stage 2 – Deep Mining: Khai thác mô tả tóm tắt học phần (số chương, bài TH, công cụ).
  Stage 3 – Logic Alignment: Chuẩn hóa quan hệ tiên quyết / học-trước / song-hành.

Guardrails:
  - Identity key = ma_mon  → không tạo node trùng.
  - so_tin_chi, giờ học   → luôn Integer.
  - Zero-Inference         → không suy diễn thêm nội dung.
"""

# ──────────────────────────────────────────────────────────────────────────
# 0. IMPORTS
# ──────────────────────────────────────────────────────────────────────────
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pdfplumber

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from neo4j import Driver, GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable
from pydantic import BaseModel, Field, field_validator

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────
# 1. LOGGING
# ──────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("curriculum_parser")


# ──────────────────────────────────────────────────────────────────────────
# 2. PYDANTIC SCHEMAS
# ──────────────────────────────────────────────────────────────────────────

class AcademicProgram(BaseModel):
    """Thông tin chung của toàn chương trình đào tạo (AcademicProgram node)."""

    ma_nganh: str = Field(..., description="Mã ngành đào tạo, ví dụ: '7480201'")
    ten_nganh_vn: str = Field(..., description="Tên ngành bằng tiếng Việt")
    ten_nganh_en: Optional[str] = Field(None, description="Tên ngành bằng tiếng Anh")
    tong_tin_chi: int = Field(..., description="Tổng số tín chỉ tích lũy yêu cầu, ví dụ: 124")
    thoi_gian_dao_tao: str = Field(..., description="Thời gian đào tạo thiết kế, ví dụ: '4 năm (8 học kỳ)'")
    ten_van_bang_vn: Optional[str] = Field(None, description="Tên văn bằng tốt nghiệp tiếng Việt")
    ten_van_bang_en: Optional[str] = Field(None, description="Tên văn bằng tốt nghiệp tiếng Anh")
    ty_le_truc_tuyen_toi_da: Optional[str] = Field(
        None, description="Tỷ lệ học trực tuyến tối đa, ví dụ: '30%'"
    )
    thang_diem: Optional[str] = Field(
        None, description="Thang điểm đánh giá, ví dụ: 'Thang 10, làm tròn 1 chữ số thập phân'"
    )
    chuan_ngoai_ngu: Optional[str] = Field(
        None, description="Chuẩn đầu ra ngoại ngữ yêu cầu, ví dụ: 'Bậc 3 theo khung 6 bậc của Việt Nam'"
    )


class CourseHours(BaseModel):
    """Phân bổ giờ dạy học theo hình thức."""

    ly_thuyet_truc_tiep: int = Field(0, description="Số giờ lý thuyết dạy trực tiếp trên lớp")
    ly_thuyet_truc_tuyen: int = Field(0, description="Số giờ lý thuyết dạy trực tuyến (online)")
    thuc_hanh_thao_luan: int = Field(0, description="Số giờ thực hành / thảo luận")
    tu_hoc: int = Field(0, description="Số giờ tự học (= Tổng giờ − Trực tiếp − Trực tuyến)")

    @field_validator("ly_thuyet_truc_tiep", "ly_thuyet_truc_tuyen", "thuc_hanh_thao_luan", "tu_hoc", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> int:
        """Ép kiểu về int, xử lý None và string rỗng."""
        if v is None or v == "":
            return 0
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            return 0


class CourseRich(BaseModel):
    """Thông tin đầy đủ của một học phần (Course node) — schema 'giàu'."""

    # Định danh
    ma_mon: str = Field(..., description="Mã học phần duy nhất (primary key), ví dụ: 'COMP1010'")
    ten_mon: str = Field(..., description="Tên học phần đầy đủ")
    so_tin_chi: int = Field(..., description="Số tín chỉ (Integer ≥ 1)")
    loai_mon: str = Field(
        "Bắt buộc",
        description="Phân loại môn học: 'Bắt buộc' hoặc 'Tự chọn'",
    )

    # Phân bổ giờ
    gio_hoc: CourseHours = Field(
        default_factory=CourseHours,
        description="Phân bổ giờ dạy học chi tiết theo từng hình thức",
    )

    # Quản lý & lộ trình
    don_vi_quan_ly: Optional[str] = Field(
        None, description="Tên Khoa/Bộ môn quản lý học phần này"
    )
    hoc_ky_du_kien: Optional[int] = Field(
        None,
        ge=1,
        le=8,
        description="Học kỳ dự kiến giảng dạy (1–8)",
    )

    # Nội hàm — trích từ phần 8 mô tả tóm tắt
    mo_ta_tom_tat: Optional[str] = Field(
        None, description="Mô tả tóm tắt nội dung học phần (≤ 300 ký tự)"
    )
    so_chuong_ly_thuyet: Optional[int] = Field(
        None, description="Số chương lý thuyết (đếm từ cụm 'X chương', 'X phần' trong mô tả)"
    )
    so_bai_thuc_hanh_chi_tiet: Optional[int] = Field(
        None,
        description="Số bài thực hành/lab chi tiết (đếm từ cụm 'X bài', 'X lab' trong mô tả)",
    )
    ngon_ngu_cong_cu: List[str] = Field(
        default_factory=list,
        description=(
            "Danh sách ngôn ngữ lập trình / công cụ / framework xuất hiện trong mô tả. "
            "Ví dụ: ['Python', 'SQL Server', 'Agile', 'Scrum', 'OpenCV']"
        ),
    )

    # Quan hệ (lưu mã môn liên quan — xử lý thành edge khi nạp vào Neo4j)
    mon_tien_quyet: List[str] = Field(
        default_factory=list,
        description="Danh sách mã môn học là điều kiện TIÊN QUYẾT (Prerequisite) — phải học & qua trước.",
    )
    mon_hoc_truoc: List[str] = Field(
        default_factory=list,
        description="Danh sách mã môn học nên học TRƯỚC (Take-before) — khuyến nghị, không bắt buộc.",
    )
    mon_song_hanh: List[str] = Field(
        default_factory=list,
        description="Danh sách mã môn được học SONG HÀNH (Co-requisite) — học cùng học kỳ.",
    )
    dap_ung_plo: List[str] = Field(
        default_factory=list,
        description="Danh sách mã PLO mà học phần này đóng góp vào (từ ma trận PLO × Môn học).",
    )

    @field_validator("so_tin_chi", "so_chuong_ly_thuyet", "so_bai_thuc_hanh_chi_tiet", mode="before")
    @classmethod
    def coerce_int(cls, v: Any) -> Any:
        if v is None or v == "":
            return v
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            return v


class AcademicRule(BaseModel):
    """Một quy tắc học vụ trích xuất từ phần Quy định chung."""

    loai_quy_tac: str = Field(
        ...,
        description=(
            "Phân loại quy tắc: 'khoa_luan' | 'cai_thien_diem' | 'hoc_vuot' | 'roi_mon' | 'khac'"
        ),
    )
    mo_ta: str = Field(..., description="Nội dung nguyên văn hoặc tóm tắt quy tắc")


class ExtractionStage1(BaseModel):
    """Output của Stage 1 — Mapping từ bảng kế hoạch đào tạo."""

    program: AcademicProgram
    courses: List[CourseRich]
    rules: List[AcademicRule] = Field(default_factory=list)


class ExtractionStage2Update(BaseModel):
    """Output của Stage 2 — Deep Mining bổ sung nội hàm cho một nhóm môn."""

    updates: List[Dict[str, Any]] = Field(
        ...,
        description=(
            "Danh sách cập nhật. Mỗi phần tử là dict có key 'ma_mon' và "
            "các field cần cập nhật: mo_ta_tom_tat, so_chuong_ly_thuyet, "
            "so_bai_thuc_hanh_chi_tiet, ngon_ngu_cong_cu."
        ),
    )


# ──────────────────────────────────────────────────────────────────────────
# 3. PDF EXTRACTION HELPERS
# ──────────────────────────────────────────────────────────────────────────

def extract_all_pages(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Đọc toàn bộ PDF, trả về list các dict:
      {'page': int, 'text': str, 'tables': list[list[list]]}
    """
    logger.info(f"Mở PDF: {pdf_path}")
    pages_data: List[Dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        logger.info(f"PDF có {total} trang.")
        for i, page in enumerate(pdf.pages):
            logger.debug(f"  Đang đọc trang {i + 1}/{total}...")
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            pages_data.append({"page": i + 1, "text": text, "tables": tables})
    logger.info("Hoàn thành đọc PDF.")
    return pages_data


def _pages_to_text_block(pages_data: List[Dict], from_page: int, to_page: int) -> str:
    """Ghép text từ trang from_page đến to_page (1-indexed, inclusive)."""
    chunks = []
    for p in pages_data:
        if from_page <= p["page"] <= to_page:
            chunks.append(f"[Trang {p['page']}]\n{p['text']}")
    return "\n\n".join(chunks)


def _tables_in_range(pages_data: List[Dict], from_page: int, to_page: int) -> List[List[List]]:
    """Thu thập tất cả bảng trong khoảng trang chỉ định."""
    tables = []
    for p in pages_data:
        if from_page <= p["page"] <= to_page:
            tables.extend(p.get("tables", []))
    return tables


def _safe_json_parse(raw: str) -> Any:
    """Parse JSON từ LLM output — tách code fence nếu cần."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


# ──────────────────────────────────────────────────────────────────────────
# 4. LLM SETUP
# ──────────────────────────────────────────────────────────────────────────

def build_llm() -> ChatGoogleGenerativeAI:
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL", "gemini-2.5-flash")
    if not api_key:
        raise EnvironmentError("Thiếu LLM_API_KEY trong .env")
    logger.info(f"Khởi tạo LLM: {model}")
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=0,
        max_retries=3,
    )


# ──────────────────────────────────────────────────────────────────────────
# 5. STAGE 1 — MAPPING (Bảng kế hoạch đào tạo)
# ──────────────────────────────────────────────────────────────────────────

_STAGE1_SYSTEM = """Bạn là chuyên gia phân tích chương trình đào tạo đại học Việt Nam.
Nhiệm vụ: Trích xuất TẤT CẢ thông tin từ văn bản PDF được cung cấp.

[QUỲ TẬC BẮT BUỘC]
- Trả về JSON hợp lệ theo đúng schema bên dưới — tuyệt đối không thêm text ngoài JSON.
- Không suy diễn (Zero-Inference): chỉ lấy những gì có trong văn bản.
- so_tin_chi, gio_hoc.*: phải là số nguyên (int), không phải chuỗi.
- ma_mon là khóa chính duy nhất — nếu trùng mã thì gộp, không tạo 2 bản.
- loai_mon: "Bắt buộc" hoặc "Tự chọn". Nếu không rõ, mặc định "Bắt buộc".
- Quan hệ mon_tien_quyet / mon_hoc_truoc / mon_song_hanh: điền mã môn, không phải tên.
- hoc_ky_du_kien: số nguyên 1–8 tương ứng học kỳ. Null nếu không rõ.

[SCHEMA]
{{
  "program": {{
    "ma_nganh": "str",
    "ten_nganh_vn": "str",
    "ten_nganh_en": "str | null",
    "tong_tin_chi": "int",
    "thoi_gian_dao_tao": "str",
    "ten_van_bang_vn": "str | null",
    "ten_van_bang_en": "str | null",
    "ty_le_truc_tuyen_toi_da": "str | null",
    "thang_diem": "str | null",
    "chuan_ngoai_ngu": "str | null"
  }},
  "courses": [
    {{
      "ma_mon": "str",
      "ten_mon": "str",
      "so_tin_chi": "int",
      "loai_mon": "Bắt buộc | Tự chọn",
      "gio_hoc": {{
        "ly_thuyet_truc_tiep": "int",
        "ly_thuyet_truc_tuyen": "int",
        "thuc_hanh_thao_luan": "int",
        "tu_hoc": "int"
      }},
      "don_vi_quan_ly": "str | null",
      "hoc_ky_du_kien": "int | null",
      "mon_tien_quyet": ["str"],
      "mon_hoc_truoc": ["str"],
      "mon_song_hanh": ["str"],
      "dap_ung_plo": ["str"]
    }}
  ],
  "rules": [
    {{ "loai_quy_tac": "str", "mo_ta": "str" }}
  ]
}}
"""

_STAGE1_HUMAN = """Văn bản chương trình đào tạo (có thể bao gồm bảng):
{text}

Trả về duy nhất JSON theo schema đã mô tả."""


def run_stage1(llm: ChatGoogleGenerativeAI, pages_data: List[Dict]) -> ExtractionStage1:
    """
    Stage 1 — Mapping:
    Đọc toàn bộ nội dung PDF (trang 1–42) → trích xuất thông tin chương trình
    và danh sách học phần kèm thông số định lượng.
    """
    logger.info("=== STAGE 1: MAPPING ===")
    # Ghép toàn bộ text + tables (pages 1 → tất cả)
    full_text = _pages_to_text_block(pages_data, 1, len(pages_data))
    # Giới hạn kích thước context — lấy 60000 ký tự đầu để không vượt token limit
    full_text = full_text[:60000]

    prompt = ChatPromptTemplate.from_messages([
        ("system", _STAGE1_SYSTEM),
        ("human", _STAGE1_HUMAN),
    ])
    structured_llm = llm.with_structured_output(ExtractionStage1)
    chain = prompt | structured_llm

    logger.info("  Gửi Stage 1 đến LLM...")
    try:
        result: ExtractionStage1 = chain.invoke({"text": full_text})
        logger.info(
            f"  Stage 1 kết quả: {len(result.courses)} học phần, "
            f"{len(result.rules)} quy tắc."
        )
        return result
    except Exception as e:
        logger.error(f"Stage 1 thất bại: {e}", exc_info=True)
        raise


# ──────────────────────────────────────────────────────────────────────────
# 6. STAGE 2 — DEEP MINING (Phần 8: Mô tả tóm tắt học phần)
# ──────────────────────────────────────────────────────────────────────────

_STAGE2_SYSTEM = """Bạn là chuyên gia phân tích nội dung học phần đại học.
Nhiệm vụ: Với danh sách mã môn được cung cấp, hãy TÌM KIẾM trong đoạn văn bản phần mô tả tóm tắt
và trích xuất thông tin chi tiết NỘI HÀM của từng môn.

[QUỲ TẬC BẮT BUỘC]
- Chỉ lấy thông tin CÓ TRONG đoạn văn bản — Zero-Inference.
- so_chuong_ly_thuyet: đếm số chương/phần lý thuyết (int). Null nếu không đề cập.
- so_bai_thuc_hanh_chi_tiet: đếm số bài/lab thực hành (int). Null nếu không đề cập.
- ngon_ngu_cong_cu: các từ khóa như C++, Python, Java, SQL Server, Oracle, OpenCV, Agile, Scrum, etc.
- mo_ta_tom_tat: tóm tắt ngắn (≤ 300 ký tự). Null nếu không có mô tả.
- Nếu một mã môn không xuất hiện trong văn bản, vẫn trả về entry với các trường null/[].

[SCHEMA]
{{
  "updates": [
    {{
      "ma_mon": "str",
      "mo_ta_tom_tat": "str | null",
      "so_chuong_ly_thuyet": "int | null",
      "so_bai_thuc_hanh_chi_tiet": "int | null",
      "ngon_ngu_cong_cu": ["str"]
    }}
  ]
}}
"""

_STAGE2_HUMAN = """Danh sách mã môn cần khai thác:
{ma_mon_list}

Văn bản mô tả học phần:
{text}

Trả về duy nhất JSON theo schema đã mô tả."""


def run_stage2(
    llm: ChatGoogleGenerativeAI,
    pages_data: List[Dict],
    stage1_result: ExtractionStage1,
    batch_size: int = 15,
) -> ExtractionStage1:
    """
    Stage 2 — Deep Mining:
    Khai thác phần mô tả tóm tắt học phần để bổ sung nội hàm.
    Xử lý theo batch để tránh vượt token limit.
    """
    logger.info("=== STAGE 2: DEEP MINING ===")

    # Lấy phần text từ nửa sau PDF — nơi thường chứa mô tả học phần
    mid = max(1, len(pages_data) // 2)
    description_text = _pages_to_text_block(pages_data, mid, len(pages_data))

    ma_mons = [c.ma_mon for c in stage1_result.courses]
    course_map: Dict[str, CourseRich] = {c.ma_mon: c for c in stage1_result.courses}

    # Build chain
    prompt = ChatPromptTemplate.from_messages([
        ("system", _STAGE2_SYSTEM),
        ("human", _STAGE2_HUMAN),
    ])
    structured_llm = llm.with_structured_output(ExtractionStage2Update)
    chain = prompt | structured_llm

    # Batch processing
    total_batches = (len(ma_mons) + batch_size - 1) // batch_size
    for batch_idx in range(total_batches):
        batch = ma_mons[batch_idx * batch_size: (batch_idx + 1) * batch_size]
        logger.info(f"  Batch {batch_idx + 1}/{total_batches}: {batch}")
        try:
            result: ExtractionStage2Update = chain.invoke({
                "ma_mon_list": ", ".join(batch),
                "text": description_text[:40000],
            })
            for upd in result.updates:
                code = upd.get("ma_mon", "")
                if code in course_map:
                    c = course_map[code]
                    if upd.get("mo_ta_tom_tat"):
                        c.mo_ta_tom_tat = upd["mo_ta_tom_tat"]
                    if upd.get("so_chuong_ly_thuyet") is not None:
                        c.so_chuong_ly_thuyet = int(upd["so_chuong_ly_thuyet"])
                    if upd.get("so_bai_thuc_hanh_chi_tiet") is not None:
                        c.so_bai_thuc_hanh_chi_tiet = int(upd["so_bai_thuc_hanh_chi_tiet"])
                    tools = upd.get("ngon_ngu_cong_cu", [])
                    if tools:
                        c.ngon_ngu_cong_cu = tools
            logger.info(f"    Cập nhật {len(result.updates)} học phần.")
        except Exception as e:
            logger.warning(f"  Batch {batch_idx + 1} lỗi: {e}")

    logger.info("=== Stage 2 hoàn thành ===")
    return stage1_result


# ──────────────────────────────────────────────────────────────────────────
# 7. STAGE 3 — LOGIC ALIGNMENT (Chuẩn hóa quan hệ)
# ──────────────────────────────────────────────────────────────────────────

def run_stage3(stage2_result: ExtractionStage1) -> ExtractionStage1:
    """
    Stage 3 — Logic Alignment:
    Chuẩn hóa quan hệ tiên quyết theo nguyên tắc:
      - Nếu môn A có mon_tien_quyet = [B], thì edge hướng: (B)→[:TIEN_QUYET]→(A)
        (B phải hoàn thành TRƯỚC khi học A)
    Kiểm tra & loại bỏ mã môn không tồn tại trong danh sách.
    """
    logger.info("=== STAGE 3: LOGIC ALIGNMENT ===")
    valid_codes = {c.ma_mon for c in stage2_result.courses}
    cleaned = 0

    for course in stage2_result.courses:
        for field_name in ("mon_tien_quyet", "mon_hoc_truoc", "mon_song_hanh", "dap_ung_plo"):
            original: List[str] = getattr(course, field_name)
            filtered = [
                code for code in original
                # Giữ mã môn hợp lệ hoặc PLO (bắt đầu bằng PLO)
                if code in valid_codes or code.startswith("PLO")
            ]
            if len(filtered) < len(original):
                removed = set(original) - set(filtered)
                logger.warning(
                    f"  [{course.ma_mon}] Loại {len(removed)} mã không hợp lệ khỏi '{field_name}': {removed}"
                )
                cleaned += len(original) - len(filtered)
            setattr(course, field_name, filtered)

    logger.info(f"Stage 3 hoàn thành. Đã làm sạch {cleaned} tham chiếu không hợp lệ.")
    return stage2_result


# ──────────────────────────────────────────────────────────────────────────
# 8. NEO4J INGESTION
# ──────────────────────────────────────────────────────────────────────────

_NEO4J_CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:AcademicProgram)  REQUIRE n.ma_nganh  IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Course)           REQUIRE n.ma_mon    IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Khoa)             REQUIRE n.ten       IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:PLO)              REQUIRE n.ma_plo    IS UNIQUE",
]


def get_neo4j_driver_adv() -> Driver:
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USERNAME")
    pwd = os.getenv("NEO4J_PASSWORD")
    if not all([uri, user, pwd]):
        raise EnvironmentError("Thiếu NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD trong .env")
    try:
        driver = GraphDatabase.driver(uri, auth=(user, pwd))
        driver.verify_connectivity()
        logger.info(f"Neo4j kết nối thành công: {uri}")
        return driver
    except AuthError as e:
        logger.error(f"Xác thực Neo4j thất bại: {e}")
        raise
    except ServiceUnavailable as e:
        logger.error(f"Neo4j không khả dụng tại {uri}: {e}")
        raise


def setup_constraints(driver: Driver) -> None:
    logger.info("Thiết lập Neo4j constraints...")
    with driver.session() as s:
        for q in _NEO4J_CONSTRAINTS:
            try:
                s.run(q)
            except Exception as e:
                logger.debug(f"  Constraint: {e}")
    logger.info("Constraints sẵn sàng.")


def ingest_program(session: Any, program: AcademicProgram) -> None:
    session.run(
        """
        MERGE (p:AcademicProgram {ma_nganh: $ma_nganh})
        SET p.ten_nganh_vn            = $ten_nganh_vn,
            p.ten_nganh_en            = $ten_nganh_en,
            p.tong_tin_chi            = $tong_tin_chi,
            p.thoi_gian_dao_tao       = $thoi_gian_dao_tao,
            p.ten_van_bang_vn         = $ten_van_bang_vn,
            p.ten_van_bang_en         = $ten_van_bang_en,
            p.ty_le_truc_tuyen_toi_da = $ty_le_truc_tuyen_toi_da,
            p.thang_diem              = $thang_diem,
            p.chuan_ngoai_ngu         = $chuan_ngoai_ngu
        """,
        **program.model_dump(),
    )
    logger.info(f"  Đã MERGE AcademicProgram: {program.ma_nganh}")


def ingest_courses(session: Any, courses: List[CourseRich]) -> None:
    logger.info(f"  Nạp {len(courses)} Course nodes...")
    rows = []
    for c in courses:
        rows.append({
            "ma_mon":                   c.ma_mon,
            "ten_mon":                  c.ten_mon,
            "so_tin_chi":               c.so_tin_chi,
            "loai_mon":                 c.loai_mon,
            "don_vi_quan_ly":           c.don_vi_quan_ly,
            "hoc_ky_du_kien":           c.hoc_ky_du_kien,
            "mo_ta_tom_tat":            c.mo_ta_tom_tat,
            "so_chuong_ly_thuyet":      c.so_chuong_ly_thuyet,
            "so_bai_thuc_hanh":         c.so_bai_thuc_hanh_chi_tiet,
            "ngon_ngu_cong_cu":         c.ngon_ngu_cong_cu,
            "ly_thuyet_truc_tiep":      c.gio_hoc.ly_thuyet_truc_tiep,
            "ly_thuyet_truc_tuyen":     c.gio_hoc.ly_thuyet_truc_tuyen,
            "thuc_hanh_thao_luan":      c.gio_hoc.thuc_hanh_thao_luan,
            "tu_hoc":                   c.gio_hoc.tu_hoc,
        })

    session.run(
        """
        UNWIND $rows AS r
        MERGE (c:Course {ma_mon: r.ma_mon})
        SET c.ten_mon               = r.ten_mon,
            c.so_tin_chi            = r.so_tin_chi,
            c.loai_mon              = r.loai_mon,
            c.don_vi_quan_ly        = r.don_vi_quan_ly,
            c.hoc_ky_du_kien        = r.hoc_ky_du_kien,
            c.mo_ta_tom_tat         = r.mo_ta_tom_tat,
            c.so_chuong_ly_thuyet   = r.so_chuong_ly_thuyet,
            c.so_bai_thuc_hanh      = r.so_bai_thuc_hanh,
            c.ngon_ngu_cong_cu      = r.ngon_ngu_cong_cu,
            c.gio_truc_tiep         = r.ly_thuyet_truc_tiep,
            c.gio_truc_tuyen        = r.ly_thuyet_truc_tuyen,
            c.gio_thuc_hanh         = r.thuc_hanh_thao_luan,
            c.gio_tu_hoc            = r.tu_hoc
        """,
        rows=rows,
    )
    logger.info(f"  Đã MERGE {len(rows)} Course nodes.")


def ingest_khoa_edges(session: Any, courses: List[CourseRich]) -> None:
    """(Course)-[:THUOC_KHOA]->(Khoa)"""
    rows = [
        {"ma_mon": c.ma_mon, "khoa": c.don_vi_quan_ly}
        for c in courses if c.don_vi_quan_ly
    ]
    if not rows:
        return
    session.run(
        """
        UNWIND $rows AS r
        MERGE (k:Khoa {ten: r.khoa})
        WITH k, r
        MATCH (c:Course {ma_mon: r.ma_mon})
        MERGE (c)-[:THUOC_KHOA]->(k)
        """,
        rows=rows,
    )
    logger.info(f"  Đã tạo {len(rows)} THUOC_KHOA edges.")


def ingest_prerequisite_edges(session: Any, courses: List[CourseRich]) -> None:
    """
    (MonHoc)-[:HOC_TRUOC]->(MonHoc)
    Nếu A.mon_tien_quyet = [B] → edge (B)-[:HOC_TRUOC]->(A)
    """
    rows = []
    for c in courses:
        for pre in c.mon_tien_quyet:
            rows.append({"source": pre, "target": c.ma_mon, "rel": "TIEN_QUYET"})
        for before in c.mon_hoc_truoc:
            rows.append({"source": before, "target": c.ma_mon, "rel": "HOC_TRUOC"})
    if not rows:
        logger.info("  Không có quan hệ tiên quyết / học trước.")
        return
    session.run(
        """
        UNWIND $rows AS r
        MATCH (src:Course {ma_mon: r.source})
        MATCH (tgt:Course {ma_mon: r.target})
        CALL apoc.merge.relationship(src, r.rel, {}, {}, tgt, {}) YIELD rel
        RETURN count(rel)
        """,
        rows=rows,
    )
    logger.info(f"  Đã tạo {len(rows)} TIEN_QUYET / HOC_TRUOC edges.")


def ingest_prerequisite_edges_no_apoc(session: Any, courses: List[CourseRich]) -> None:
    """Fallback không dùng APOC — tạo từng loại relationship riêng."""
    tq_rows, ht_rows = [], []
    for c in courses:
        for pre in c.mon_tien_quyet:
            tq_rows.append({"source": pre, "target": c.ma_mon})
        for before in c.mon_hoc_truoc:
            ht_rows.append({"source": before, "target": c.ma_mon})

    if tq_rows:
        session.run(
            """
            UNWIND $rows AS r
            MATCH (src:Course {ma_mon: r.source})
            MATCH (tgt:Course {ma_mon: r.target})
            MERGE (src)-[:TIEN_QUYET]->(tgt)
            """,
            rows=tq_rows,
        )
        logger.info(f"  Đã tạo {len(tq_rows)} TIEN_QUYET edges.")
    if ht_rows:
        session.run(
            """
            UNWIND $rows AS r
            MATCH (src:Course {ma_mon: r.source})
            MATCH (tgt:Course {ma_mon: r.target})
            MERGE (src)-[:HOC_TRUOC]->(tgt)
            """,
            rows=ht_rows,
        )
        logger.info(f"  Đã tạo {len(ht_rows)} HOC_TRUOC edges.")


def ingest_corequisite_edges(session: Any, courses: List[CourseRich]) -> None:
    """(MonHoc)-[:SONG_HANH]->(MonHoc)"""
    rows = []
    for c in courses:
        for co in c.mon_song_hanh:
            rows.append({"a": c.ma_mon, "b": co})
    if not rows:
        return
    session.run(
        """
        UNWIND $rows AS r
        MATCH (a:Course {ma_mon: r.a})
        MATCH (b:Course {ma_mon: r.b})
        MERGE (a)-[:SONG_HANH]->(b)
        """,
        rows=rows,
    )
    logger.info(f"  Đã tạo {len(rows)} SONG_HANH edges.")


def ingest_plo_edges(session: Any, courses: List[CourseRich]) -> None:
    """(MonHoc)-[:DAP_UNG_PLO]->(ChuanDauRa)"""
    rows = []
    for c in courses:
        for plo in c.dap_ung_plo:
            rows.append({"ma_mon": c.ma_mon, "ma_plo": plo})
    if not rows:
        return
    session.run(
        """
        UNWIND $rows AS r
        MERGE (plo:PLO {ma_plo: r.ma_plo})
        WITH plo, r
        MATCH (c:Course {ma_mon: r.ma_mon})
        MERGE (c)-[:DAP_UNG_PLO]->(plo)
        """,
        rows=rows,
    )
    logger.info(f"  Đã tạo {len(rows)} DAP_UNG_PLO edges.")


def ingest_to_neo4j(driver: Driver, final_result: ExtractionStage1) -> None:
    """Master ingestion — nạp toàn bộ dữ liệu vào Neo4j."""
    logger.info("=== NEO4J INGESTION ===")
    setup_constraints(driver)

    with driver.session() as session:
        ingest_program(session, final_result.program)
        ingest_courses(session, final_result.courses)
        ingest_khoa_edges(session, final_result.courses)
        ingest_corequisite_edges(session, final_result.courses)
        ingest_plo_edges(session, final_result.courses)
        # Thử dùng APOC; nếu không có thì fallback
        try:
            ingest_prerequisite_edges(session, final_result.courses)
        except Exception as apoc_err:
            logger.warning(f"APOC không khả dụng ({apoc_err}), dùng fallback Cypher...")
            ingest_prerequisite_edges_no_apoc(session, final_result.courses)

    logger.info("=== INGESTION HOÀN THÀNH ===")


# ──────────────────────────────────────────────────────────────────────────
# 9. ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────

def run_pipeline(pdf_path: str) -> ExtractionStage1:
    """
    Chạy toàn bộ pipeline:
      PDF → Stage1 → Stage2 → Stage3 → Neo4j
    """
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"Không tìm thấy file PDF: {pdf_path}")

    logger.info("=" * 60)
    logger.info("BẮT ĐẦU ADVANCED CURRICULUM PARSER")
    logger.info(f"Input: {pdf_path}")
    logger.info("=" * 60)

    # Đọc PDF
    pages_data = extract_all_pages(pdf_path)

    # Khởi tạo LLM
    llm = build_llm()

    # Stage 1: Mapping
    stage1 = run_stage1(llm, pages_data)

    # Stage 2: Deep Mining
    stage2 = run_stage2(llm, pages_data, stage1)

    # Stage 3: Logic Alignment
    final = run_stage3(stage2)

    # Nạp vào Neo4j
    driver = get_neo4j_driver_adv()
    ingest_to_neo4j(driver, final)
    driver.close()

    # Lưu kết quả JSON để kiểm tra
    out_path = Path("data/processed/curriculum_extracted.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final.model_dump(), f, ensure_ascii=False, indent=2)
    logger.info(f"Đã lưu JSON kết quả tại: {out_path}")

    logger.info("=" * 60)
    logger.info("PIPELINE HOÀN THÀNH THÀNH CÔNG")
    logger.info(f"  → {len(final.courses)} học phần đã nạp vào Neo4j")
    logger.info("=" * 60)
    return final

if __name__ == "__main__":
    PDF = "scripts/chuong_trinh_dao_tao.pdf"
    run_pipeline(PDF)
