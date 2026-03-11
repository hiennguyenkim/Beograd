"""
extractor.py
============
GPTExtractor        — trích xuất thông minh bằng LLM (llm7.io / OpenAI-compatible)
CurriculumExtractor — trích xuất toàn bộ dữ liệu từ PDF chương trình đào tạo
"""

import pdfplumber
import re
import json
import os
import traceback
from dotenv import load_dotenv

load_dotenv()

try:
    from openai import OpenAI as _OpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

class GPTExtractor:
    """
    Dùng OpenAI GPT để trích xuất dữ liệu từ đoạn văn bản PDF.
    Tự động fallback về regex nếu không có API key hoặc thư viện.
    """
    MODEL     = "gpt-4o-mini"
    MAX_CHUNK = 3000

    def __init__(self, api_key: str = ""):
        self.enabled = False
        self.client  = None

        if not _OPENAI_AVAILABLE:
            print("   ⚠️  openai chưa được cài (pip install openai). Dùng regex fallback.")
            return
        if not api_key:
            print("   ⚠️  OPENAI_API_KEY chưa được set. Dùng regex fallback.")
            return

        self.client  = _OpenAI(api_key=api_key)
        self.enabled = True
        print("   ✓  GPT extractor sẵn sàng.")

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.MODEL,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user",   "content": user_prompt}],
            temperature=0, max_tokens=2048,
        )
        return resp.choices[0].message.content.strip()

    def _safe_json(self, text: str):
        text = re.sub(r"```(?:json)?", "", text).strip().strip("`")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def extract_plo_pi(self, raw_text: str) -> list:
        if not self.enabled:
            return []
        system = ("Bạn là chuyên gia phân tích chương trình đào tạo đại học Việt Nam. "
                  "Chỉ trả về JSON, không giải thích thêm.")
        prompt = f"""
Từ đoạn văn bản sau, trích xuất tất cả Chuẩn đầu ra chương trình (PLO) và
Chỉ số thực hiện (PI). Trả về JSON theo đúng schema:
{{
  "plos": [
    {{
      "code": "PLO1", "number": 1, "description": "...",
      "type": "PHAM_CHAT|NANG_LUC_CHUNG|NANG_LUC_CHUYEN_MON|NANG_LUC_NGHE_NGHIEP|KHAC",
      "indicators": [
        {{"code": "PI1_1", "full_code": "PI 1.1", "description": "..."}}
      ]
    }}
  ]
}}
VĂN BẢN:
{raw_text[:self.MAX_CHUNK]}
"""
        result = self._safe_json(self._chat(system, prompt))
        if result and "plos" in result:
            print(f"   🤖 GPT trích xuất {len(result['plos'])} PLO")
            return result["plos"]
        return []

    def extract_courses(self, raw_text: str) -> list:
        if not self.enabled:
            return []
        system = ("Bạn là chuyên gia phân tích chương trình đào tạo đại học Việt Nam. "
                  "Chỉ trả về JSON, không giải thích thêm.")
        prompt = f"""
Từ đoạn văn bản sau, trích xuất danh sách học phần. Trả về JSON:
{{
  "courses": [
    {{
      "id": "COMP1001", "name": "Lập trình cơ bản", "credits": 3,
      "is_elective": false, "prerequisite": "", "co_requisite": "", "support_course": ""
    }}
  ]
}}
VĂN BẢN:
{raw_text[:self.MAX_CHUNK]}
"""
        result = self._safe_json(self._chat(system, prompt))
        if result and "courses" in result:
            print(f"   🤖 GPT trích xuất {len(result['courses'])} môn học")
            return result["courses"]
        return []

    def enrich_job_positions(self, raw_text: str) -> list:
        if not self.enabled:
            return []
        system = ("Bạn là chuyên gia phân tích chương trình đào tạo đại học Việt Nam. "
                  "Chỉ trả về JSON, không giải thích thêm.")
        prompt = f"""
Từ đoạn văn bản sau, trích xuất tất cả vị trí việc làm sau tốt nghiệp.
Trả về JSON:
{{
  "positions": [
    {{"name": "Lập trình viên", "category": "Phát triển phần mềm", "description": "..."}}
  ]
}}
VĂN BẢN:
{raw_text[:self.MAX_CHUNK]}
"""
        result = self._safe_json(self._chat(system, prompt))
        if result and "positions" in result:
            print(f"   🤖 GPT trích xuất {len(result['positions'])} vị trí việc làm")
            return result["positions"]
        return []


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  CURRICULUM EXTRACTOR                                                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

