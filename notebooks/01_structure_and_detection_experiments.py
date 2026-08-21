# %% [markdown]
# # [실험 1] Spreadsheet 2D 구조 분석 & 표 영역 검출 실험
# 
# **목적**:
# 다양한 서식과 병합 셀을 포함하는 엑셀 문서에서 표 영역(Table Region), 행/열 헤더 계층, 데이터 영역을
# 정확하게 검출하고 비교 분석합니다.

# %%
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, List, cast

# Set root directory for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.storage.processed_file_selector import ProcessedFileSelectorModule
from modules.structure.docling_table_detector import DoclingTableDetectorModule
from modules.structure.openpyxl_region_detector import OpenpyxlRegionDetectorModule

print(f"Project root initialized: {PROJECT_ROOT}")

# %% [markdown]
# ## 1. 엑셀 파일 로드 및 메타데이터 확인

# %%
source_dir = PROJECT_ROOT / "data" / "source_files"
excel_files = list(source_dir.glob("*.xlsm")) + list(source_dir.glob("*.xlsx"))
print(f"발견된 엑셀 파일 목록 ({len(excel_files)}개):")
for f in excel_files[:5]:
    print(f" - {f.name} ({f.stat().st_size / 1024:.1f} KB)")

target_file = excel_files[0] if excel_files else None

# %% [markdown]
# ## 2. 파일 선택 및 시트 메타데이터 추출 (ProcessedFileSelector)

# %%
selected_file: Optional[Dict[str, Any]] = None
docling_result: Optional[Dict[str, Any]] = None
file_selector = ProcessedFileSelectorModule(processed_dir=source_dir)
if target_file:
    print(f"\n--- 파일 메타데이터 추출: {target_file.name} ---")
    selected_file = file_selector.run({"file_name": target_file.name})
    # 실험용으로 첫 1개 주요 시트로 슬라이싱하여 빠른 실행
    selected_file["sheet_names"] = selected_file.get("sheet_names", [])[:1]
    print(f"선택된 파일: {selected_file.get('file_name')}")
    print(f"워크북 해시: {selected_file.get('workbook_hash')}")
    print(f"대상 시트: {selected_file.get('sheet_names')}")

# %% [markdown]
# ## 3. Docling Table Detector 실험 (도큐먼트 레이아웃 파서)

# %%
if target_file and selected_file:
    print(f"\n--- Docling Table Detector 분석 시작 ---")
    docling_detector = DoclingTableDetectorModule()
    
    start_t = time.perf_counter()
    docling_result = docling_detector.run(
        input_payload=selected_file,
        config={"max_rows": 30, "max_columns": 20},
    )
    elapsed = time.perf_counter() - start_t
    
    tables = docling_result.get("tables", [])
    print(f"Docling 분석 완료! 소요 시간: {elapsed:.3f}초 | 검출된 표(Table) 수: {len(tables)}개")

# %% [markdown]
# ## 4. Openpyxl Region Detector 실험 (서식 & 병합 셀 기반)

# %%
if target_file and docling_result:
    print(f"\n--- Openpyxl Region Detector 분석 시작 ---")
    openpyxl_detector = OpenpyxlRegionDetectorModule()
    
    start_t = time.perf_counter()
    openpyxl_result = openpyxl_detector.run(docling_result)
    elapsed = time.perf_counter() - start_t
    
    tables = openpyxl_result.get("tables", [])
    print(f"Openpyxl 분석 완료! 소요 시간: {elapsed:.3f}초 | 검출된 표(Table) 수: {len(tables)}개")
    for t in tables[:3]:
        print(f"  [시트: {t.get('sheet_name')}] 범위: {t.get('excel_range')} | 영역 수: {len(t.get('regions', []))}개")

# %% [markdown]
# ## 5. 실험 결과 요약

# %%
print("\n" + "=" * 60)
print("실험 1 요약:")
print(" - ProcessedFileSelector: 파일 무결성 및 시트 목록 검출")
print(" - Docling Detector: 시트별 테이블 바운딩 박스 검출")
print(" - Openpyxl Detector: 병합 셀, 계층형 열/행 헤더 트리 및 데이터 영역 정밀 태깅")
print("=" * 60)
