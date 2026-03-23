"""
graph_builder.py
~~~~~~~~~~~~~~~~
Giai đoạn 3: Xây dựng Knowledge Graph trên Neo4j.

Nhận ExtractionResult từ extraction.py và chuyển toàn bộ
nodes + relationships thành lệnh Cypher MERGE để nạp vào Neo4j.

Thiết kế:
  - Dùng MERGE (không phải CREATE) để đảm bảo idempotent:
    chạy lại pipeline không tạo node trùng lặp.
  - Mỗi loại node có constraint UNIQUE trên thuộc tính `id`.
  - Batch import bằng UNWIND để hiệu quả hơn khi có nhiều nodes.
"""

import logging
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, AuthError



# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Neo4j Driver Factory
# ---------------------------------------------------------------------------

def get_neo4j_driver() -> Driver:
    """
    Khởi tạo và kiểm tra kết nối Neo4j từ biến môi trường.

    Returns:
        neo4j.Driver đã được xác thực.

    Raises:
        EnvironmentError: Nếu thiếu biến môi trường.
        AuthError: Nếu thông tin xác thực sai.
        ServiceUnavailable: Nếu không kết nối được tới Neo4j.
    """
    uri = os.getenv("NEO4J_URI")
    username = os.getenv("NEO4J_USERNAME")
    password = os.getenv("NEO4J_PASSWORD")

    if not all([uri, username, password]):
        raise EnvironmentError(
            "Thiếu biến môi trường NEO4J_URI, NEO4J_USERNAME, hoặc NEO4J_PASSWORD trong .env"
        )

    try:
        driver = GraphDatabase.driver(uri, auth=(username, password))
        driver.verify_connectivity()
        logger.info(f"Kết nối Neo4j thành công: {uri}")
        return driver
    except AuthError as e:
        logger.error(f"Xác thực Neo4j thất bại: {e}")
        raise
    except ServiceUnavailable as e:
        logger.error(f"Không thể kết nối Neo4j tại {uri}: {e}")
        raise


# ---------------------------------------------------------------------------
# Schema Setup — UNIQUE Constraints
# ---------------------------------------------------------------------------

CONSTRAINT_QUERIES = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Course)   REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Skill)    REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Concept)  REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:PLO)      REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:PI)       REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Semester) REQUIRE n.id IS UNIQUE",
]


def setup_schema(driver: Driver) -> None:
    """Tạo UNIQUE constraints trên tất cả node types."""
    logger.info("Thiết lập schema constraints trên Neo4j...")
    with driver.session() as session:
        for query in CONSTRAINT_QUERIES:
            try:
                session.run(query)
                logger.debug(f"OK: {query}")
            except Exception as e:
                logger.warning(f"Constraint có thể đã tồn tại: {e}")
    logger.info("Hoàn thành thiết lập schema.")


# ---------------------------------------------------------------------------
# Node import helpers
# ---------------------------------------------------------------------------

def _run_batch(session: Any, query: str, params: Dict) -> None:
    """Chạy query với UNWIND batch."""
    try:
        session.run(query, params)
    except Exception as e:
        logger.error(f"Lỗi khi chạy batch query: {e}", exc_info=True)
        raise


def import_courses(session: Any, extraction: ExtractionResult) -> None:
    """MERGE tất cả Course nodes."""
    if not extraction.courses:
        return
    rows = [
        {"id": c.id, "name": c.name, "code": c.code, "credits": c.credits}
        for c in extraction.courses
    ]
    query = """
    UNWIND $rows AS row
    MERGE (n:Course {id: row.id})
    SET n.name    = row.name,
        n.code    = row.code,
        n.credits = row.credits
    """
    _run_batch(session, query, {"rows": rows})
    logger.info(f"  Đã MERGE {len(rows)} Course nodes.")


def import_skills(session: Any, extraction: ExtractionResult) -> None:
    """MERGE tất cả Skill nodes."""
    if not extraction.skills:
        return
    rows = [{"id": s.id, "name": s.name} for s in extraction.skills]
    query = """
    UNWIND $rows AS row
    MERGE (n:Skill {id: row.id})
    SET n.name = row.name
    """
    _run_batch(session, query, {"rows": rows})
    logger.info(f"  Đã MERGE {len(rows)} Skill nodes.")


def import_concepts(session: Any, extraction: ExtractionResult) -> None:
    """MERGE tất cả Concept nodes."""
    if not extraction.concepts:
        return
    rows = [{"id": c.id, "name": c.name} for c in extraction.concepts]
    query = """
    UNWIND $rows AS row
    MERGE (n:Concept {id: row.id})
    SET n.name = row.name
    """
    _run_batch(session, query, {"rows": rows})
    logger.info(f"  Đã MERGE {len(rows)} Concept nodes.")


def import_plos(session: Any, extraction: ExtractionResult) -> None:
    """MERGE tất cả PLO nodes."""
    if not extraction.plos:
        return
    rows = [{"id": p.id, "name": p.name} for p in extraction.plos]
    query = """
    UNWIND $rows AS row
    MERGE (n:PLO {id: row.id})
    SET n.name = row.name
    """
    _run_batch(session, query, {"rows": rows})
    logger.info(f"  Đã MERGE {len(rows)} PLO nodes.")