class CurriculumExtractor:
    def __init__(self, pdf_path: str, gpt_extractor=None):
        self.pdf_path = pdf_path
        self.gpt      = gpt_extractor
        self.data = {
            'program_info': {}, 'learning_outcomes': [],
            'program_indicators': [], 'courses': {},
            'semesters': {}, 'job_positions': [],
            'credit_distribution': {}, 'teaching_methods': {},
            'evaluation_methods': {}, 'prerequisites': []
        }

    def clean_text(self, text: str) -> str:
        if not text:
            return ""
        return re.sub(r'[\x00-\x1f\x7f-\x9f]', '', re.sub(r'\s+', ' ', text)).strip()

    # ── 1. Program info ───────────────────────────────────────────────────────

    def extract_program_info(self, pages):
        print("1. Trích xuất thông tin chương trình...")
        full_text = "".join(p.extract_text() or "" for p in pages[:10])
        patterns = {
            'program_name':             r'TÊN CHƯƠNG TRÌNH\s*[:：]\s*([^\n]+)',
            'program_code':             r'MÃ NGÀNH ĐÀO TẠO\s*[:：]\s*(\d+)',
            'degree_level':             r'TRÌNH ĐỘ ĐÀO TẠO\s*[:：]\s*([^\n]+)',
            'training_form':            r'HÌNH THỨC ĐÀO TẠO\s*[:：]\s*([^\n]+)',
            'graduation_certificate_vi':r'[-–]\s*TIẾNG VIỆT\s*[:：]\s*([^\n]+)',
            'duration_years':           r'(\d+)\s*năm\s*\((\d+)\s*học\s*k[ìỳy]',
            'year':                     r'năm\s*(20\d{2})',
        }
        for key, pat in patterns.items():
            m = re.search(pat, full_text, re.IGNORECASE)
            if m:
                if key == 'duration_years':
                    self.data['program_info'][key]             = int(m.group(1))
                    self.data['program_info']['num_semesters']  = int(m.group(2))
                else:
                    self.data['program_info'][key] = self.clean_text(m.group(1))
        for pat in [r'Tổng số tín chỉ.*?là\s*(\d+)\s*tín chỉ',
                    r'Tổng số tín chỉ.*?[:：]\s*(\d+)']:
            m = re.search(pat, full_text, re.IGNORECASE)
            if m:
                self.data['program_info']['total_credits'] = int(m.group(1))
                break
        print(f"   ✓ Tên: {self.data['program_info'].get('program_name','N/A')}")
        print(f"   ✓ Mã : {self.data['program_info'].get('program_code','N/A')}")
        print(f"   ✓ TC : {self.data['program_info'].get('total_credits','N/A')}")

    # ── 2. PLO / PI ───────────────────────────────────────────────────────────

    def extract_learning_outcomes(self, pages):
        print("2. Trích xuất chuẩn đầu ra (PLO/PI)...")
        full_text = "\n\n".join(p.extract_text() or "" for p in pages)

        # GPT ưu tiên
        if self.gpt and self.gpt.enabled:
            gpt_plos = self.gpt.extract_plo_pi(full_text)
            if gpt_plos:
                for plo in gpt_plos:
                    plo.setdefault('type', self.classify_plo(plo.get('description', '')))
                    for ind in plo.get('indicators', []):
                        ind['plo_code'] = plo['code']
                        self.data['program_indicators'].append(ind)
                    self.data['learning_outcomes'].append(plo)
                print(f"   ✓ {len(self.data['learning_outcomes'])} PLO, "
                      f"{len(self.data['program_indicators'])} PI (GPT)")
                return

        # Regex fallback
        SKIP = {'PHẨM CHẤT','NĂNG LỰC CHUNG','NĂNG LỰC CHUYÊN MÔN',
                'NĂNG LỰC NGHỀ NGHIỆP','MÃ CĐR','CHUẨN ĐẦU RA'}
        current, desc_lines = None, []

        for line in full_text.split('\n'):
            line = self.clean_text(line)
            if not line or len(line) < 3:
                continue
            m_plo = re.match(r'^PLO\s*(\d+)\s*(.*)$', line, re.IGNORECASE)
            if m_plo:
                self._flush_plo(current, desc_lines)
                num = m_plo.group(1)
                current = {'code': f'PLO{num}', 'number': int(num),
                           'description': '', 'type': '', 'indicators': []}
                desc_lines = [m_plo.group(2).strip()] if m_plo.group(2).strip() else []
                continue
            m_pi = re.match(r'^PI\s*(\d+)\.(\d+)\s*(.*)$', line, re.IGNORECASE)
            if m_pi and current:
                pn, pin, desc = m_pi.group(1), m_pi.group(2), m_pi.group(3).strip()
                if int(pn) == current['number']:
                    ind = {'code': f'PI{pn}_{pin}', 'full_code': f'PI {pn}.{pin}',
                           'description': desc, 'plo_code': current['code']}
                    current['indicators'].append(ind)
                    self.data['program_indicators'].append(ind)
                continue
            if current and not any(s in line.upper() for s in SKIP):
                if len(line) > 15 and not line.upper().startswith('PI'):
                    desc_lines.append(line)

        self._flush_plo(current, desc_lines)
        print(f"   ✓ {len(self.data['learning_outcomes'])} PLO, "
              f"{len(self.data['program_indicators'])} PI (regex)")

    def _flush_plo(self, plo, lines):
        if plo and lines:
            plo['description'] = self.clean_text(' '.join(lines))
            plo['type']        = self.classify_plo(plo['description'])
            self.data['learning_outcomes'].append(plo)
            print(f"   ✓ {plo['code']}: {plo['description'][:60]}...")

    def classify_plo(self, desc: str) -> str:
        d = desc.lower()
        if 'phẩm chất' in d or ('trách nhiệm' in d and 'công dân' in d): return 'PHAM_CHAT'
        if 'nhân văn' in d or 'bền vững' in d:                            return 'PHAM_CHAT'
        if 'giao tiếp' in d or 'hợp tác' in d:                            return 'NANG_LUC_CHUNG'
        if 'giải quyết vấn đề' in d:                                       return 'NANG_LUC_CHUNG'
        if 'chuyên môn' in d or 'chuyên ngành' in d:                      return 'NANG_LUC_CHUYEN_MON'
        if 'khởi nghiệp' in d:                                             return 'NANG_LUC_NGHE_NGHIEP'
        if 'nghề nghiệp' in d or 'sự nghiệp' in d:                        return 'NANG_LUC_NGHE_NGHIEP'
        if 'nghiên cứu' in d:                                              return 'NANG_LUC_NGHE_NGHIEP'
        return 'KHAC'

    # ── 3. Courses ────────────────────────────────────────────────────────────

    def extract_courses_from_tables(self, pages):
        print("3. Trích xuất môn học từ bảng...")
        course_pat = re.compile(r'^([A-Z]{4}\d{1,4})$')
        found = {}

        # GPT
        if self.gpt and self.gpt.enabled:
            sample = "\n".join(p.extract_text() or "" for p in pages[5:20])
            for c in self.gpt.extract_courses(sample):
                cid = c.get('id', '')
                if course_pat.match(cid):
                    c.setdefault('department', self.get_department(cid))
                    c.setdefault('category',   self.get_category(cid))
                    found[cid] = c

        # Bảng regex (bổ sung GPT)
        for page in pages:
            for table in (page.extract_tables() or []):
                if not table or len(table) < 2: continue
                header, hidx = None, 0
                for ri, row in enumerate(table[:5]):
                    if row and any('Mã HP' in str(c) or 'Mã học phần' in str(c)
                                   for c in row if c):
                        header = [self.clean_text(str(c)) if c else "" for c in row]
                        hidx   = ri; break
                if not header: continue

                col = {}
                for i, h in enumerate(header):
                    hl = h.lower()
                    if   'mã hp'        in hl or 'mã học phần' in hl: col['id']      = i
                    elif 'tên hp'       in hl or 'tên học phần' in hl: col['name']    = i
                    elif 'số tc'        in hl or 'tín chỉ'      in hl: col['credits'] = i
                    elif 'tiên quyết'   in hl:                          col['prereq']  = i
                    elif 'học trước'    in hl:                          col['coreq']   = i
                    elif 'hỗ trợ'       in hl or 'song hành'    in hl: col['support'] = i
                    elif 'tự chọn'      in hl:                          col['elective']= i

                for row in table[hidx + 1:]:
                    if not row: continue
                    cr = [self.clean_text(str(c)) if c else "" for c in row]
                    cid = None
                    if 'id' in col and col['id'] < len(cr) and course_pat.match(cr[col['id']]):
                        cid = cr[col['id']]
                    if not cid:
                        for cell in cr:
                            if course_pat.match(cell): cid = cell; break
                    if not cid: continue

                    name = cr[col['name']] if 'name' in col and col['name'] < len(cr) else ""
                    credits = 0
                    if 'credits' in col and col['credits'] < len(cr):
                        try: credits = int(cr[col['credits']])
                        except (ValueError, IndexError): pass
                    if credits == 0:
                        for cell in cr:
                            if cell.isdigit() and 1 <= int(cell) <= 10:
                                credits = int(cell); break

                    def rel(k):
                        if k in col and col[k] < len(cr):
                            v = cr[col[k]]
                            if v and v != 'Không' and course_pat.match(v): return v
                        return ""

                    if cid and name:
                        found[cid] = {
                            'id': cid, 'name': name, 'credits': credits,
                            'is_elective': ('elective' in col and col['elective'] < len(cr)
                                            and 'x' in cr[col['elective']].lower()),
                            'prerequisite': rel('prereq'), 'co_requisite': rel('coreq'),
                            'support_course': rel('support'),
                            'department': self.get_department(cid),
                            'category':   self.get_category(cid),
                        }

        self.data['courses'] = found
        print(f"   ✓ {len(found)} môn học")
        for cid, c in list(found.items())[:3]:
            print(f"      - {cid}: {c['name']} ({c['credits']} TC)")

    def get_department(self, cid: str) -> str:
        return {'POLI':'Khoa Giáo dục Chính trị','PSYC':'Khoa Tâm lý học',
                'PHYL':'Khoa Giáo dục Thể chất', 'MILI':'Khoa Giáo dục Quốc phòng',
                'EDUC':'Khoa Khoa học Giáo dục',  'COMP':'Khoa Công nghệ thông tin',
                'DOMS':'Trung tâm ngoại khóa'}.get(cid[:4], 'Khác')

    def get_category(self, cid: str) -> str:
        if cid[:4] in {'POLI','PSYC','PHYL','MILI','EDUC','DOMS'}: return 'Nền tảng'
        if cid in {'COMP1809','COMP1410','COMP1811'}:               return 'Thực hành'
        if cid in {'COMP1083','COMP1813','COMP1830'}:               return 'Tốt nghiệp'
        if cid.startswith('COMP18') or cid.startswith('COMP15'):    return 'Chuyên môn chung'
        if any(cid.startswith(p) for p in ('COMP10','COMP13','COMP14')): return 'Chuyên môn ngành'
        return 'Nghiệp vụ'

    # ── 4. Semesters ──────────────────────────────────────────────────────────

    def extract_semester_info(self, pages):
        print("4. Trích xuất thông tin học kỳ...")
        sems = {}
        for page in pages:
            text = page.extract_text() or ""
            for m in re.finditer(r'Học\s+k[ìỳy]\s+(\d+)\s*\(Tổng\s+cộng:\s*(\d+)\s*TC',
                                  text, re.IGNORECASE):
                sn, tc = int(m.group(1)), int(m.group(2))
                start  = m.start()
                ep     = text.find('Học k', start + 10)
                seg    = text[start: ep if ep != -1 else start + 2500]
                courses = [cid for cid in self.data['courses']
                           if re.search(r'\b' + re.escape(cid) + r'\b', seg)]
                sems[f'HK{sn}'] = {'number': sn, 'name': f'Học kỳ {sn}',
                                    'total_credits': tc, 'courses': courses,
                                    'year': (sn + 1) // 2}
        self.data['semesters'] = sems
        print(f"   ✓ {len(sems)} học kỳ")

    # ── 5. Prerequisites ──────────────────────────────────────────────────────

    def extract_prerequisites(self):
        print("5. Trích xuất quan hệ tiên quyết...")
        prereqs = []
        for cid, info in self.data['courses'].items():
            for field, rtype in [('prerequisite','TIEN_QUYET'),
                                  ('co_requisite', 'HOC_TRUOC'),
                                  ('support_course','HO_TRO')]:
                val = info.get(field, '').strip()
                if val and val != 'Không' and val in self.data['courses']:
                    prereqs.append({'course': cid, 'prerequisite': val,
                                    'type': rtype, 'source': 'TABLE'})
        if len(prereqs) < 10:
            print("   ℹ️  Bổ sung bằng suy luận...")
            prereqs.extend(self._infer())
        self.data['prerequisites'] = self._dedup(prereqs)
        print(f"   ✓ {len(self.data['prerequisites'])} quan hệ")

    def _infer(self):
        rules = [
            ('lập trình.*nâng cao',          'lập trình.*cơ bản',  'TIEN_QUYET'),
            ('lập trình.*oop|hướng đối tượng','lập trình.*cơ bản', 'TIEN_QUYET'),
            ('cấu trúc dữ liệu',             'lập trình.*cơ bản',  'TIEN_QUYET'),
            ('lập trình.*windows',           'lập trình.*oop',      'TIEN_QUYET'),
            ('cơ sở dữ liệu.*nâng cao',      'cơ sở dữ liệu',      'TIEN_QUYET'),
            ('các hệ.*csdl',                 'cơ sở dữ liệu',      'TIEN_QUYET'),
            ('cisco',                        'mạng máy tính',       'TIEN_QUYET'),
            ('quản trị.*linux',              'mạng máy tính',       'TIEN_QUYET'),
            ('thị giác máy tính',            'xử lý ảnh',           'TIEN_QUYET'),
            ('học máy.*nâng cao',            'học máy',             'TIEN_QUYET'),
            ('kinh tế chính trị',            'triết học',           'HOC_TRUOC'),
            ('chủ nghĩa xã hội khoa học',    'triết học',           'HOC_TRUOC'),
        ]
        result = []
        for adv_pat, base_pat, rtype in rules:
            for aid, ai in self.data['courses'].items():
                if re.search(adv_pat, ai.get('name',''), re.IGNORECASE):
                    for bid, bi in self.data['courses'].items():
                        if bid != aid and re.search(base_pat, bi.get('name',''), re.IGNORECASE):
                            result.append({'course': aid, 'prerequisite': bid,
                                           'type': rtype, 'source': 'INFERENCE'})
                            break
        return result

    def _dedup(self, lst):
        seen, pri = {}, {'TABLE': 3, 'INFERENCE': 1}
        for item in lst:
            key = (item['course'], item['prerequisite'], item['type'])
            src = item.get('source', 'UNKNOWN')
            if key not in seen or pri.get(src,0) > pri.get(seen[key].get('source',''),0):
                seen[key] = item
        return list(seen.values())

    # ── 6. Other info ─────────────────────────────────────────────────────────

    def extract_other_info(self, pages):
        print("6. Trích xuất thông tin bổ sung...")
        full = " ".join((p.extract_text() or "").lower() for p in pages)

        if self.gpt and self.gpt.enabled:
            gpt_jobs = self.gpt.enrich_job_positions(full[:4000])
            if gpt_jobs:
                self.data['job_positions'] = gpt_jobs
                print(f"   ✓ Vị trí việc làm (GPT): {len(gpt_jobs)}")

        if not self.data['job_positions']:
            positions = [
                ('lập trình viên','Phát triển phần mềm'),
                ('phân tích viên','Phân tích thiết kế'),
                ('thiết kế chương trình','Phân tích thiết kế'),
                ('quản trị cơ sở dữ liệu','Quản trị hệ thống'),
                ('nghiên cứu viên','Nghiên cứu phát triển'),
                ('kiểm thử','Kiểm thử chất lượng'),
                ('quản trị hệ thống','Quản trị hệ thống'),
                ('quản trị mạng','Quản trị hệ thống'),
                ('thiết kế hệ thống mạng','Phân tích thiết kế'),
            ]
            self.data['job_positions'] = [
                {'name': n.title(), 'category': c, 'description': f'Vị trí {n}'}
                for n, c in positions if n in full
            ]
            print(f"   ✓ Vị trí việc làm (regex): {len(self.data['job_positions'])}")

        self.data['teaching_methods'] = {
            'methods':    [m.title() for m in
                           ['thuyết giảng','đàm thoại','thảo luận',
                            'giải quyết vấn đề','đóng vai','dự án'] if m in full],
            'techniques': [t.title() for t in
                           ['phòng tranh','khăn trải bàn','công đoạn','bể cá'] if t in full],
        }
        self.data['evaluation_methods'] = {
            'formative_assessment':  ['Đánh giá quá trình'] if 'đánh giá quá trình' in full else [],
            'summative_assessment':  ['Đánh giá tổng kết']  if 'đánh giá tổng kết'  in full else [],
        }

    # ── 7. Credit distribution ────────────────────────────────────────────────

    def extract_credit_distribution(self, pages):
        print("7. Trích xuất phân bổ tín chỉ...")
        dist = {}
        for page in pages[4:7]:
            text = page.extract_text() or ""
            if 'phân bổ' not in text.lower() or 'hợp phần' not in text.lower():
                continue
            for table in (page.extract_tables() or []):
                if not table or len(table) < 2: continue
                for row in table:
                    if not row or len(row) < 2: continue
                    rt = ' '.join(str(c) for c in row if c).lower()
                    cat = None
                    if 'nền tảng' in rt:                      cat = 'Nền tảng'
                    elif 'nghiệp vụ' in rt:                   cat = 'Nghiệp vụ'
                    elif 'thực hành' in rt and 'tập' in rt:   cat = 'Thực hành'
                    elif 'tốt nghiệp' in rt:                  cat = 'Tốt nghiệp'
                    if cat:
                        nums = [int(n) for c in row if c
                                for n in re.findall(r'\b(\d{1,3})\b', str(c))
                                if 1 <= int(n) <= 200]
                        if len(nums) >= 2:
                            dist[cat] = {'credits': nums[0], 'percentage': float(nums[1])}
        self.data['credit_distribution'] = dist
        print(f"   ✓ {len(dist)} loại học phần")

    # ── run ───────────────────────────────────────────────────────────────────

    def run(self):
        print("\n=== BẮT ĐẦU TRÍCH XUẤT ===")
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                pages = list(pdf.pages)
                self.extract_program_info(pages)
                self.extract_learning_outcomes(pages)
                self.extract_courses_from_tables(pages)
                self.extract_semester_info(pages)
                self.extract_prerequisites()
                self.extract_other_info(pages)
                self.extract_credit_distribution(pages)
            print("=== HOÀN THÀNH TRÍCH XUẤT ===\n")
            return self.data
        except Exception as e:
            print(f"❌ Lỗi: {e}")
            traceback.print_exc()
            raise

    def save_to_json(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        print(f"✓ JSON: {path}")

    def print_summary(self):
        d = self.data
        print("\n=== TÓM TẮT ===")
        for label, val in [
            ("Thông tin CTĐT",  len(d['program_info'])),
            ("PLO",             len(d['learning_outcomes'])),
            ("PI",              len(d['program_indicators'])),
            ("Môn học",         len(d['courses'])),
            ("Học kỳ",          len(d['semesters'])),
            ("Tiên quyết",      len(d['prerequisites'])),
            ("Vị trí việc làm", len(d['job_positions'])),
        ]:
            print(f"  ✓ {label}: {val}")