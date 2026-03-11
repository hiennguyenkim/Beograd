"""
database.py
===========
Neo4jImporter — nhập toàn bộ dữ liệu curriculum vào Neo4j Knowledge Graph

Sử dụng:
    from database import Neo4jImporter
    importer = Neo4jImporter(uri, user, password)
    importer.import_curriculum_data(data)
    importer.close()
"""

import traceback
from neo4j import GraphDatabase


class Neo4jImporter:
    """
    Import dữ liệu chương trình đào tạo vào Neo4j.

    Node types  : Program, PLO, PI, Course, Semester, JobPosition,
                  CourseCategory, Department
    Relationships: OUTCOME_OF, HAS_INDICATOR, BELONGS_TO, PREREQUISITE,
                   IN_SEMESTER, SEMESTER_OF, JOB_FOR, IN_CATEGORY,
                   CATEGORY_OF, MANAGED_BY, DEPARTMENT_OF, CONTRIBUTES_TO
    """

    # Mapping category → PLO (dùng cho CONTRIBUTES_TO)
    COURSE_PLO_MAPPING = {
        'Nền tảng':         ['PLO1', 'PLO2', 'PLO3'],
        'Chuyên môn chung': ['PLO3', 'PLO4', 'PLO5'],
        'Chuyên môn ngành': ['PLO5', 'PLO6'],
        'Nghiệp vụ':        ['PLO6', 'PLO7', 'PLO8', 'PLO9'],
        'Thực hành':        ['PLO9', 'PLO10'],
        'Tốt nghiệp':       ['PLO10'],
    }

    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(
            uri, auth=(user, password),
            connection_timeout=30,
            max_transaction_retry_time=15,
        )
        self.stats = {'nodes_created': 0, 'relationships_created': 0, 'errors': 0}

    def close(self):
        self.driver.close()

    # ── setup ─────────────────────────────────────────────────────────────────

    def clear_database(self):
        print("\n=== XÓA DỮ LIỆU CŨ ===")
        with self.driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
        print("   ✓ Đã xóa dữ liệu cũ")

    def create_constraints(self):
        print("\n=== TẠO RÀNG BUỘC VÀ INDEX ===")
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Program)  REQUIRE p.code  IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Course)   REQUIRE c.id    IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (plo:PLO)    REQUIRE plo.code IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (pi:PI)      REQUIRE pi.code  IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Semester) REQUIRE s.name  IS UNIQUE",
        ]
        with self.driver.session() as s:
            for c in constraints:
                try:
                    s.run(c)
                except Exception:
                    pass
        print("   ✓ Đã tạo constraints")

    # ── import steps ──────────────────────────────────────────────────────────

    def _import_program(self, s, info: dict, pc: str):
        print("1. Tạo Program node...")
        s.run("""
            CREATE (p:Program {
                code:$code, name:$name, degree_level:$dl,
                training_form:$tf, total_credits:$tc,
                duration_years:$dy, year:$yr
            })
        """,
        code=pc,
        name=info.get('program_name', ''),
        dl=info.get('degree_level', ''),
        tf=info.get('training_form', ''),
        tc=info.get('total_credits', 0),
        dy=info.get('duration_years', 0),
        yr=info.get('year', ''))
        self.stats['nodes_created'] += 1

    def _import_plos(self, s, plos: list, pc: str):
        print("2. Tạo PLO nodes...")
        for plo in plos:
            s.run("""
                CREATE (plo:PLO {
                    code:$code, number:$num,
                    description:$desc, type:$type
                })
                WITH plo
                MATCH (p:Program {code:$pc})
                CREATE (plo)-[:OUTCOME_OF]->(p)
            """,
            code=plo['code'], num=plo['number'],
            desc=plo['description'], type=plo['type'], pc=pc)
            self.stats['nodes_created'] += 1
            self.stats['relationships_created'] += 1

    def _import_pis(self, s, pis: list):
        print("3. Tạo PI nodes...")
        for pi in pis:
            s.run("""
                CREATE (pi:PI {
                    code:$code, full_code:$fc, description:$desc
                })
                WITH pi
                MATCH (plo:PLO {code:$ploc})
                CREATE (plo)-[:HAS_INDICATOR]->(pi)
            """,
            code=pi['code'], fc=pi['full_code'],
            desc=pi['description'], ploc=pi['plo_code'])
            self.stats['nodes_created'] += 1
            self.stats['relationships_created'] += 1

    def _import_courses(self, s, courses: dict, pc: str):
        print("4. Tạo Course nodes...")
        for cid, c in courses.items():
            s.run("""
                CREATE (c:Course {
                    id:$id, name:$name, credits:$cr,
                    is_elective:$ie, department:$dept, category:$cat
                })
                WITH c
                MATCH (p:Program {code:$pc})
                CREATE (c)-[:BELONGS_TO]->(p)
            """,
            id=cid, name=c['name'], cr=c['credits'],
            ie=c['is_elective'], dept=c['department'],
            cat=c['category'], pc=pc)
            self.stats['nodes_created'] += 1
            self.stats['relationships_created'] += 1

    def _import_prerequisites(self, s, prereqs: list):
        print("5. Tạo quan hệ tiên quyết...")
        for pr in prereqs:
            s.run("""
                MATCH (c1:Course {id:$c})
                MATCH (c2:Course {id:$p})
                MERGE (c1)-[:PREREQUISITE {type:$t}]->(c2)
            """,
            c=pr['course'], p=pr['prerequisite'], t=pr['type'])
            self.stats['relationships_created'] += 1

    def _import_semesters(self, s, semesters: dict, pc: str):
        print("6. Tạo Semester nodes...")
        for sem in semesters.values():
            s.run("""
                CREATE (s:Semester {
                    name:$name, number:$num,
                    total_credits:$tc, year:$yr
                })
                WITH s
                MATCH (p:Program {code:$pc})
                CREATE (s)-[:SEMESTER_OF]->(p)
            """,
            name=sem['name'], num=sem['number'],
            tc=sem['total_credits'], yr=sem['year'], pc=pc)
            self.stats['nodes_created'] += 1
            self.stats['relationships_created'] += 1

            for cid in sem['courses']:
                try:
                    s.run("""
                        MATCH (c:Course {id:$ci})
                        MATCH (sem:Semester {name:$sn})
                        MERGE (c)-[:IN_SEMESTER]->(sem)
                    """,
                    ci=cid, sn=sem['name'])
                    self.stats['relationships_created'] += 1
                except Exception as e:
                    print(f"   ⚠️  IN_SEMESTER {cid}: {e}")
                    self.stats['errors'] += 1

    def _import_jobs(self, s, jobs: list, pc: str):
        print("7. Tạo JobPosition nodes...")
        for j in jobs:
            s.run("""
                CREATE (j:JobPosition {
                    name:$n, category:$cat, description:$desc
                })
                WITH j
                MATCH (p:Program {code:$pc})
                CREATE (j)-[:JOB_FOR]->(p)
            """,
            n=j['name'], cat=j['category'],
            desc=j.get('description', ''), pc=pc)
            self.stats['nodes_created'] += 1
            self.stats['relationships_created'] += 1

    def _import_categories_and_departments(self, s, courses: dict, pc: str):
        print("8. Tạo CourseCategory và Department nodes...")
        for attr, label, cat_rel, sub_rel in [
            ('category',   'CourseCategory', 'CATEGORY_OF',   'IN_CATEGORY'),
            ('department', 'Department',     'DEPARTMENT_OF', 'MANAGED_BY'),
        ]:
            for val in set(c[attr] for c in courses.values()):
                s.run(
                    f"MERGE (n:{label} {{name:$n}}) "
                    f"WITH n MATCH (p:Program {{code:$pc}}) "
                    f"MERGE (n)-[:{cat_rel}]->(p)",
                    n=val, pc=pc)
                self.stats['nodes_created'] += 1
                self.stats['relationships_created'] += 1

                for cid, c in courses.items():
                    if c[attr] == val:
                        s.run(
                            f"MATCH (c:Course {{id:$ci}}) "
                            f"MATCH (n:{label} {{name:$n}}) "
                            f"MERGE (c)-[:{sub_rel}]->(n)",
                            ci=cid, n=val)
                        self.stats['relationships_created'] += 1

    def _import_contributes_to(self, s, courses: dict):
        print("9. Tạo quan hệ CONTRIBUTES_TO...")
        for cid, c in courses.items():
            for plo_code in self.COURSE_PLO_MAPPING.get(c['category'], []):
                try:
                    s.run("""
                        MATCH (c:Course {id:$ci})
                        MATCH (p:PLO {code:$pc})
                        MERGE (c)-[:CONTRIBUTES_TO {strength:'MEDIUM'}]->(p)
                    """,
                    ci=cid, pc=plo_code)
                    self.stats['relationships_created'] += 1
                except Exception:
                    self.stats['errors'] += 1

    # ── main entry point ──────────────────────────────────────────────────────

    def import_curriculum_data(self, data: dict):
        print("\n=== BẮT ĐẦU IMPORT VÀO NEO4J ===")
        try:
            self.clear_database()
            self.create_constraints()

            pc = data['program_info'].get('program_code', '')

            with self.driver.session() as s:
                self._import_program(s, data['program_info'], pc)
                self._import_plos(s, data['learning_outcomes'], pc)
                self._import_pis(s, data['program_indicators'])
                self._import_courses(s, data['courses'], pc)
                self._import_prerequisites(s, data['prerequisites'])
                self._import_semesters(s, data['semesters'], pc)
                self._import_jobs(s, data['job_positions'], pc)
                self._import_categories_and_departments(s, data['courses'], pc)
                self._import_contributes_to(s, data['courses'])

            print("\n=== HOÀN THÀNH IMPORT ===")
            print(f"  ✓ Nodes         : {self.stats['nodes_created']}")
            print(f"  ✓ Relationships : {self.stats['relationships_created']}")
            print(f"  ⚠ Errors        : {self.stats['errors']}")

            self._print_sample_queries()

        except Exception as e:
            print(f"❌ Lỗi: {e}")
            traceback.print_exc()
            self.stats['errors'] += 1
            raise

    # ── sample queries ────────────────────────────────────────────────────────

    def _print_sample_queries(self):
        print("\n=== CÂU TRUY VẤN MẪU ===")
        queries = [
            ("Thông tin chương trình",
             "MATCH (p:Program) RETURN p.name, p.code, p.total_credits LIMIT 1"),
            ("Tổng số môn học",
             "MATCH (c:Course) RETURN count(c) AS total_courses"),
            ("Môn học theo học kỳ",
             "MATCH (c:Course)-[:IN_SEMESTER]->(s:Semester) "
             "WITH s, count(c) AS n RETURN s.name, n ORDER BY s.number"),
            ("Môn học có tiên quyết",
             "MATCH (c:Course)-[:PREREQUISITE]->(p:Course) "
             "RETURN c.id, c.name, collect(p.id) AS prerequisites LIMIT 5"),
            ("PLO và số PI",
             "MATCH (plo:PLO)-[:HAS_INDICATOR]->(pi:PI) "
             "WITH plo, count(pi) AS n "
             "RETURN plo.code, n ORDER BY plo.code LIMIT 5"),
            ("Vị trí việc làm",
             "MATCH (j:JobPosition) RETURN j.name, j.category LIMIT 5"),
        ]
        with self.driver.session() as s:
            for i, (title, query) in enumerate(queries, 1):
                try:
                    records = list(s.run(query))
                    print(f"\n{i}. {title}:")
                    for rec in records[:3]:
                        print(f"   {dict(rec)}")
                    if not records:
                        print("   (Không có dữ liệu)")
                except Exception as e:
                    print(f"   ❌ {e}")