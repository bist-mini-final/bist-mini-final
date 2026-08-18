#!/usr/bin/env python3
"""
detected_tables DB 저장/로드 검증 스크립트
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.storage.db_manager import DatabaseManager
from backend.spreadsheets.workbook_catalog import WorkbookCatalog
from backend.core.settings import PROCESSED_DATA_DIR, SPREADSHEET_ARTIFACT_DIR

TARGET_FILE = "SPG_Company_KeyStats_v3.xlsm"

def check_db_detected_tables():
    catalog = WorkbookCatalog(PROCESSED_DATA_DIR)
    wb_path = catalog.resolve(TARGET_FILE)
    wb_hash = catalog.sha256(wb_path)
    print(f"\n파일: {TARGET_FILE}")
    print(f"Hash: {wb_hash[:16]}...")

    db = DatabaseManager()
    if not db.is_connected():
        print("❌ DB 연결 실패 — PostgreSQL이 실행 중인지 확인하세요")
        return
    print("✅ DB 연결 성공")

    import psycopg2
    conn = psycopg2.connect(db.database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT sheet_name, sheet_index, row_count, column_count, "
                "COALESCE(jsonb_array_length(detected_tables), 0) as table_count "
                "FROM sheets WHERE file_id = %s ORDER BY sheet_index;",
                (wb_hash,)
            )
            rows = cur.fetchall()
        if not rows:
            print(f"❌ sheets 테이블에 {TARGET_FILE} 레코드 없음 — 아직 인덱싱 안 됨")
            return
        print(f"\n📋 sheets 테이블 ({len(rows)}개 시트):")
        for sheet_name, idx, rc, cc, tc in rows:
            st = "✅" if tc > 0 else "⚠️ "
            print(f"  {st} [{idx}] {sheet_name}: {rc}행 × {cc}열, detected_tables={tc}개")

        with conn.cursor() as cur:
            cur.execute("SELECT sheet_name, detected_tables FROM sheets WHERE file_id = %s ORDER BY sheet_index;", (wb_hash,))
            detail_rows = cur.fetchall()

        all_valid = True
        for sheet_name, detected in detail_rows:
            if not detected:
                continue
            for i, t in enumerate(detected):
                required = {"sheet_name", "table_index", "excel_range", "regions"}
                missing = required - set(t.keys())
                if missing:
                    print(f"  ❌ {sheet_name} table[{i}] 누락 필드: {missing}")
                    all_valid = False
                else:
                    print(f"  ✅ {sheet_name} table[{i}]: {t['excel_range']}, {len(t['regions'])} regions")
                    for r_idx, region in enumerate(t["regions"]):
                        bbox = region.get("bbox_px")
                        if not bbox or len(bbox) != 4:
                            print(f"    ❌ region[{r_idx}] bbox_px 이상: {bbox}")
                            all_valid = False
        if all_valid:
            print("\n✅ DB 저장 구조 정상")
    finally:
        conn.close()

    print("\n📤 get_detected_tables() + ClassifiedTableDTO 변환 테스트:")
    tables = db.get_detected_tables(wb_hash)
    print(f"  반환 테이블 수: {len(tables)}")
    if not tables:
        print("  ⚠️  테이블 없음 — detected_tables가 저장 안 됐거나 형식 오류")
        return

    from backend.modules.spreadsheet_structure import ClassifiedTableDTO
    success, fail = 0, 0
    for i, t in enumerate(tables):
        try:
            dto = ClassifiedTableDTO(**t)
            print(f"  ✅ [{i}] {dto.sheet_name} / {dto.excel_range} ({len(dto.regions)} regions)")
            success += 1
        except Exception as e:
            print(f"  ❌ [{i}] 변환 실패: {e}")
            print(f"     키: {list(t.keys())}")
            fail += 1
    print(f"\n변환: 성공 {success}, 실패 {fail}")

    cache_path = SPREADSHEET_ARTIFACT_DIR / wb_hash[:16] / "serialized_docs.json"
    print(f"\n📂 serialized_docs.json: {cache_path}")
    if cache_path.is_file():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        print(f"  ✅ 캐시 존재: {len(cached.get('items', []))}개 문서, pipeline={cached.get('used_pipeline')}")
    else:
        print("  ⚠️  캐시 없음 — 완전 인덱싱 후 자동 생성됩니다")

if __name__ == "__main__":
    check_db_detected_tables()
