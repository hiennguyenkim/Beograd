"""
refinement.py
~~~~~~~~~~~~~
Giai đoạn 4: Làm sạch và tinh chỉnh Knowledge Graph.

Thực hiện các tác vụ hậu xử lý sau khi import dữ liệu thô vào Neo4j:
  1. Deduplication: Gộp các node Skill/Concept bị trùng lặp về ngữ nghĩa
     (khác tên nhưng cùng nghĩa, ví dụ "ML" vs "Machine Learning").
  2. Orphan cleanup: Xóa node không có bất kỳ relationship nào.
  3. Normalization: Chuẩn hóa tên các node theo quy tắc alias đã định nghĩa.
  4. Index creation: Tạo full-text index để hỗ trợ tìm kiếm nhanh.

Chiến lược deduplication:
  - Bước 1 (Tên giống hệt): collapse các node trùng `name` (case-insensitive).
  - Bước 2 (Alias mapping): ánh xạ tên viết tắt → tên đầy đủ theo bảng ALIAS_MAP.
  - Bước 3 (LLM-assisted, optional): gọi LLM để phát hiện đồng nghĩa phức tạp hơn.
"""

import logging
import os
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from neo4j import Driver

from graph_builder import get_neo4j_driver

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bảng chuẩn hóa alias
# ---------------------------------------------------------------------------

# Tên viết tắt / sai chuẩn → tên đầy đủ chuẩn
ALIAS_MAP: Dict[str, str] = {
    # Tiếng Anh viết tắt
    "AI":    "Artificial Intelligence",
    "ML":    "Machine Learning",
    "DL":    "Deep Learning",
    "NLP":   "Natural Language Processing",
    "DS":    "Data Science",
    "OOP":   "Object-Oriented Programming",
    "DB":    "Database",
    "OS":    "Operating System",
    "CV":    "Computer Vision",
    # Tiếng Việt → Tiếng Anh chuẩn hóa
    "Lập trình":         "Programming",
    "Giải quyết vấn đề": "Problem Solving",
    "Trí tuệ nhân tạo":  "Artificial Intelligence",
    "Học máy":           "Machine Learning",
    "Cơ sở dữ liệu":     "Database",
}


# ---------------------------------------------------------------------------
# 1. Normalization: chuẩn hóa tên theo ALIAS_MAP
# ---------------------------------------------------------------------------

def normalize_node_names(driver: Driver) -> None:
    """
    Chuẩn hóa tên các node Skill và Concept theo ALIAS_MAP.
    Ví dụ: node {name: 'AI'} → {name: 'Artificial Intelligence'}.
    """
    logger.info("Bắt đầu normalize node names theo alias map...")
    with driver.session() as session:
        for alias, canonical in ALIAS_MAP.items():
            for label in ("Skill", "Concept"):
                query = f"""
                MATCH (n:{label})
                WHERE toLower(trim(n.name)) = toLower($alias)
                  AND n.name <> $canonical
                SET n.name = $canonical
                RETURN count(n) AS updated
                """
                result = session.run(query, alias=alias, canonical=canonical)
                count = result.single()["updated"]
                if count > 0:
                    logger.info(f"  Normalized {count} {label} node(s): '{alias}' → '{canonical}'")
    logger.info("Hoàn thành normalize.")


# ---------------------------------------------------------------------------
# 2. Deduplication — Stage 1: Exact name match (case-insensitive)
# ---------------------------------------------------------------------------

def _find_exact_duplicates(session, label: str) -> List[Tuple[str, List[str]]]:
    """
    Tìm các nhóm node cùng label có name giống nhau (case-insensitive).

    Returns:
        List of (canonical_id, [duplicate_ids...])
    """
    query = f"""
    MATCH (n:{label})
    WITH toLower(trim(n.name)) AS norm_name, collect(n.id) AS ids
    WHERE size(ids) > 1
    RETURN norm_name, ids
    """
    result = session.run(query)
    groups = []
    for record in result:
        ids = record["ids"]
        # Chọn node đầu tiên làm canonical (giữ lại), còn lại là duplicates
        canonical_id = ids[0]
        duplicate_ids = ids[1:]
        groups.append((canonical_id, duplicate_ids))
    return groups


