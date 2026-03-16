"""
neo4j_tools.py
==============
Các tool để agent query trực tiếp từ Neo4j Knowledge Graph.
Database ID: 349190b5
"""

import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URL      = os.environ.get("NEO4J_URI",      os.environ.get("NEO4J_URL",  ""))
NEO4J_USER     = os.environ.get("NEO4J_USERNAME", os.environ.get("NEO4J_USER", ""))
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

# ── Driver singleton ──────────────────────────────────────────────────────────

_driver = None

def get_driver():
    global _driver
    if _driver is None:
        if not NEO4J_URL or not NEO4J_USER or not NEO4J_PASSWORD:
            raise ValueError("Neo4j chưa cấu hình trong file .env!")
        _driver = GraphDatabase.driver(
            NEO4J_URL, auth=(NEO4J_USER, NEO4J_PASSWORD),
            connection_timeout=30,
        )
        print(f"   ✓ Neo4j connected: {NEO4J_URL}")
    return _driver

def close_driver():
    global _driver
    if _driver:
        _driver.close()
        _driver = None


# ── Hằng số category ────────────────────────────────────────────────────────

CAT_COMMON          = "Học phần chung"
CAT_MAJOR_GROUP     = "Chuyên môn chung nhóm ngành"
CAT_MAJOR_FIELD     = "Chuyên môn chung lĩnh vực"
CAT_PROFESSION_BASE = "Nghiệp vụ chung"
CAT_PROFESSION      = "Nghiệp vụ ngành"
CAT_PRACTICE        = "Thực hành nghề nghiệp"
CAT_GRADUATION      = "Tốt nghiệp"

