"""
tools.py
~~~~~~~~
Tập hợp tất cả @tool được Agent sử dụng để trả lời câu hỏi sinh viên.

Hai nhóm tool:
  1. Neo4j Graph Tools  — truy vấn Knowledge Graph: môn học, tiên quyết, lộ trình...
  2. RAG Pipeline Tool  — tìm kiếm lai (BM25 + FAISS) + Reranking từ JSON curriculum.

Cách hoạt động:
  - Mỗi tool được đăng ký với @tool của LangChain.
  - agent.py chỉ cần `from tools import ALL_TOOLS` rồi truyền vào create_react_agent.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_classic.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_google_genai import ChatGoogleGenerativeAI
from neo4j import GraphDatabase, Driver
from neo4j.exceptions import AuthError, ServiceUnavailable

load_dotenv()

logger = logging.getLogger("tools")


# ──────────────────────────────────────────────────────────────────────────
# DB CONNECTION
# ──────────────────────────────────────────────────────────────────────────

def get_neo4j_driver() -> Driver:
    """Khởi tạo kết nối Neo4j từ biến môi trường."""
    uri  = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USERNAME")
    pwd  = os.getenv("NEO4J_PASSWORD")
    if not all([uri, user, pwd]):
        raise EnvironmentError("Thiếu NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD trong .env")
    try:
        driver = GraphDatabase.driver(uri, auth=(user, pwd))
        driver.verify_connectivity()
        return driver
    except AuthError as e:
        logger.error(f"Xác thực Neo4j thất bại: {e}")
        raise
    except ServiceUnavailable as e:
        logger.error(f"Neo4j không khả dụng tại {uri}: {e}")
        raise


# ──────────────────────────────────────────────────────────────────────────
# HELPER
# ──────────────────────────────────────────────────────────────────────────

def _extract_text(content) -> str:
    """Trích xuất plain text từ AIMessage.content (str hoặc list[dict])."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            p.get("text", "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        return "\n".join(parts).strip()
    return str(content)


# ──────────────────────────────────────────────────────────────────────────
# NEO4J TOOLS
# ──────────────────────────────────────────────────────────────────────────