def _merge_node_into_canonical(session, canonical_id: str, duplicate_ids: List[str], label: str) -> int:
    """
    Chuyển toàn bộ relationships từ duplicate nodes sang canonical node,
    sau đó xóa duplicate nodes.

    Returns:
        Số node đã được gộp.
    """
    total_merged = 0
    for dup_id in duplicate_ids:
        # Chuyển tất cả incoming relationships
        session.run(
            f"""
            MATCH (dup:{label} {{id: $dup_id}})
            MATCH (canonical:{label} {{id: $canonical_id}})
            CALL apoc.refactor.mergeNodes([canonical, dup], {{properties: 'discard', mergeRels: true}})
            YIELD node RETURN node
            """,
            dup_id=dup_id,
            canonical_id=canonical_id,
        )
        total_merged += 1
    return total_merged


def _merge_duplicates_no_apoc(session, canonical_id: str, duplicate_ids: List[str], label: str) -> int:
    """
    Fallback deduplication không dùng APOC:
    Dùng Cypher thuần để re-wire relationships rồi xóa duplicate.
    """
    total_merged = 0
    for dup_id in duplicate_ids:
        try:
            # Chuyển OUTGOING relationships của duplicate sang canonical
            session.run(
                f"""
                MATCH (dup:{label} {{id: $dup_id}})-[r]->(target)
                MATCH (canonical:{label} {{id: $canonical_id}})
                WHERE NOT (canonical)-[:{{}}"type(r)"]->(target)
                CALL apoc.create.relationship(canonical, type(r), {{}}, target) YIELD rel
                DELETE r
                """,
                dup_id=dup_id,
                canonical_id=canonical_id,
            )
        except Exception:
            pass  # sẽ dùng pure Cypher dưới đây

        # Pure Cypher re-wire cho các relationship phổ biến
        for rel_type in ("TEACHES", "COVERS", "MEETS", "HAS_INDICATOR", "PREREQUISITE", "IN_SEMESTER"):
            # Outgoing
            session.run(
                f"""
                MATCH (dup:{label} {{id: $dup_id}})-[r:{rel_type}]->(target)
                MATCH (canonical:{label} {{id: $canonical_id}})
                MERGE (canonical)-[:{rel_type}]->(target)
                DELETE r
                """,
                dup_id=dup_id, canonical_id=canonical_id,
            )
            # Incoming
            session.run(
                f"""
                MATCH (source)-[r:{rel_type}]->(dup:{label} {{id: $dup_id}})
                MATCH (canonical:{label} {{id: $canonical_id}})
                MERGE (source)-[:{rel_type}]->(canonical)
                DELETE r
                """,
                dup_id=dup_id, canonical_id=canonical_id,
            )

        # Xóa duplicate node
        session.run(
            f"MATCH (dup:{label} {{id: $dup_id}}) DELETE dup",
            dup_id=dup_id,
        )
        total_merged += 1
    return total_merged


def deduplicate_by_exact_name(driver: Driver) -> None:
    """
    Gộp các node Skill và Concept có tên giống nhau (case-insensitive).
    Thử dùng APOC trước, fallback sang pure Cypher nếu APOC chưa cài.
    """
    logger.info("Bắt đầu deduplication (exact name match)...")
    with driver.session() as session:
        for label in ("Skill", "Concept"):
            groups = _find_exact_duplicates(session, label)
            if not groups:
                logger.info(f"  Không có {label} node trùng lặp.")
                continue
            logger.info(f"  Tìm thấy {len(groups)} nhóm {label} trùng lặp, bắt đầu gộp...")
            total = 0
            for canonical_id, dup_ids in groups:
                try:
                    merged = _merge_node_into_canonical(session, canonical_id, dup_ids, label)
                except Exception as apoc_err:
                    logger.warning(f"  APOC không khả dụng ({apoc_err}), dùng fallback Cypher...")
                    merged = _merge_duplicates_no_apoc(session, canonical_id, dup_ids, label)
                total += merged
                logger.debug(f"    Gộp {merged} bản sao của '{canonical_id}'")
            logger.info(f"  Đã gộp tổng {total} {label} node(s).")
    logger.info("Hoàn thành deduplication.")


