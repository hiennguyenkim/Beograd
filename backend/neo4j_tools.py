"""
neo4j_tools.py
==============
Các tool để agent query Neo4j Knowledge Graph.
Category names khớp đúng với import_data.py:
  - Học phần chung
  - Chuyên môn chung nhóm ngành
  - Chuyên môn chung lĩnh vực
  - Nghiệp vụ chung
  - Nghiệp vụ ngành
  - Thực hành nghề nghiệp
  - Tốt nghiệp
"""

import os
import re
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URL      = os.environ.get("NEO4J_URI",      os.environ.get("NEO4J_URL",  ""))
NEO4J_USER     = os.environ.get("NEO4J_USERNAME",  os.environ.get("NEO4J_USER", ""))
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

# ── Driver singleton ──────────────────────────────────────────────────────────

_driver = None

def get_driver():
    global _driver
    if _driver is None:
        pw = "set" if NEO4J_PASSWORD else "MISSING"
        if not NEO4J_URL or not NEO4J_USER or not NEO4J_PASSWORD:
            raise ValueError(
                "Neo4j chua cau hinh!\n"
                "  NEO4J_URI  = " + (NEO4J_URL  or "MISSING") + "\n"
                "  NEO4J_USER = " + (NEO4J_USER or "MISSING") + "\n"
                "  PASSWORD   = " + pw
            )
        _driver = GraphDatabase.driver(
            NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASSWORD),
            connection_timeout=30,
        )
        print("   ✓ Neo4j connected: " + NEO4J_URL)
    return _driver

def close_driver():
    global _driver
    if _driver:
        _driver.close()
        _driver = None


# ── Hằng số category (khớp với import_data.py) ───────────────────────────────

CAT_COMMON          = "Học phần chung"
CAT_MAJOR_GROUP     = "Chuyên môn chung nhóm ngành"
CAT_MAJOR_FIELD     = "Chuyên môn chung lĩnh vực"
CAT_PROFESSION_BASE = "Nghiệp vụ chung"
CAT_PROFESSION      = "Nghiệp vụ ngành"
CAT_PRACTICE        = "Thực hành nghề nghiệp"
CAT_GRADUATION      = "Tốt nghiệp"

