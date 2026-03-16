"""
import_data.py
==============

Chạy: python import_data.py
"""

import os
from dotenv import load_dotenv
load_dotenv()

from database import Neo4jImporter

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  1. THÔNG TIN CHƯƠNG TRÌNH                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

PROGRAM_INFO = {
    "program_code":   "7480201",
    "program_name":   "Công nghệ thông tin",
    "degree_level":   "Đại học",
    "training_form":  "Chính quy",
    "total_credits":  124,
    "duration_years": 4,
    "year":           "2024",
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  2. CHUẨN ĐẦU RA (PLO) & CHỈ SỐ THỰC HIỆN (PI)                            ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

LEARNING_OUTCOMES = [
    # PHẨM CHẤT
    {"code": "PLO1", "number": 1, "type": "Phẩm chất",
     "description": "Thể hiện được trách nhiệm công dân và trách nhiệm với nghề nghiệp"},
    {"code": "PLO2", "number": 2, "type": "Phẩm chất",
     "description": "Thể hiện được tính nhân văn và quan tâm đến các vấn đề về phát triển bền vững"},
    # NĂNG LỰC CHUNG
    {"code": "PLO3", "number": 3, "type": "Năng lực chung",
     "description": "Giao tiếp và hợp tác hiệu quả"},
    {"code": "PLO4", "number": 4, "type": "Năng lực chung",
     "description": "Giải quyết vấn đề hiệu quả và sáng tạo"},
    # NĂNG LỰC CHUYÊN MÔN
    {"code": "PLO5", "number": 5, "type": "Năng lực chuyên môn",
     "description": "Giải quyết các vấn đề cơ bản trong công nghệ thông tin bằng cách phân tích yêu cầu, vận dụng kiến thức và kỹ năng chuyên ngành, sử dụng lý thuyết và công cụ cơ bản"},
    {"code": "PLO6", "number": 6, "type": "Năng lực chuyên môn",
     "description": "Giải quyết các vấn đề thực tiễn trong công nghệ thông tin bằng cách đánh giá và áp dụng giải pháp công nghệ phù hợp"},
    # NĂNG LỰC NGHỀ NGHIỆP
    {"code": "PLO7", "number": 7, "type": "Năng lực nghề nghiệp",
     "description": "Thực hiện được ý tưởng khởi nghiệp"},
    {"code": "PLO8", "number": 8, "type": "Năng lực nghề nghiệp",
     "description": "Vận dụng kiến thức về nghề nghiệp công nghệ thông tin để định hướng và phát triển sự nghiệp cá nhân trong lĩnh vực này"},
    {"code": "PLO9", "number": 9, "type": "Năng lực nghề nghiệp",
     "description": "Thực hiện các hoạt động nghề nghiệp trong công nghệ thông tin bao gồm cài đặt, vận hành, nâng cấp, quản trị và quản lý hệ thống CNTT đáp ứng các tiêu chuẩn kỹ thuật và chuyên môn trong ngành"},
    {"code": "PLO10", "number": 10, "type": "Năng lực nghề nghiệp",
     "description": "Thực hiện được hoạt động nghiên cứu khoa học"},
]

PROGRAM_INDICATORS = [
    # PLO1
    {"code": "1.1", "full_code": "PI 1.1", "plo_code": "PLO1",
     "description": "Tuân thủ, chấp hành đường lối, chủ trương của Đảng, chính sách, pháp luật của Nhà nước"},
    {"code": "1.2", "full_code": "PI 1.2", "plo_code": "PLO1",
     "description": "Thể hiện trách nhiệm với bản thân và xã hội"},
    {"code": "1.3", "full_code": "PI 1.3", "plo_code": "PLO1",
     "description": "Thể hiện trách nhiệm của người công dân toàn cầu"},
    {"code": "1.4", "full_code": "PI 1.4", "plo_code": "PLO1",
     "description": "Tuân thủ các quy chuẩn nghề nghiệp"},
    # PLO2
    {"code": "2.1", "full_code": "PI 2.1", "plo_code": "PLO2",
     "description": "Tôn trọng, quan tâm, chia sẻ và giúp đỡ mọi người"},
    {"code": "2.2", "full_code": "PI 2.2", "plo_code": "PLO2",
     "description": "Thể hiện trách nhiệm bản thân với các vấn đề về phát triển bền vững"},
    # PLO3
    {"code": "3.1", "full_code": "PI 3.1", "plo_code": "PLO3",
     "description": "Sử dụng hiệu quả tiếng Việt để truyền đạt vấn đề và giải pháp tới người khác trong học tập và nghề nghiệp"},
    {"code": "3.2", "full_code": "PI 3.2", "plo_code": "PLO3",
     "description": "Sử dụng được một ngoại ngữ đạt trình độ bậc 3 theo Khung Năng lực ngoại ngữ 6 bậc dùng cho Việt Nam"},
    {"code": "3.3", "full_code": "PI 3.3", "plo_code": "PLO3",
     "description": "Tham gia, tổ chức và đánh giá được hoạt động nhóm trong các điều kiện làm việc khác nhau"},
    {"code": "3.4", "full_code": "PI 3.4", "plo_code": "PLO3",
     "description": "Giao tiếp và hợp tác đạt kết quả dựa trên sự tôn trọng các khác biệt của cá nhân, nhóm"},
    {"code": "3.5", "full_code": "PI 3.5", "plo_code": "PLO3",
     "description": "Ứng dụng công nghệ thông tin, khai thác và sử dụng thiết bị công nghệ hiệu quả trong giao tiếp và hợp tác"},
    # PLO4
    {"code": "4.1", "full_code": "PI 4.1", "plo_code": "PLO4",
     "description": "Giải quyết được các nhiệm vụ một cách độc lập và bảo vệ được quan điểm cá nhân"},
    {"code": "4.2", "full_code": "PI 4.2", "plo_code": "PLO4",
     "description": "Sử dụng các nguồn lực một cách hiệu quả và sáng tạo trong giải quyết vấn đề"},
    {"code": "4.3", "full_code": "PI 4.3", "plo_code": "PLO4",
     "description": "Thích ứng với những thay đổi để giải quyết vấn đề đạt kết quả"},
    # PLO5
    {"code": "5.1", "full_code": "PI 5.1", "plo_code": "PLO5",
     "description": "Vận dụng được kiến thức, kỹ năng cơ sở toán học để giải quyết các vấn đề thuộc lĩnh vực công nghệ thông tin"},
    {"code": "5.2", "full_code": "PI 5.2", "plo_code": "PLO5",
     "description": "Vận dụng được kiến thức, kĩ năng cơ sở ngành để giải quyết các vấn đề thuộc lĩnh vực công nghệ thông tin"},
    {"code": "5.3", "full_code": "PI 5.3", "plo_code": "PLO5",
     "description": "Vận dụng được kiến thức, kĩ năng lập trình để phát triển ứng dụng trên các nền tảng máy tính"},
    # PLO6
    {"code": "6.1", "full_code": "PI 6.1", "plo_code": "PLO6",
     "description": "Vận dụng được kiến thức, kĩ năng chuyên ngành để phát triển các ứng dụng thực tiễn thuộc lĩnh vực công nghệ thông tin"},
    {"code": "6.2", "full_code": "PI 6.2", "plo_code": "PLO6",
     "description": "Vận dụng được các giải pháp, mô hình và ứng dụng công nghệ mới trong lĩnh vực công nghệ thông tin để đáp ứng nhu cầu thực tiễn"},
    # PLO7
    {"code": "7.1", "full_code": "PI 7.1", "plo_code": "PLO7",
     "description": "Xác định được định hướng khởi nghiệp cho bản thân"},
    {"code": "7.2", "full_code": "PI 7.2", "plo_code": "PLO7",
     "description": "Dẫn dắt được người khác khởi nghiệp"},
    # PLO8
    {"code": "8.1", "full_code": "PI 8.1", "plo_code": "PLO8",
     "description": "Vận dụng hiểu biết về đặc trưng nghề nghiệp cùng các tố chất, năng lực cần thiết để lập kế hoạch phát triển bản thân trong lĩnh vực công nghệ thông tin"},
    {"code": "8.2", "full_code": "PI 8.2", "plo_code": "PLO8",
     "description": "Vận dụng kiến thức về ảnh hưởng của bối cảnh toàn cầu, khu vực, quốc gia và địa phương để thích nghi và đóng góp hiệu quả trong công việc công nghệ thông tin"},
    {"code": "8.3", "full_code": "PI 8.3", "plo_code": "PLO8",
     "description": "Vận dụng nhận thức về nhu cầu xã hội và xu hướng phát triển của công nghệ thông tin để xác định cơ hội và triển khai giải pháp đáp ứng yêu cầu nghề nghiệp"},
    # PLO9
    {"code": "9.1", "full_code": "PI 9.1", "plo_code": "PLO9",
     "description": "Thực hiện hiệu quả việc cài đặt, vận hành, nâng cấp, quản trị và quản lý hệ thống CNTT, giải quyết các vấn đề thực tế theo tiêu chuẩn kỹ thuật và chuyên môn"},
    {"code": "9.2", "full_code": "PI 9.2", "plo_code": "PLO9",
     "description": "Thích nghi và làm việc hiệu quả trong các điều kiện và môi trường khác nhau của ngành công nghệ thông tin, tuân thủ các tiêu chuẩn kỹ thuật và chuyên môn trong ngành"},
    # PLO10
    {"code": "10.1", "full_code": "PI 10.1", "plo_code": "PLO10",
     "description": "Lập được kế hoạch nghiên cứu khoa học trong lĩnh vực công nghệ thông tin"},
    {"code": "10.2", "full_code": "PI 10.2", "plo_code": "PLO10",
     "description": "Triển khai thực hiện nghiên cứu khoa học trong lĩnh vực công nghệ thông tin"},
]

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  3. MÔN HỌC                                                                 ║
# ║  Nguồn: Mục 2 (Khung CTĐT) + Mục 3 (Kế hoạch dạy học)                     ║
# ║  category: đúng theo phân loại trong tài liệu                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

COURSES = {
    # ── 1.1a Học phần chung - bắt buộc ───────────────────────────────────────
    "POLI2001": {"name": "Triết học Mác – Lênin",                       "credits": 3,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDCT"},
    "POLI2002": {"name": "Kinh tế chính trị Mác – Lênin",               "credits": 2,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDCT"},
    "POLI2003": {"name": "Chủ nghĩa xã hội khoa học",                   "credits": 2,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDCT"},
    "POLI2004": {"name": "Lịch sử Đảng Cộng sản Việt Nam",              "credits": 2,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDCT"},
    "POLI2005": {"name": "Tư tưởng Hồ Chí Minh",                        "credits": 2,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDCT"},
    "POLI1903": {"name": "Pháp luật đại cương",                          "credits": 2,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDCT"},
    "PSYC1001": {"name": "Tâm lý học đại cương",                         "credits": 2,  "is_elective": False, "category": "Học phần chung",          "department": "K.TLH"},
    "PHYL2401": {"name": "Giáo dục thể chất 1",                          "credits": 1,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDTC"},
    "PHYL2":    {"name": "Giáo dục thể chất 2",                          "credits": 1,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDTC"},
    "PHYL3":    {"name": "Giáo dục thể chất 3",                          "credits": 1,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDTC"},
    "MILI2701": {"name": "Đường lối quốc phòng và an ninh của Đảng Cộng sản Việt Nam", "credits": 3, "is_elective": False, "category": "Học phần chung", "department": "K.GDQP"},
    "MILI2702": {"name": "Công tác quốc phòng và an ninh",               "credits": 2,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDQP"},
    "MILI2703": {"name": "Quân sự chung",                                 "credits": 2,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDQP"},
    "MILI2704": {"name": "Kỹ thuật chiến đấu bộ binh và chiến thuật",    "credits": 4,  "is_elective": False, "category": "Học phần chung",          "department": "K.GDQP"},
    # ── 1.1b Học phần chung - tự chọn bắt buộc (chọn 4 TC) ──────────────────
    "EDUC2801": {"name": "Phương pháp học tập hiệu quả",                 "credits": 2,  "is_elective": True,  "category": "Học phần chung",          "department": "K.KHGD"},
    "PSYC1493": {"name": "Kỹ năng thích ứng và giải quyết vấn đề",      "credits": 2,  "is_elective": True,  "category": "Học phần chung",          "department": "K.TLH"},
    "PSYC2801": {"name": "Kỹ năng làm việc nhóm và tư duy sáng tạo",    "credits": 2,  "is_elective": True,  "category": "Học phần chung",          "department": "K.TLH"},
    "DOMS0":    {"name": "Giáo dục đời sống",                            "credits": 2,  "is_elective": True,  "category": "Học phần chung",          "department": "TNC"},
    # ── 1.2a Học phần chuyên môn chung cho nhóm ngành - bắt buộc ─────────────
    "COMP1501": {"name": "Xác suất thống kê và ứng dụng",                "credits": 3,  "is_elective": False, "category": "Chuyên môn chung nhóm ngành", "department": "K.CNTT"},
    "COMP1802": {"name": "Thiết kế Web",                                  "credits": 2,  "is_elective": False, "category": "Chuyên môn chung nhóm ngành", "department": "K.CNTT"},
    "COMP1801": {"name": "Toán rời rạc và ứng dụng",                     "credits": 2,  "is_elective": False, "category": "Chuyên môn chung nhóm ngành", "department": "K.CNTT"},
    "COMP1800": {"name": "Cơ sở toán trong CNTT",                        "credits": 4,  "is_elective": False, "category": "Chuyên môn chung nhóm ngành", "department": "K.CNTT"},
    # ── 1.3a Học phần chuyên môn chung lĩnh vực - bắt buộc ───────────────────
    "COMP1010": {"name": "Lập trình cơ bản",                             "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1013": {"name": "Lập trình nâng cao",                           "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1017": {"name": "Lập trình hướng đối tượng",                    "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1502": {"name": "Quy hoạch tuyến tính và ứng dụng",             "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1011": {"name": "Kiến trúc máy tính và hợp ngữ",                "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1016": {"name": "Cấu trúc dữ liệu",                             "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1018": {"name": "Cơ sở dữ liệu",                                "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1401": {"name": "Phân tích và thiết kế giải thuật",             "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1019": {"name": "Lập trình trên Windows",                       "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1015": {"name": "Nhập môn mạng máy tính",                       "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "PSYC2804": {"name": "Phương pháp nghiên cứu khoa học",              "credits": 2,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.TLH"},
    "COMP1829": {"name": "Quản lý công việc hiệu quả theo Agile",        "credits": 2,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1701": {"name": "Lý thuyết đồ thị và ứng dụng",                 "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1332": {"name": "Hệ điều hành",                                  "credits": 3,  "is_elective": False, "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    # ── 1.3b Học phần chuyên môn chung lĩnh vực - tự chọn (chọn 6 TC) ────────
    "COMP1043": {"name": "Hệ thống mã nguồn mở",                         "credits": 3,  "is_elective": True,  "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1308": {"name": "Phát triển ứng dụng trò chơi",                 "credits": 3,  "is_elective": True,  "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1047": {"name": "Đồ hoạ máy tính",                              "credits": 3,  "is_elective": True,  "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1712": {"name": "Học máy",                                       "credits": 3,  "is_elective": True,  "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1050": {"name": "Xử lý ảnh số",                                 "credits": 3,  "is_elective": True,  "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1709": {"name": "Hệ thống nhúng và ứng dụng",                   "credits": 3,  "is_elective": True,  "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1304": {"name": "Phát triển ứng dụng trên thiết bị di động",    "credits": 3,  "is_elective": True,  "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1024": {"name": "Các hệ cơ sở dữ liệu",                         "credits": 3,  "is_elective": True,  "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    "COMP1305": {"name": "Quản lý dự án Công nghệ Thông tin",            "credits": 3,  "is_elective": True,  "category": "Chuyên môn chung lĩnh vực", "department": "K.CNTT"},
    # ── 2.1 Học phần nghiệp vụ chung cho khối ngành ──────────────────────────
    "PSYC2803": {"name": "Khởi nghiệp",                                   "credits": 2,  "is_elective": False, "category": "Nghiệp vụ chung",          "department": "K.TLH"},
    # ── 2.2a Học phần nghiệp vụ - bắt buộc ───────────────────────────────────
    "COMP1044": {"name": "Nhập môn công nghệ phần mềm",                  "credits": 3,  "is_elective": False, "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1314": {"name": "Trí tuệ nhân tạo",                             "credits": 3,  "is_elective": False, "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1803": {"name": "Lập trình PHP",                                 "credits": 3,  "is_elective": False, "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1060": {"name": "Phân tích thiết kế hướng đối tượng",           "credits": 3,  "is_elective": False, "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    # ── 2.2b Học phần nghiệp vụ - tự chọn (chọn 18 TC) ──────────────────────
    "COMP1041": {"name": "Cơ sở dữ liệu nâng cao",                       "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1071": {"name": "Nghi thức giao tiếp mạng (CISCO 1)",           "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1307": {"name": "Kiểm thử phần mềm cơ bản",                     "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1703": {"name": "Phát triển ứng dụng trên thiết bị di động nâng cao", "credits": 3, "is_elective": True, "category": "Nghiệp vụ ngành",      "department": "K.CNTT"},
    "COMP1032": {"name": "Phân tích và thiết kế hệ thống thông tin",     "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1306": {"name": "Xây dựng dự án Công nghệ thông tin",           "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1326": {"name": "Lắp ráp, cài đặt và bảo trì máy tính",        "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1076": {"name": "Quản trị mạng với Linux",                       "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1804": {"name": "Lập trình Python",                              "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1315": {"name": "Khai thác dữ liệu và ứng dụng",                "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1714": {"name": "Khai thác dữ liệu văn bản",                    "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1309": {"name": "Kiểm thử phần mềm nâng cao",                   "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1318": {"name": "Các phương pháp học thống kê",                  "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1715": {"name": "Xử lý ngôn ngữ tự nhiên",                      "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1704": {"name": "Nhập môn DevOps",                               "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1046": {"name": "Các hệ cơ sở tri thức",                         "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1310": {"name": "Hệ tư vấn thông tin",                           "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1031": {"name": "Công nghệ Web",                                  "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1064": {"name": "Công nghệ NET",                                  "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1085": {"name": "Hệ thống quản trị doanh nghiệp",               "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1311": {"name": "Bảo mật cơ sở dữ liệu",                        "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1042": {"name": "Công nghệ JAVA",                                 "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1065": {"name": "Chuyên đề Oracle",                              "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1504": {"name": "Thị giác máy tính và ứng dụng",                "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1325": {"name": "Máy học nâng cao",                              "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1084": {"name": "Thương mại điện tử",                            "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1069": {"name": "Công nghệ phần mềm nâng cao",                  "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    "COMP1313": {"name": "Điện toán đám mây",                             "credits": 3,  "is_elective": True,  "category": "Nghiệp vụ ngành",          "department": "K.CNTT"},
    # ── 3. Học phần thực hành, thực tập nghề nghiệp ──────────────────────────
    "COMP1809": {"name": "Thực hành nghề nghiệp",                        "credits": 3,  "is_elective": False, "category": "Thực hành nghề nghiệp",    "department": "K.CNTT"},
    "COMP1410": {"name": "Thực tập nghề nghiệp 1",                       "credits": 2,  "is_elective": False, "category": "Thực hành nghề nghiệp",    "department": "K.CNTT"},
    "COMP1811": {"name": "Thực tập nghề nghiệp 2",                       "credits": 5,  "is_elective": False, "category": "Thực hành nghề nghiệp",    "department": "K.CNTT"},
    # ── 4. Học phần tốt nghiệp ────────────────────────────────────────────────
    "COMP1083": {"name": "Khóa luận tốt nghiệp",                         "credits": 6,  "is_elective": True,  "category": "Tốt nghiệp",               "department": "K.CNTT"},
    "COMP1813": {"name": "Hồ sơ tốt nghiệp",                             "credits": 3,  "is_elective": True,  "category": "Tốt nghiệp",               "department": "K.CNTT"},
    "COMP1830": {"name": "Sản phẩm nghiên cứu",                          "credits": 3,  "is_elective": True,  "category": "Tốt nghiệp",               "department": "K.CNTT"},
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  4. ĐIỀU KIỆN TIÊN QUYẾT                                                    ║
# ║  Nguồn: Cột "HP tiên quyết" và "HP học trước" trong bảng Khung CTĐT        ║
# ║  type = "prerequisite" (HP tiên quyết) | "precede" (HP học trước)          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

PREREQUISITES = [
    # HP học trước (HP học trước — phải hoàn thành trước)
    {"course": "POLI2002", "prerequisite": "POLI2001", "type": "precede"},
    {"course": "POLI2003", "prerequisite": "POLI2001", "type": "precede"},
    {"course": "POLI2004", "prerequisite": "POLI2005", "type": "precede"},
    {"course": "POLI2005", "prerequisite": "POLI2003", "type": "precede"},
    {"course": "MILI2704", "prerequisite": "MILI2703", "type": "precede"},
    {"course": "COMP1013", "prerequisite": "COMP1010", "type": "precede"},
    {"course": "COMP1017", "prerequisite": "COMP1010", "type": "precede"},
    {"course": "COMP1502", "prerequisite": "COMP1800", "type": "precede"},
    {"course": "COMP1016", "prerequisite": "COMP1010", "type": "precede"},
    {"course": "COMP1018", "prerequisite": "COMP1010", "type": "precede"},
    {"course": "COMP1401", "prerequisite": "COMP1010", "type": "precede"},
    {"course": "COMP1019", "prerequisite": "COMP1017", "type": "precede"},
    {"course": "COMP1308", "prerequisite": "COMP1017", "type": "precede"},
    {"course": "COMP1050", "prerequisite": "COMP1019", "type": "precede"},
    {"course": "COMP1709", "prerequisite": "COMP1017", "type": "precede"},
    {"course": "COMP1041", "prerequisite": "COMP1018", "type": "precede"},
    {"course": "COMP1071", "prerequisite": "COMP1015", "type": "precede"},
    {"course": "COMP1703", "prerequisite": "COMP1304", "type": "precede"},
    {"course": "COMP1032", "prerequisite": "COMP1018", "type": "precede"},
    {"course": "COMP1306", "prerequisite": "COMP1044", "type": "precede"},
    {"course": "COMP1076", "prerequisite": "COMP1015", "type": "precede"},
    {"course": "COMP1315", "prerequisite": "COMP1018", "type": "precede"},
    {"course": "COMP1714", "prerequisite": "COMP1314", "type": "precede"},
    {"course": "COMP1309", "prerequisite": "COMP1044", "type": "precede"},
    {"course": "COMP1318", "prerequisite": "COMP1501", "type": "precede"},
    {"course": "COMP1704", "prerequisite": "COMP1044", "type": "precede"},
    {"course": "COMP1046", "prerequisite": "COMP1701", "type": "precede"},
    {"course": "COMP1310", "prerequisite": "COMP1018", "type": "precede"},
    {"course": "COMP1085", "prerequisite": "COMP1018", "type": "precede"},
    {"course": "COMP1311", "prerequisite": "COMP1018", "type": "precede"},
    {"course": "COMP1065", "prerequisite": "COMP1018", "type": "precede"},
    {"course": "COMP1504", "prerequisite": "COMP1050", "type": "precede"},
    {"course": "COMP1325", "prerequisite": "COMP1712", "type": "precede"},
    {"course": "COMP1069", "prerequisite": "COMP1044", "type": "precede"},
    {"course": "COMP1313", "prerequisite": "COMP1015", "type": "precede"},
    {"course": "COMP1044", "prerequisite": "COMP1017", "type": "precede"},
    {"course": "COMP1314", "prerequisite": "COMP1701", "type": "precede"},
    {"course": "COMP1803", "prerequisite": "COMP1013", "type": "precede"},
    {"course": "COMP1060", "prerequisite": "COMP1017", "type": "precede"},
    {"course": "COMP1811", "prerequisite": "COMP1410", "type": "precede"},
]

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  5. HỌC KỲ                                                                  ║
# ║  Nguồn: Mục 3 "Kế hoạch dạy học" — đúng theo bảng phân bổ học kỳ          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

SEMESTERS = {
    "HK1": {
        "name": "Học kỳ 1", "number": 1, "year": 1, "total_credits": 18,
        "courses": [
            "POLI2001", "POLI1903", "PSYC1001", "PHYL2401",
            "MILI2701", "COMP1802", "COMP1801", "COMP1800", "COMP1010",
        ],
    },
    "HK2": {
        "name": "Học kỳ 2", "number": 2, "year": 1, "total_credits": 16,
        "courses": [
            "POLI2002", "POLI2003", "PHYL2", "MILI2702",
            "EDUC2801", "PSYC1493", "PSYC2801", "DOMS0",
            "COMP1013", "COMP1017", "PSYC2804",
        ],
    },
    "HK3": {
        "name": "Học kỳ 3", "number": 3, "year": 2, "total_credits": 17,
        "courses": [
            "POLI2005", "PHYL3", "MILI2703",
            "COMP1501", "COMP1016", "COMP1018", "COMP1019", "COMP1701",
        ],
    },
    "HK4": {
        "name": "Học kỳ 4", "number": 4, "year": 2, "total_credits": 16,
        "courses": [
            "POLI2004", "MILI2704",
            "COMP1011", "COMP1401", "COMP1015", "COMP1829", "COMP1332",
        ],
    },
    "HK5": {
        "name": "Học kỳ 5", "number": 5, "year": 3, "total_credits": 15,
        "courses": [
            # Bắt buộc
            "COMP1044", "COMP1314", "COMP1060",
            # Tự chọn (các môn được xếp ở HK5 theo kế hoạch dạy học)
            "COMP1043", "COMP1308", "COMP1712", "COMP1050",
            "COMP1709", "COMP1304", "COMP1024", "COMP1305",
            "COMP1041", "COMP1071", "COMP1307", "COMP1032", "COMP1804",
        ],
    },
    "HK6": {
        "name": "Học kỳ 6", "number": 6, "year": 3, "total_credits": 15,
        "courses": [
            # Bắt buộc
            "COMP1502", "COMP1803",
            # Tự chọn
            "COMP1047", "COMP1306", "COMP1326", "COMP1076",
            "COMP1315", "COMP1318", "COMP1715", "COMP1704",
            "COMP1046", "COMP1310", "COMP1031", "COMP1064",
            "COMP1085", "COMP1311", "COMP1042", "COMP1065",
        ],
    },
    "HK7": {
        "name": "Học kỳ 7", "number": 7, "year": 4, "total_credits": 16,
        "courses": [
            # Bắt buộc
            "PSYC2803", "COMP1809", "COMP1410",
            # Tự chọn
            "COMP1703", "COMP1714", "COMP1309", "COMP1504",
            "COMP1325", "COMP1084", "COMP1069", "COMP1313",
        ],
    },
    "HK8": {
        "name": "Học kỳ 8", "number": 8, "year": 4, "total_credits": 11,
        "courses": [
            # Bắt buộc
            "COMP1811",
            # Tự chọn (chọn 1 trong 2 hình thức tốt nghiệp)
            "COMP1083", "COMP1813", "COMP1830",
        ],
    },
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  6. VỊ TRÍ VIỆC LÀM                                                         ║
# ║  Nguồn: Mục 1.3 trong PDF — giữ đúng nguyên văn, không thêm                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

JOB_POSITIONS = [
    {"name": "Lập trình viên",                       "category": "Phần mềm",    "description": "Làm việc tại các công ty sản xuất và kiểm thử phần mềm"},
    {"name": "Phân tích viên",                        "category": "Phần mềm",    "description": "Phân tích yêu cầu phần mềm"},
    {"name": "Thiết kế chương trình và dữ liệu",     "category": "Phần mềm",    "description": "Thiết kế kiến trúc chương trình và cơ sở dữ liệu"},
    {"name": "Quản trị cơ sở dữ liệu",               "category": "Dữ liệu",     "description": "Quản trị các hệ cơ sở dữ liệu"},
    {"name": "Nghiên cứu viên",                       "category": "Nghiên cứu",  "description": "Nghiên cứu trong các tổ chức/cơ quan chuyên nghiệp"},
    {"name": "Triển khai giải pháp CNTT",             "category": "Hệ thống",    "description": "Triển khai giải pháp, quản trị công nghệ thông tin cho các cơ quan hay tổ chức"},
    {"name": "Quản trị hệ thống",                     "category": "Hệ thống",    "description": "Quản trị hệ thống CNTT"},
    {"name": "Quản trị mạng",                         "category": "Mạng",        "description": "Quản trị mạng máy tính"},
    {"name": "Thiết kế hệ thống mạng",               "category": "Mạng",        "description": "Thiết kế hệ thống mạng"},
]

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  ENTRY POINT                                                                ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

def main():
    uri      = os.environ.get("NEO4J_URI",      "")
    user     = os.environ.get("NEO4J_USERNAME", "")
    password = os.environ.get("NEO4J_PASSWORD", "")

    if not uri or not user or not password:
        print("❌ Thiếu thông tin Neo4j trong .env")
        print("   Cần: NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD")
        return

    data = {
        "program_info":       PROGRAM_INFO,
        "learning_outcomes":  LEARNING_OUTCOMES,
        "program_indicators": PROGRAM_INDICATORS,
        "courses":            COURSES,
        "prerequisites":      PREREQUISITES,
        "semesters":          SEMESTERS,
        "job_positions":      JOB_POSITIONS,
    }

    print(f"Tổng số môn học: {len(COURSES)}")
    print(f"Tổng số PLO    : {len(LEARNING_OUTCOMES)}")
    print(f"Tổng số PI     : {len(PROGRAM_INDICATORS)}")
    print(f"Tổng số tiên quyết: {len(PREREQUISITES)}")

    importer = Neo4jImporter(uri, user, password)
    try:
        importer.import_curriculum_data(data)
    finally:
        importer.close()


if __name__ == "__main__":
    main()