# ---------------------------------------------------------------------------
# 3. Orphan cleanup
# ---------------------------------------------------------------------------

def remove_orphan_nodes(driver: Driver, labels: List[str] = None) -> None:
    """
    Xóa các node không có bất kỳ relationship nào (orphan nodes).
    Thường là kết quả của extraction lỗi hoặc tham chiếu đến node không tồn tại.

    Args:
        labels: Danh sách labels cần kiểm tra. Mặc định: Skill, Concept.
    """
    if labels is None:
        labels = ["Skill", "Concept"]

    logger.info("Tìm và xóa orphan nodes...")
    with driver.session() as session:
        for label in labels:
            query = f"""
            MATCH (n:{label})
            WHERE NOT (n)--()
            WITH n, n.id AS orphan_id
            DELETE n
            RETURN count(*) AS deleted
            """
            result = session.run(query)
            count = result.single()["deleted"]
            if count > 0:
                logger.info(f"  Đã xóa {count} orphan {label} node(s).")
            else:
                logger.info(f"  Không có orphan {label} node.")
    logger.info("Hoàn thành orphan cleanup.")


# ---------------------------------------------------------------------------
# 4. Full-text index
# ---------------------------------------------------------------------------

def create_fulltext_indexes(driver: Driver) -> None:
    """
    Tạo full-text indexes để hỗ trợ tìm kiếm ngữ nghĩa từ Agent.
    """
    indexes = [
        ("idx_course_name",  ["Course"],          ["name", "code"]),
        ("idx_skill_name",   ["Skill"],            ["name"]),
        ("idx_concept_name", ["Concept"],          ["name"]),
        ("idx_plo_name",     ["PLO"],              ["name"]),
    ]
    logger.info("Tạo full-text indexes...")
    with driver.session() as session:
        for idx_name, labels, props in indexes:
            labels_str = " | ".join(labels)
            props_str = ", ".join([f"n.{p}" for p in props])
            query = f"""
            CREATE FULLTEXT INDEX {idx_name} IF NOT EXISTS
            FOR (n:{labels_str})
            ON EACH [{props_str}]
            """
            try:
                session.run(query)
                logger.debug(f"  Index '{idx_name}' đã tạo.")
            except Exception as e:
                logger.warning(f"  Index '{idx_name}' có thể đã tồn tại: {e}")
    logger.info("Hoàn thành tạo indexes.")


# ---------------------------------------------------------------------------
# Master refinement pipeline
# ---------------------------------------------------------------------------

def run_refinement_pipeline(driver: Driver) -> None:
    """
    Chạy toàn bộ pipeline làm sạch Knowledge Graph.
    Thứ tự thực hiện quan trọng:
      1. Normalize → 2. Deduplicate → 3. Remove orphans → 4. Create indexes
    """
    logger.info("=== BẮT ĐẦU REFINEMENT PIPELINE ===")
    normalize_node_names(driver)
    deduplicate_by_exact_name(driver)
    remove_orphan_nodes(driver)
    create_fulltext_indexes(driver)
    logger.info("=== HOÀN THÀNH REFINEMENT PIPELINE ===")


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("Chạy smoke test refinement.py...")
    try:
        driver = get_neo4j_driver()
        run_refinement_pipeline(driver)
        driver.close()
        logger.info("Smoke test hoàn thành.")
    except Exception as e:
        logger.error(f"Smoke test thất bại: {e}", exc_info=True)