# Mapping từ keyword mục tiêu → danh sách category
GOAL_CATEGORY_MAP = {
    "lập trình":        [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "lập trình viên":   [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "phần mềm":         [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "software":         [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "ai":               [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "trí tuệ nhân tạo": [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "machine learning": [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "học máy":          [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "mạng":             [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "mạng máy tính":    [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "network":          [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "database":         [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "cơ sở dữ liệu":    [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "web":              [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "bảo mật":          [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "quản trị":         [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "devops":           [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "cloud":            [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "đám mây":          [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "kiểm thử":         [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "mobile":           [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "di động":          [CAT_MAJOR_FIELD, CAT_PROFESSION],
}


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TOOL 1 — LỘ TRÌNH HỌC THEO MỤC TIÊU                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def get_learning_path(goal: str) -> dict:
    goal_lower = goal.lower()

    # Tìm categories phù hợp với mục tiêu
    target_categories = []
    for keyword, cats in GOAL_CATEGORY_MAP.items():
        if keyword in goal_lower:
            target_categories.extend(cats)

    if not target_categories:
        target_categories = [CAT_MAJOR_FIELD, CAT_PROFESSION]

    target_categories = list(set(target_categories))

    # Luôn bao gồm môn nền tảng chung (toán, lập trình cơ bản)
    foundation_cats = [CAT_COMMON, CAT_MAJOR_GROUP, CAT_MAJOR_FIELD]

    all_cats = list(set(foundation_cats + target_categories))

    cypher = """
    MATCH (c:Course)-[:IN_CATEGORY]->(cc:CourseCategory)
    WHERE cc.name IN $categories
    OPTIONAL MATCH (c)-[:IN_SEMESTER]->(s:Semester)
    OPTIONAL MATCH (c)-[:PREREQUISITE]->(prereq:Course)
    RETURN
        c.id          AS id,
        c.name        AS name,
        c.credits     AS credits,
        c.is_elective AS is_elective,
        cc.name       AS category,
        s.number      AS semester_number,
        collect(prereq.id) AS prerequisites
    ORDER BY s.number, c.id
    """

    with get_driver().session() as session:
        result = session.run(cypher, categories=all_cats)
        courses = [dict(r) for r in result]

    # Nhóm theo học kỳ
    semesters = {}
    for c in courses:
        sem = c.get("semester_number") or 0
        key = f"Học kỳ {sem}" if sem > 0 else "Chưa xếp học kỳ"
        semesters.setdefault(key, []).append({
            "id":           c["id"],
            "name":         c["name"],
            "credits":      c["credits"],
            "is_elective":  c["is_elective"],
            "category":     c["category"],
            "prerequisites": [p for p in c["prerequisites"] if p],
        })

    return {
        "goal":               goal,
        "matched_categories": target_categories,
        "total_courses":      len(courses),
        "total_credits":      sum(c["credits"] or 0 for c in courses),
        "by_semester":        dict(sorted(semesters.items())),
    }


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TOOL 2 — KIỂM TRA TIÊN QUYẾT                                              ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def check_prerequisites(course_id: str, completed_courses: list = None) -> dict:
    completed_courses = [c.upper() for c in (completed_courses or [])]
    course_id = course_id.upper().strip()

    cypher = """
    MATCH (c:Course {id: $course_id})
    OPTIONAL MATCH (c)-[r:PREREQUISITE]->(prereq:Course)
    OPTIONAL MATCH (c)-[:IN_SEMESTER]->(s:Semester)
    OPTIONAL MATCH (c)-[:IN_CATEGORY]->(cc:CourseCategory)
    RETURN
        c.id          AS id,
        c.name        AS name,
        c.credits     AS credits,
        c.is_elective AS is_elective,
        cc.name       AS category,
        s.number      AS semester_number,
        collect({id: prereq.id, name: prereq.name, type: r.type}) AS prerequisites
    """

    with get_driver().session() as session:
        record = session.run(cypher, course_id=course_id).single()

    if not record:
        return {"error": f"Không tìm thấy môn học '{course_id}'. Hãy kiểm tra lại mã môn."}

    data    = dict(record)
    prereqs = [p for p in data["prerequisites"] if p.get("id")]
    missing = [p for p in prereqs if p["id"] not in completed_courses]

    return {
        "course": {
            "id":       data["id"],
            "name":     data["name"],
            "credits":  data["credits"],
            "category": data["category"],
            "semester": data["semester_number"],
        },
        "prerequisites":         prereqs,
        "completed_courses":     completed_courses,
        "missing_prerequisites": missing,
        "can_enroll":            len(missing) == 0,
        "message": (
            f"✅ Có thể đăng ký môn {data['name']}."
            if len(missing) == 0 else
            f"❌ Chưa đủ điều kiện. Cần hoàn thành trước: "
            f"{', '.join(p['name'] for p in missing)}"
        ),
    }


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TOOL 3 — TỐI ƯU KẾ HOẠCH HỌC KỲ                                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def optimize_semester_plan(
    completed_courses: list,
    target_credits_per_semester: int = 18,
    max_credits_per_semester:    int = 21,
) -> dict:
    completed_courses = [c.upper() for c in (completed_courses or [])]

    cypher = """
    MATCH (c:Course)
    WHERE NOT c.id IN $completed
    OPTIONAL MATCH (c)-[:PREREQUISITE]->(prereq:Course)
    OPTIONAL MATCH (c)-[:IN_SEMESTER]->(s:Semester)
    OPTIONAL MATCH (c)-[:IN_CATEGORY]->(cc:CourseCategory)
    RETURN
        c.id          AS id,
        c.name        AS name,
        c.credits     AS credits,
        c.is_elective AS is_elective,
        cc.name       AS category,
        s.number      AS suggested_semester,
        collect(prereq.id) AS prerequisites
    ORDER BY s.number
    """

    with get_driver().session() as session:
        remaining = [dict(r) for r in session.run(cypher, completed=completed_courses)]

    plan      = []
    scheduled = set(completed_courses)
    pending   = remaining.copy()
    semester  = 1

    while pending and semester <= 20:
        sem_courses = []
        sem_credits = 0
        next_round  = []

        pending.sort(key=lambda c: (
            not all(p in scheduled for p in c["prerequisites"] if p),
            c.get("suggested_semester") or 99,
            -(c["credits"] or 0),
        ))

        for course in pending:
            prereqs_ok = all(p in scheduled for p in course["prerequisites"] if p)
            cr = course["credits"] or 0

            if prereqs_ok and sem_credits + cr <= max_credits_per_semester:
                sem_courses.append(course)
                sem_credits += cr
                scheduled.add(course["id"])
                if sem_credits >= target_credits_per_semester:
                    break
            else:
                next_round.append(course)

        if not sem_courses:
            break  # tránh vòng lặp vô hạn

        plan.append({
            "semester":      semester,
            "courses":       sem_courses,
            "total_credits": sem_credits,
        })

        pending = [c for c in pending if c not in sem_courses]
        semester += 1

    return {
        "completed_count":    len(completed_courses),
        "remaining_count":    len(remaining),
        "remaining_credits":  sum(c["credits"] or 0 for c in remaining),
        "target_per_sem":     target_credits_per_semester,
        "estimated_semesters": len(plan),
        "plan":               plan,
        "stuck_courses":      pending,
    }


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TOOL 4 — HỎI ĐÁP TỰ DO                                                   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def query_program_info(question: str) -> dict:
    q       = question.lower()
    results = {}

    with get_driver().session() as session:

        # Thông tin chương trình
        if any(k in q for k in ["chương trình", "tổng", "tín chỉ", "bao nhiêu", "ngành", "trường"]):
            r = session.run("""
                MATCH (p:Program)
                RETURN p.name AS name, p.code AS code,
                       p.total_credits AS total_credits,
                       p.degree_level AS degree_level,
                       p.duration_years AS duration_years,
                       p.year AS year
            """)
            results["program_info"] = [dict(rec) for rec in r]

        # Tìm môn học theo mã hoặc tên
        if any(k in q for k in ["môn", "học phần", "mã", "comp", "poli", "educ", "phyl", "psyc", "mili", "doms"]):
            codes = re.findall(r'\b[A-Z]{3,4}\d{1,4}\b', question.upper())
            if codes:
                r = session.run("""
                    MATCH (c:Course) WHERE c.id IN $codes
                    OPTIONAL MATCH (c)-[:IN_SEMESTER]->(s:Semester)
                    OPTIONAL MATCH (c)-[:IN_CATEGORY]->(cc:CourseCategory)
                    OPTIONAL MATCH (c)-[:PREREQUISITE]->(prereq:Course)
                    RETURN c.id AS id, c.name AS name, c.credits AS credits,
                           c.is_elective AS is_elective,
                           s.number AS semester, cc.name AS category,
                           collect(prereq.name) AS prerequisites
                """, codes=codes)
                results["courses"] = [dict(rec) for rec in r]
            else:
                # Tìm theo tên — lấy các từ có nghĩa (> 3 ký tự)
                words = [w for w in q.split() if len(w) > 3
                         and w not in ["môn", "học", "phần", "trong", "theo", "như", "thế", "nào", "bạn"]]
                if words:
                    r = session.run("""
                        MATCH (c:Course)
                        WHERE any(w IN $words WHERE toLower(c.name) CONTAINS w)
                        OPTIONAL MATCH (c)-[:IN_SEMESTER]->(s:Semester)
                        OPTIONAL MATCH (c)-[:IN_CATEGORY]->(cc:CourseCategory)
                        RETURN c.id AS id, c.name AS name,
                               c.credits AS credits,
                               c.is_elective AS is_elective,
                               s.number AS semester,
                               cc.name AS category
                        LIMIT 15
                    """, words=words)
                    results["courses"] = [dict(rec) for rec in r]

        # PLO / Chuẩn đầu ra
        if any(k in q for k in ["plo", "chuẩn đầu ra", "đầu ra", "mục tiêu", "năng lực", "pi "]):
            r = session.run("""
                MATCH (plo:PLO)
                OPTIONAL MATCH (plo)-[:HAS_INDICATOR]->(pi:PI)
                WITH plo, collect(pi.description) AS indicators
                RETURN plo.code AS code, plo.description AS description,
                       plo.type AS type, size(indicators) AS pi_count,
                       indicators
                ORDER BY plo.number
            """)
            results["plos"] = [dict(rec) for rec in r]

        # Học kỳ
        if any(k in q for k in ["học kỳ", "semester", "hk", "kỳ "]):
            r = session.run("""
                MATCH (s:Semester)
                OPTIONAL MATCH (c:Course)-[:IN_SEMESTER]->(s)
                WITH s, count(c) AS num_courses,
                     collect(c.name)[..5] AS sample_courses
                RETURN s.name AS name, s.number AS number,
                       s.total_credits AS total_credits,
                       s.year AS year,
                       num_courses, sample_courses
                ORDER BY s.number
            """)
            results["semesters"] = [dict(rec) for rec in r]

        # Vị trí việc làm
        if any(k in q for k in ["việc làm", "nghề nghiệp", "vị trí", "job", "career", "sau khi tốt nghiệp", "ra trường"]):
            r = session.run("""
                MATCH (j:JobPosition)
                RETURN j.name AS name, j.category AS category,
                       j.description AS description
                ORDER BY j.category
            """)
            results["job_positions"] = [dict(rec) for rec in r]

        # Môn tự chọn
        if any(k in q for k in ["tự chọn", "elective", "chọn"]):
            r = session.run("""
                MATCH (c:Course {is_elective: true})
                OPTIONAL MATCH (c)-[:IN_CATEGORY]->(cc:CourseCategory)
                OPTIONAL MATCH (c)-[:IN_SEMESTER]->(s:Semester)
                RETURN c.id AS id, c.name AS name,
                       c.credits AS credits,
                       cc.name AS category,
                       s.number AS semester
                ORDER BY s.number, cc.name
            """)
            results["elective_courses"] = [dict(rec) for rec in r]

        # Thống kê tổng quan (fallback)
        if not results:
            r = session.run("""
                MATCH (c:Course)   WITH count(c) AS total_courses
                MATCH (plo:PLO)    WITH total_courses, count(plo) AS total_plos
                MATCH (s:Semester) WITH total_courses, total_plos, count(s) AS total_sems
                MATCH (p:Program)  WITH total_courses, total_plos, total_sems,
                                        p.name AS prog_name, p.total_credits AS prog_credits
                RETURN total_courses, total_plos, total_sems, prog_name, prog_credits
            """)
            results["overview"] = [dict(rec) for rec in r]

    results["original_question"] = question
    return results