def import_pis(session: Any, extraction: ExtractionResult) -> None:
    """MERGE tất cả PI nodes."""
    if not extraction.pis:
        return
    rows = [{"id": p.id, "name": p.name, "plo_id": p.plo_id} for p in extraction.pis]
    query = """
    UNWIND $rows AS row
    MERGE (n:PI {id: row.id})
    SET n.name   = row.name,
        n.plo_id = row.plo_id
    """
    _run_batch(session, query, {"rows": rows})
    logger.info(f"  Đã MERGE {len(rows)} PI nodes.")


def import_semesters(session: Any, extraction: ExtractionResult) -> None:
    """MERGE tất cả Semester nodes."""
    if not extraction.semesters:
        return
    rows = [{"id": s.id, "name": s.name} for s in extraction.semesters]
    query = """
    UNWIND $rows AS row
    MERGE (n:Semester {id: row.id})
    SET n.name = row.name
    """
    _run_batch(session, query, {"rows": rows})
    logger.info(f"  Đã MERGE {len(rows)} Semester nodes.")


# ---------------------------------------------------------------------------
# Relationship import
# ---------------------------------------------------------------------------

# Map relationship type → (source_label, target_label)
REL_TYPE_MAP: Dict[str, tuple] = {
    "TEACHES":       ("Course",   "Skill"),
    "COVERS":        ("Course",   "Concept"),
    "MEETS":         ("Course",   "PLO"),
    "HAS_INDICATOR": ("PLO",      "PI"),
    "PREREQUISITE":  ("Course",   "Course"),
    "IN_SEMESTER":   ("Course",   "Semester"),
}


def import_relationships(session: Any, extraction: ExtractionResult) -> None:
    """
    MERGE tất cả relationships.
    Gom nhóm theo loại relationship để tạo query hiệu quả.
    """
    if not extraction.relationships:
        return

    # Gom nhóm theo type
    groups: Dict[str, List[Dict]] = {}
    for rel in extraction.relationships:
        groups.setdefault(rel.type, []).append(
            {"source_id": rel.source_id, "target_id": rel.target_id}
        )

    for rel_type, rows in groups.items():
        if rel_type not in REL_TYPE_MAP:
            logger.warning(f"Bỏ qua relationship type không xác định: '{rel_type}'")
            continue

        src_label, tgt_label = REL_TYPE_MAP[rel_type]
        query = f"""
        UNWIND $rows AS row
        MATCH (src:{src_label} {{id: row.source_id}})
        MATCH (tgt:{tgt_label} {{id: row.target_id}})
        MERGE (src)-[:{rel_type}]->(tgt)
        """
        try:
            _run_batch(session, query, {"rows": rows})
            logger.info(f"  Đã MERGE {len(rows)} [{rel_type}] relationships.")
        except Exception as e:
            logger.error(f"Lỗi khi MERGE relationship {rel_type}: {e}")


# ---------------------------------------------------------------------------
# Master import function
# ---------------------------------------------------------------------------

def import_extraction_result(driver: Driver, extraction: ExtractionResult) -> None:
    """
    Nạp toàn bộ ExtractionResult (nodes + relationships) vào Neo4j.

    Thứ tự import: nodes trước, relationships sau (để MATCH không thất bại).

    Args:
        driver: Neo4j Driver đã kết nối.
        extraction: Kết quả sau khi merge từ tất cả chunks.
    """
    logger.info("Bắt đầu import vào Neo4j...")
    with driver.session() as session:
        import_courses(session, extraction)
        import_skills(session, extraction)
        import_concepts(session, extraction)
        import_plos(session, extraction)
        import_pis(session, extraction)
        import_semesters(session, extraction)
        import_relationships(session, extraction)
    logger.info("Hoàn thành import toàn bộ dữ liệu vào Neo4j.")


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from schemas import (
        Course, Concept, Skill, PLO, Semester, Relationship, ExtractionResult
    )

    # Tạo dữ liệu mẫu kiểm thử
    sample = ExtractionResult(
        courses=[Course(id="comp1016", name="Cấu trúc dữ liệu", code="COMP1016", credits=3)],
        concepts=[Concept(id="binary_tree", name="Binary Tree"),
                  Concept(id="stack", name="Stack")],
        skills=[Skill(id="problem_solving", name="Problem Solving")],
        plos=[PLO(id="plo_5", name="Phân tích và thiết kế thuật toán hiệu quả")],
        semesters=[Semester(id="semester_3", name="Học kỳ 3")],
        relationships=[
            Relationship(source_id="comp1016", target_id="binary_tree", type="COVERS"),
            Relationship(source_id="comp1016", target_id="stack",        type="COVERS"),
            Relationship(source_id="comp1016", target_id="problem_solving", type="TEACHES"),
            Relationship(source_id="comp1016", target_id="plo_5",        type="MEETS"),
            Relationship(source_id="comp1016", target_id="semester_3",   type="IN_SEMESTER"),
        ],
    )

    logger.info("Chạy smoke test graph_builder.py...")
    driver = get_neo4j_driver()
    setup_schema(driver)
    import_extraction_result(driver, sample)
    driver.close()
    logger.info("Smoke test hoàn thành.")