GOAL_CATEGORY_MAP = {
    "lập trình":        [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "ai":               [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "mạng":             [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "web":              [CAT_MAJOR_FIELD, CAT_PROFESSION],
    "bảo mật":          [CAT_MAJOR_FIELD, CAT_PROFESSION],
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TOOL 1 — LỘ TRÌNH HỌC THEO MỤC TIÊU                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def get_learning_path(goal: str) -> dict:
    goal_lower = goal.lower()
    target_categories = []
    for keyword, cats in GOAL_CATEGORY_MAP.items():
        if keyword in goal_lower:
            target_categories.extend(cats)

    if not target_categories:
        target_categories = [CAT_MAJOR_FIELD, CAT_PROFESSION]

    all_cats = list(set([CAT_COMMON, CAT_MAJOR_GROUP, CAT_MAJOR_FIELD] + target_categories))

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

    with get_driver().session(database="349190b5") as session:
        result = session.run(cypher, categories=all_cats)
        courses = [dict(r) for r in result]

    semesters = {}
    for c in courses:
        sem = c.get("semester_number") or 0
        key = f"Học kỳ {sem}" if sem > 0 else "Chưa xếp học kỳ"
        semesters.setdefault(key, []).append({
            "id": c["id"], "name": c["name"], "credits": c["credits"],
            "is_elective": c["is_elective"], "category": c["category"],
            "prerequisites": [p for p in c["prerequisites"] if p],
        })

    return {
        "goal": goal,
        "total_courses": len(courses),
        "by_semester": dict(sorted(semesters.items())),
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
        cc.name       AS category,
        s.number      AS semester_number,
        collect({id: prereq.id, name: prereq.name, type: r.type}) AS prerequisites
    """

    with get_driver().session(database="349190b5") as session:
        record = session.run(cypher, course_id=course_id).single()

    if not record:
        return {"error": f"Không tìm thấy môn học '{course_id}'."}

    data = dict(record)
    prereqs = [p for p in data["prerequisites"] if p.get("id")]
    missing = [p for p in prereqs if p["id"] not in completed_courses]

    return {
        "course": data,
        "missing_prerequisites": missing,
        "can_enroll": len(missing) == 0,
        "message": "✅ Có thể đăng ký." if not missing else f"❌ Thiếu: {', '.join(p['name'] for p in missing)}"
    }

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TOOL 3 — TỐI ƯU KẾ HOẠCH HỌC KỲ                                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def optimize_semester_plan(completed_courses: list, target_credits: int = 18) -> dict:
    completed_courses = [c.upper() for c in (completed_courses or [])]

    cypher = """
    MATCH (c:Course)
    WHERE NOT c.id IN $completed
    OPTIONAL MATCH (c)-[:PREREQUISITE]->(prereq:Course)
    OPTIONAL MATCH (c)-[:IN_SEMESTER]->(s:Semester)
    RETURN
        c.id AS id, c.name AS name, c.credits AS credits,
        s.number AS suggested_semester,
        collect(prereq.id) AS prerequisites
    ORDER BY s.number
    """

    with get_driver().session(database="349190b5") as session:
        remaining = [dict(r) for r in session.run(cypher, completed=completed_courses)]

    # Logic tối ưu cơ bản
    plan = []
    scheduled = set(completed_courses)
    pending = remaining.copy()

    for sem in range(1, 11):
        if not pending: break
        sem_courses = []
        sem_credits = 0
        for course in list(pending):
            if all(p in scheduled for p in course["prerequisites"] if p) and sem_credits + course["credits"] <= 21:
                sem_courses.append(course)
                sem_credits += course["credits"]
                scheduled.add(course["id"])
                pending.remove(course)
        plan.append({"semester": sem, "courses": sem_courses, "total_credits": sem_credits})

    return {"plan": plan}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TOOL 4 — THÔNG TIN TỔNG QUAN CHƯƠNG TRÌNH                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def get_program_overview() -> dict:
    """Lấy thông tin tổng quan về chương trình đào tạo"""
    cypher = """
    MATCH (p:Program)
    RETURN p.code AS code, p.name AS name, p.total_credits AS credits, p.duration_years AS duration
    LIMIT 1
    """
    with get_driver().session(database="349190b5") as session:
        record = session.run(cypher).single()
        return dict(record) if record else {"error": "Không tìm thấy dữ liệu chương trình."}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TOOL 5 — TRA CỨU CHI TIẾT MÔN HỌC                                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def get_course_details(course_name: str) -> dict:
    """Tra cứu chi tiết một môn học (tín chỉ, học kỳ, tiên quyết, loại môn)"""
    cypher = """
    MATCH (c:Course)
    WHERE toLower(c.name) CONTAINS toLower($course_name) OR toLower(c.id) CONTAINS toLower($course_name)
    OPTIONAL MATCH (c)-[:IN_SEMESTER]->(s:Semester)
    OPTIONAL MATCH (c)-[:IN_CATEGORY]->(cat:CourseCategory)
    OPTIONAL MATCH (c)-[:PREREQUISITE]->(pre:Course)
    RETURN c.id AS id, c.name AS name, c.credits AS credits, 
           c.is_elective AS is_elective, s.name AS semester, cat.name AS category,
           collect(pre.id + ' - ' + pre.name) AS prerequisites
    LIMIT 5
    """
    with get_driver().session(database="349190b5") as session:
        results = [dict(r) for r in session.run(cypher, course_name=course_name)]
        return {"courses": results} if results else {"error": f"Không tìm thấy môn học nào khớp với '{course_name}'."}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  TOOL 6 — CƠ HỘI VIỆC LÀM                                                 ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def get_job_opportunities() -> dict:
    """Lấy danh sách các vị trí việc làm sau khi tốt nghiệp"""
    cypher = """
    MATCH (j:JobPosition)-[:JOB_FOR]->(p:Program)
    RETURN j.name AS job_name, j.category AS category, j.description AS description
    """
    with get_driver().session(database="349190b5") as session:
        results = [dict(r) for r in session.run(cypher)]
        return {"jobs": results} if results else {"error": "Chưa có dữ liệu vị trí việc làm cho chương trình này."}