@tool
def tim_mon_theo_ky(hoc_ky: int) -> str:
    """
    Lấy danh sách TẤT CẢ môn học được dự kiến dạy trong một học kỳ cụ thể.
    Dùng khi sinh viên hỏi "em đang học kỳ X, nên đăng ký những môn nào?".

    Args:
        hoc_ky: Số thứ tự học kỳ từ 1 đến 8.
    """
    logger.info(f"[Tool] tim_mon_theo_ky → hoc_ky={hoc_ky}")
    try:
        driver = get_neo4j_driver()
        with driver.session() as s:
            result = s.run(
                """
                MATCH (c:Course)
                WHERE c.hoc_ky_du_kien = $hk
                OPTIONAL MATCH (c)-[:THUOC_KHOA]->(k:Khoa)
                RETURN c.ma_mon      AS ma,
                       c.ten_mon     AS ten,
                       c.so_tin_chi  AS tc,
                       c.loai_mon    AS loai,
                       k.ten         AS khoa
                ORDER BY c.ma_mon
                """,
                hk=hoc_ky,
            )
            rows = list(result)
        if not rows:
            return f"Không tìm thấy môn học nào được lên kế hoạch cho Học kỳ {hoc_ky}."
        lines = [f"Các môn học kỳ {hoc_ky} ({len(rows)} môn):"]
        for r in rows:
            khoa = r["khoa"] or "Chưa phân khoa"
            lines.append(f"  [{r['ma']}] {r['ten']} — {r['tc']} TC | {r['loai']} | Khoa: {khoa}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(e, exc_info=True)
        return f"Lỗi truy vấn Neo4j: {e}"


@tool
def tim_mon_theo_cong_cu(cong_cu: str) -> str:
    """
    Tìm các môn học sử dụng một công cụ / ngôn ngữ lập trình cụ thể.
    Dùng khi sinh viên muốn học Python, Java, SQL Server, C++, OpenCV, Agile, v.v.

    Args:
        cong_cu: Tên công cụ hoặc ngôn ngữ (ví dụ: "Python", "SQL Server", "Agile").
    """
    logger.info(f"[Tool] tim_mon_theo_cong_cu → cong_cu='{cong_cu}'")
    try:
        driver = get_neo4j_driver()
        with driver.session() as s:
            result = s.run(
                """
                MATCH (c:Course)
                WHERE any(t IN c.ngon_ngu_cong_cu
                          WHERE toLower(t) CONTAINS toLower($ccu))
                RETURN c.ma_mon      AS ma,
                       c.ten_mon     AS ten,
                       c.so_tin_chi  AS tc,
                       c.hoc_ky_du_kien AS hk,
                       c.ngon_ngu_cong_cu AS tools
                ORDER BY c.hoc_ky_du_kien
                """,
                ccu=cong_cu,
            )
            rows = list(result)
        if not rows:
            return f"Không tìm thấy môn học nào liên quan đến '{cong_cu}' trong CTĐT."
        lines = [f"Môn học sử dụng '{cong_cu}' ({len(rows)} môn):"]
        for r in rows:
            hk = f"HK{r['hk']}" if r["hk"] else "Chưa rõ HK"
            tools_str = ", ".join(r["tools"] or [])
            lines.append(f"  [{r['ma']}] {r['ten']} — {r['tc']} TC | {hk} | Tools: {tools_str}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(e, exc_info=True)
        return f"Lỗi truy vấn Neo4j: {e}"


@tool
def xem_dieu_kien_tien_quyet(ma_mon: str) -> str:
    """
    Kiểm tra các điều kiện tiên quyết (TIEN_QUYET) và các môn học trước khuyến nghị (HOC_TRUOC)
    của một môn học cụ thể. Dùng trước khi tư vấn sinh viên đăng ký môn đó.

    Args:
        ma_mon: Mã học phần, ví dụ "COMP1016", "MATH1001".
    """
    logger.info(f"[Tool] xem_dieu_kien_tien_quyet → ma_mon='{ma_mon}'")
    try:
        driver = get_neo4j_driver()
        with driver.session() as s:
            info = s.run(
                "MATCH (c:Course {ma_mon: $m}) RETURN c.ten_mon AS ten, c.so_tin_chi AS tc, c.hoc_ky_du_kien AS hk",
                m=ma_mon.upper(),
            ).single()
            if not info:
                return f"Không tìm thấy môn học có mã '{ma_mon}' trong hệ thống."

            tq = list(s.run(
                "MATCH (pre:Course)-[:TIEN_QUYET]->(c:Course {ma_mon: $m}) RETURN pre.ma_mon AS ma, pre.ten_mon AS ten",
                m=ma_mon.upper(),
            ))
            ht = list(s.run(
                "MATCH (pre:Course)-[:HOC_TRUOC]->(c:Course {ma_mon: $m}) RETURN pre.ma_mon AS ma, pre.ten_mon AS ten",
                m=ma_mon.upper(),
            ))
            sh = list(s.run(
                "MATCH (c:Course {ma_mon: $m})-[:SONG_HANH]->(co:Course) RETURN co.ma_mon AS ma, co.ten_mon AS ten",
                m=ma_mon.upper(),
            ))

        lines = [f"Knowledge Graph Context for {ma_mon.upper()} ({info['ten']} - {info['tc']}TC):"]
        if tq:
            lines.append("Paths [TIEN_QUYET - Bắt buộc]:")
            for r in tq:
                lines.append(f"({r['ma']} : {r['ten']}) -[TIEN_QUYET]-> ({ma_mon.upper()})")
        else:
            lines.append(f"Nodes: ({ma_mon.upper()}) has NO [TIEN_QUYET]")
        if ht:
            lines.append("Paths [HOC_TRUOC - Khuyến nghị]:")
            for r in ht:
                lines.append(f"({r['ma']} : {r['ten']}) -[HOC_TRUOC]-> ({ma_mon.upper()})")
        if sh:
            lines.append("Paths [SONG_HANH]:")
            for r in sh:
                lines.append(f"({ma_mon.upper()}) -[SONG_HANH]-> ({r['ma']} : {r['ten']})")
        return "\n".join(lines)
    except Exception as e:
        logger.error(e, exc_info=True)
        return f"Lỗi truy vấn Neo4j: {e}"


@tool
def xem_mo_ta_mon(ma_mon: str) -> str:
    """
    Xem thông tin chi tiết và mô tả nội dung của một môn học:
    số chương lý thuyết, số bài thực hành, phân bổ giờ, và ngôn ngữ/công cụ sử dụng.
    Dùng khi sinh viên muốn biết môn học đó học gì, khó không, thực hành nhiều không.

    Args:
        ma_mon: Mã học phần, ví dụ "COMP1016".
    """
    logger.info(f"[Tool] xem_mo_ta_mon → ma_mon='{ma_mon}'")
    try:
        driver = get_neo4j_driver()
        with driver.session() as s:
            result = s.run(
                """
                MATCH (c:Course {ma_mon: $m})
                OPTIONAL MATCH (c)-[:THUOC_KHOA]->(k:Khoa)
                RETURN c.ten_mon               AS ten,
                       c.so_tin_chi            AS tc,
                       c.loai_mon              AS loai,
                       c.hoc_ky_du_kien        AS hk,
                       c.mo_ta_tom_tat         AS mo_ta,
                       c.so_chuong_ly_thuyet   AS so_chuong,
                       c.so_bai_thuc_hanh      AS so_bai_th,
                       c.gio_truc_tiep         AS gio_tt,
                       c.gio_truc_tuyen        AS gio_tn,
                       c.gio_thuc_hanh         AS gio_th,
                       c.gio_tu_hoc            AS gio_th2,
                       c.ngon_ngu_cong_cu      AS tools,
                       k.ten                   AS khoa
                """,
                m=ma_mon.upper(),
            ).single()
        if not result:
            return f"Không tìm thấy môn học '{ma_mon}'."
        hk = f"HK{result['hk']}" if result["hk"] else "?"
        lines = [
            f"📘 [{ma_mon.upper()}] {result['ten']}",
            f"   Tín chỉ   : {result['tc']} TC | Loại: {result['loai']} | {hk}",
            f"   Khoa      : {result['khoa'] or 'Chưa phân khoa'}",
        ]
        if result["mo_ta"]:
            lines.append(f"   Mô tả     : {result['mo_ta']}")
        if result["so_chuong"] is not None:
            lines.append(f"   Lý thuyết : {result['so_chuong']} chương")
        if result["so_bai_th"] is not None:
            lines.append(f"   Thực hành : {result['so_bai_th']} bài")
        tt  = result["gio_tt"]  or 0
        tn  = result["gio_tn"]  or 0
        th  = result["gio_th"]  or 0
        th2 = result["gio_th2"] or 0
        if tt + tn + th + th2 > 0:
            lines.append(f"   Phân bổ giờ: Trực tiếp {tt}h | Trực tuyến {tn}h | TH/TL {th}h | Tự học {th2}h")
        tools = result["tools"] or []
        if tools:
            lines.append(f"   Công cụ   : {', '.join(tools)}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(e, exc_info=True)
        return f"Lỗi truy vấn Neo4j: {e}"


@tool
def kiem_tra_mo_lop(ma_mon_list: str) -> str:
    """
    Kiểm tra trong số các môn học được cung cấp, môn nào đang MỞ LỚP
    trong học kỳ hiện tại và còn chỗ trống để đăng ký.
    Luôn gọi tool này sau khi đã biết danh sách môn học ứng viên.

    Args:
        ma_mon_list: Chuỗi các mã môn cách nhau bằng dấu phẩy.
                     Ví dụ: "COMP1016, COMP1001, MATH1001".
    """
    logger.info(f"[Tool] kiem_tra_mo_lop → '{ma_mon_list}'")
    # ─── Mock API — thay bằng REST call thật khi có hệ thống đăng ký ───
    OPEN_COURSES = {
        "COMP1001": {"ten": "Nhập môn Lập trình",        "slots": 15, "phong": "B201"},
        "COMP1016": {"ten": "Cấu trúc dữ liệu",          "slots": 5,  "phong": "A305"},
        "COMP1304": {"ten": "Lập trình hướng đối tượng", "slots": 22, "phong": "B102"},
        "COMP1010": {"ten": "Giải tích I",                "slots": 0,  "phong": "—"},
        "MATH1001": {"ten": "Toán rời rạc",               "slots": 40, "phong": "C101"},
        "MATH1010": {"ten": "Đại số tuyến tính",          "slots": 30, "phong": "C102"},
        "COMP1043": {"ten": "Hệ điều hành",               "slots": 12, "phong": "A406"},
    }
    codes = [c.strip().upper() for c in ma_mon_list.split(",") if c.strip()]
    if not codes:
        return "Không có mã môn nào được cung cấp."
    lines = ["📋 Trạng thái mở lớp học kỳ này:"]
    for code in codes:
        if code in OPEN_COURSES:
            info = OPEN_COURSES[code]
            status = f"✅ Còn {info['slots']} chỗ | Phòng {info['phong']}" if info["slots"] > 0 else "❌ HẾT CHỖ"
            lines.append(f"  [{code}] {info['ten']} — {status}")
        else:
            lines.append(f"  [{code}] — ⚠️  Học kỳ này KHÔNG mở lớp")
    return "\n".join(lines)


@tool
def tim_lo_trinh_den_mon(ma_mon_dich: str) -> str:
    """
    Tìm toàn bộ chuỗi môn học cần hoàn thành TRƯỚC khi có thể học một môn đích.
    Dùng khi sinh viên hỏi "Em cần học gì trước để học được môn X?".
    Truy vết đệ quy theo quan hệ TIEN_QUYET và HOC_TRUOC.

    Args:
        ma_mon_dich: Mã học phần đích, ví dụ "COMP1307".
    """
    logger.info(f"[Tool] tim_lo_trinh_den_mon → '{ma_mon_dich}'")
    try:
        driver = get_neo4j_driver()
        with driver.session() as s:
            rows = list(s.run(
                """
                MATCH path = (pre:Course)-[:TIEN_QUYET|HOC_TRUOC*1..6]->(target:Course {ma_mon: $m})
                UNWIND relationships(path) AS rel
                WITH startNode(rel) AS src, rel, endNode(rel) AS tgt
                RETURN DISTINCT src.ma_mon AS src_ma, src.ten_mon AS src_ten,
                                type(rel) AS rel_type,
                                tgt.ma_mon AS tgt_ma, tgt.ten_mon AS tgt_ten
                """,
                m=ma_mon_dich.upper(),
            ))
            target_info = s.run(
                "MATCH (c:Course {ma_mon: $m}) RETURN c.ten_mon AS ten",
                m=ma_mon_dich.upper(),
            ).single()
        if not target_info:
            return f"Không tìm thấy môn '{ma_mon_dich}' trong hệ thống."
        target_name = target_info["ten"]
        if not rows:
            return f"Knowledge Graph Path: ({ma_mon_dich.upper()} : {target_name}) has NO prerequisite paths."
        lines = [f"Knowledge Graph Paths leading to ({ma_mon_dich.upper()} : {target_name}):"]
        for r in rows:
            lines.append(f"({r['src_ma']} : {r['src_ten']}) -[{r['rel_type']}]-> ({r['tgt_ma']} : {r['tgt_ten']})")
        return "\n".join(lines)
    except Exception as e:
        logger.error(e, exc_info=True)
        return f"Lỗi truy vấn Neo4j: {e}"


@tool
def toi_uu_lo_trinh_hoc_tap(muc_tieu: str) -> str:
    """
    Kéo toàn bộ cấu trúc đồ thị môn học (Sub-graph) của chương trình đào tạo để AI có thể
    thực hiện thuật toán sắp xếp Topo (Topological Sort) nhằm lập kế hoạch học tập tối ưu.
    Dùng khi sinh viên yêu cầu "tối ưu lộ trình", "lập kế hoạch học tập toàn diện", "xếp lịch học dài hạn".

    Args:
        muc_tieu: Mục tiêu của sinh viên (VD: "Sớm ra trường", "Tập trung AI", "Học dàn trải").
    """
    logger.info(f"[Tool] toi_uu_lo_trinh_hoc_tap → muc_tieu='{muc_tieu}'")
    try:
        driver = get_neo4j_driver()
        with driver.session() as s:
            result = s.run(
                """
                MATCH (c:Course)
                OPTIONAL MATCH (pre:Course)-[r:TIEN_QUYET|HOC_TRUOC]->(c)
                RETURN c.ma_mon AS ma, c.ten_mon AS ten, c.so_tin_chi AS tc, c.hoc_ky_du_kien AS hk,
                       pre.ma_mon AS pre_ma, type(r) AS rel_type
                ORDER BY c.hoc_ky_du_kien, c.ma_mon
                """
            )
            nodes: dict = {}
            edges: list = []
            for r in result:
                ma = r["ma"]
                if ma not in nodes:
                    nodes[ma] = {"ten": r["ten"], "tc": r["tc"], "hk": r["hk"] or "?"}
                if r["pre_ma"]:
                    edges.append(f"({r['pre_ma']}) -[{r['rel_type']}]-> ({ma})")
        lines = [
            f"Knowledge Graph (Curriculum Subgraph) for Path Optimization (Goal: {muc_tieu}):",
            "\n== NODES (All Courses) =="
        ]
        num_tc = 0
        for ma, data in nodes.items():
            lines.append(f"({ma}) : {data['ten']} | {data['tc']} TC | Đề xuất: HK{data['hk']}")
            try:
                num_tc += int(data["tc"])
            except (ValueError, TypeError):
                pass
        lines.append("\n== EDGES (Dependencies) ==")
        lines.extend(list(set(edges)))
        lines.append(f"\nTổng cấu trúc: {len(nodes)} môn ({num_tc} Tín chỉ). AI hãy sử dụng đồ thị này để phân bổ học kỳ sao cho không vi phạm logic EDGES.")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Lỗi truy xuất đồ thị tổng thể: {e}", exc_info=True)
        return f"Lỗi truy vấn đồ thị Neo4j: {e}"


@tool
def truy_van_do_thi_linh_hoat(cypher_query: str) -> str:
    """
    [Neural/Dynamic Branch] Thực hiện truy vấn Cypher linh hoạt lên Neo4j Knowledge Graph.
    Dùng khi câu hỏi phức tạp không thể giải quyết bằng các hardcoded tools
    (ví dụ: đếm số môn, tìm đường đi phức tạp, lọc đa điều kiện).

    Lưu ý: Bạn (LLM) phải TỰ VIẾT câu lệnh Cypher dựa trên schema sau:
    - Nodes: Course(ma_mon, ten_mon, so_tin_chi, loai_mon, hoc_ky_du_kien, ngon_ngu_cong_cu)
             Khoa(ten), AcademicProgram(ma_nganh, ten_nganh)
    - Relationships:
      (Course)-[:TIEN_QUYET|HOC_TRUOC|SONG_HANH]->(Course)
      (Course)-[:THUOC_KHOA]->(Khoa)
      (AcademicProgram)-[:CO_MON_HOC]->(Course)
    """
    logger.info(f"[Tool] truy_van_do_thi_linh_hoat → Query:\n{cypher_query}")
    forbidden_keywords = ["delete", "remove", "drop", "set", "merge", "create", "detach"]
    if any(kw in cypher_query.lower() for kw in forbidden_keywords):
        return "Lỗi Guardrail: Truy vấn Cypher chứa từ khóa bị cấm (chỉ cho phép READ-ONLY bằng MATCH). Hãy viết lại."
    try:
        driver = get_neo4j_driver()
        with driver.session() as s:
            rows = list(s.run(cypher_query))
        if not rows:
            return "Truy vấn thành công nhưng không tìm thấy dữ liệu (Empty Result). Hãy kiểm tra lại Label hoặc Relationship trong Cypher."
        lines = ["Raw Graph Data Trích xuất:"]
        for idx, r in enumerate(rows[:50]):
            lines.append(f"Row {idx+1}: {dict(r)}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Cypher Error: {e}")
        return f"Lỗi cú pháp Cypher (Neo4j Exception): {e}\n=> HÃY ĐỌC LỖI NÀY, TỰ ĐIỀU CHỈNH LẠI CÂU LỆNH CYPHER KHÁC VÀ GỌI LẠI TOOL."


# ──────────────────────────────────────────────────────────────────────────
# RAG PIPELINE TOOL
# ──────────────────────────────────────────────────────────────────────────

_ENSEMBLE_RETRIEVER = None


def _get_or_create_retriever():
    global _ENSEMBLE_RETRIEVER
    if _ENSEMBLE_RETRIEVER is not None:
        return _ENSEMBLE_RETRIEVER

    logger.info("Initializing Hybrid Retriever (BM25 + FAISS) + Cross-Encoder Reranking...")
    json_path = Path("data/processed/curriculum_extracted.json")
    if not json_path.exists():
        raise FileNotFoundError(f"Không tìm thấy {json_path}")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    docs = []
    prog = data.get("program", {})
    prog_text = (
        f"THÔNG TIN CHƯƠNG TRÌNH ĐÀO TẠO CNTT:\n"
        f"Mã ngành: {prog.get('ma_nganh')}, Tên: {prog.get('ten_nganh_vn')} ({prog.get('ten_nganh_en')})\n"
        f"Tổng tín chỉ: {prog.get('tong_tin_chi')} TC, Thời gian: {prog.get('thoi_gian_dao_tao')}\n"
        f"Văn bằng: {prog.get('ten_van_bang_vn')}, Tỷ lệ online tối đa: {prog.get('ty_le_truc_tuyen_toi_da')}\n"
        f"Thang điểm: {prog.get('thang_diem')}, Chuẩn ngoại ngữ: {prog.get('chuan_ngoai_ngu')}"
    )
    docs.append(Document(page_content=prog_text, metadata={"type": "program"}))

    for rule in data.get("rules", []):
        docs.append(Document(
            page_content=f"QUY TẮC [{rule.get('loai_quy_tac', 'Chung')}]: {rule.get('mo_ta', '')}",
            metadata={"type": "rule"},
        ))

    for c in data.get("courses", []):
        docs.append(Document(
            page_content=(
                f"MÔN HỌC: [{c.get('ma_mon')}] {c.get('ten_mon')} - {c.get('so_tin_chi')} TC.\n"
                f"Mô tả: {c.get('mo_ta_tom_tat')}\nKhoa: {c.get('don_vi_quan_ly')}, Loại: {c.get('loai_mon')}."
            ),
            metadata={"type": "course"},
        ))

    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    faiss_retriever = FAISS.from_documents(docs, embeddings).as_retriever(search_kwargs={"k": 10})
    bm25_retriever = BM25Retriever.from_documents(docs)
    bm25_retriever.k = 10

    ensemble_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, faiss_retriever],
        weights=[0.3, 0.7],
    )
    model = HuggingFaceCrossEncoder(model_name="cross-encoder/ms-marco-TinyBERT-L-2-v2")
    compressor = CrossEncoderReranker(model=model, top_n=4)
    _ENSEMBLE_RETRIEVER = ContextualCompressionRetriever(
        base_compressor=compressor,
        base_retriever=ensemble_retriever,
    )
    logger.info(f"Hybrid Retriever & Reranker created with {len(docs)} documents.")
    return _ENSEMBLE_RETRIEVER


@tool
def hoi_tai_lieu_chuong_trinh(cau_hoi: str) -> str:
    """
    Trả lời câu hỏi tự do bằng cách sử dụng Advanced RAG Pipeline
    (Pre-Retrieval Query Transformation + Hybrid Search + Post-Retrieval Reranking).
    Dùng khi câu hỏi liên quan đến quy chế, chuẩn đầu ra, tổng tín chỉ,
    hoặc bất kỳ nội dung nào nằm ngoài schema Neo4j graph.

    Args:
        cau_hoi: Câu hỏi tiếng Việt của sinh viên.
    """
    logger.info(f"[Tool] Advanced RAG Pipeline → '{cau_hoi[:60]}...'")
    try:
        api_key    = os.getenv("LLM_API_KEY")
        model_name = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        llm_raw = ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key, temperature=0.1)

        # 1. PRE-RETRIEVAL — Query Transformation
        rewrite_prompt = (
            "Bạn là hệ thống xử lý ngôn ngữ. Hãy viết lại và tối ưu hóa câu hỏi sau thành một câu truy vấn tìm kiếm "
            "về quy chế, mô tả môn học, chuẩn đầu ra đại học. Tập trung vào Keywords cốt lõi.\n"
            "Chỉ output ra kết quả tối ưu, không giải thích dài dòng.\n\n"
            f"Câu gốc: {cau_hoi}\n"
            "Câu tối ưu:"
        )
        rewritten_query = _extract_text(llm_raw.invoke(rewrite_prompt)).strip()
        logger.info(f"  ↪ [Query Transformation] '{cau_hoi}' => '{rewritten_query}'")

        # 2. RETRIEVAL & POST-RETRIEVAL — Hybrid Search + Reranking
        try:
            retrieved_docs = _get_or_create_retriever().invoke(rewritten_query)
        except Exception as e:
            logger.warning(f"Retriever lỗi, fallback câu gốc: {e}")
            retrieved_docs = _get_or_create_retriever().invoke(cau_hoi)

        if not retrieved_docs:
            return "RAG System không tìm thấy dữ liệu (Documents Empty)."

        context = "\n\n".join(f"[Doc {i+1}]: {d.page_content}" for i, d in enumerate(retrieved_docs))
        logger.info(f"  ↪ [Retrieved] {len(retrieved_docs)} documents sau Reranking.")

        # 3. GENERATION
        prompt = (
            "Bạn là chuyên gia tư vấn học tập. Trả lời câu hỏi của sinh viên DỰA VÀO phần Context dưới đây.\n"
            "Nếu bài toán yêu cầu tìm tên ngành, số tín chỉ, hãy phân tích kỹ nhé.\n"
            "Nếu không có thông tin trong Context, hãy xin lỗi và bảo không có dữ liệu để tránh hallucination.\n\n"
            f"=== CONTEXT ĐÃ ĐƯỢC LỌC KỸ ===\n{context}\n\n"
            f"=== CÂU HỎI GỐC CỦA SINH VIÊN ===\n{cau_hoi}\n\n"
            "=== TRẢ LỜI ==="
        )
        result = _extract_text(llm_raw.invoke(prompt).content)
        return result or "Không có câu trả lời từ hệ thống sinh ngôn ngữ."
    except Exception as e:
        logger.error(f"Advanced RAG error: {e}", exc_info=True)
        return f"Lỗi RAG Pipeline: {e}"


# ──────────────────────────────────────────────────────────────────────────
# EXPORT
# ──────────────────────────────────────────────────────────────────────────

ALL_TOOLS = [
    tim_mon_theo_ky,
    tim_mon_theo_cong_cu,
    xem_dieu_kien_tien_quyet,
    xem_mo_ta_mon,
    kiem_tra_mo_lop,
    tim_lo_trinh_den_mon,
    toi_uu_lo_trinh_hoc_tap,
    truy_van_do_thi_linh_hoat,
    hoi_tai_lieu_chuong_trinh,
]
