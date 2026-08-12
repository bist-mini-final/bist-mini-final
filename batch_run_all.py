import json
import time
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.answer_cache import AnswerCacheRepository
from backend.chat_completion import ChatCompletionClient
from backend.embedding_artifacts import EmbeddingArtifactStore
from backend.vector_index_store import VectorIndexStore
from backend.config import (
    CACHE_DIR,
    EMBEDDING_ARTIFACT_DIR,
    RUN_DIR,
    SPREADSHEET_ARTIFACT_DIR,
    VECTOR_INDEX_DIR,
    WORKFLOW_DIR,
)
from backend.module_registry import ModuleRegistry
from backend.workflows.store import ResultCache, RunStore, WorkflowStore
from backend.workflows.executor import WorkflowExecutor
from backend.workflows.models import WorkflowExecutionRequest

OUTPUT_DIR = Path('/Users/pileuszu/Repos/bist-mini-final/outputs')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
BATCH_FILE = OUTPUT_DIR / 'batch_results.json'

INPUT_FILE = '/Users/pileuszu/.gemini/antigravity-ide/brain/84de22fd-68d5-4eee-9d6f-bb4d32126cb3/.system_generated/steps/15/output.txt'

with open(INPUT_FILE, 'r', encoding='utf-8') as f:
    content = json.loads(f.read())['markdown']

table_content = re.search(r'<table.*?>(.*?)</table>', content, re.DOTALL).group(1)
rows = re.findall(r'<tr>(.*?)</tr>', table_content, re.DOTALL)

questions = []
for r in rows:
    cols = [c.strip() for c in re.findall(r'<td>(.*?)</td>', r, re.DOTALL)]
    if len(cols) == 5 and cols[0] != "문항 ID":
        questions.append({
            "id": cols[0],
            "scenario": cols[1],
            "question": cols[2],
            "chatgpt": cols[3].replace(r'\$', '$')
        })

def extract_answer(res_run):
    json_node = res_run.nodes.get('custom-node-1786497852818-2')
    if json_node and isinstance(json_node.output, dict):
        ans = json_node.output.get('answer')
        if isinstance(ans, str) and ans.strip():
            return ans, json_node.output.get('api_usage', {})

    reader_node = res_run.nodes.get('custom-node-1786497793017-1')
    if reader_node and isinstance(reader_node.output, dict):
        ans_json = reader_node.output.get('answer_json')
        if isinstance(ans_json, dict) and isinstance(ans_json.get('answer'), str) and ans_json['answer'].strip():
            return ans_json['answer'], ans_json.get('api_usage', {})

    for nid, node in res_run.nodes.items():
        if isinstance(node.output, dict):
            ans = node.output.get('answer')
            if isinstance(ans, str) and ans.strip():
                return ans, node.output.get('api_usage', {})
            ans_json = node.output.get('answer_json')
            if isinstance(ans_json, dict) and isinstance(ans_json.get('answer'), str) and ans_json['answer'].strip():
                return ans_json['answer'], ans_json.get('api_usage', {})
    return '', {}

def get_shared_executor():
    repo = AnswerCacheRepository(None)
    client = ChatCompletionClient()
    embedding_artifact_store = EmbeddingArtifactStore(EMBEDDING_ARTIFACT_DIR)
    vector_index_store = VectorIndexStore(VECTOR_INDEX_DIR)
    registry = ModuleRegistry(
        repo,
        completion_client=client,
        embedding_artifact_store=embedding_artifact_store,
        vector_index_store=vector_index_store,
    )
    workflow_store = WorkflowStore(WORKFLOW_DIR)
    run_store = RunStore(RUN_DIR)
    result_cache = ResultCache(CACHE_DIR)
    workflow = workflow_store.load('workflow')
    executor = WorkflowExecutor(registry, run_store, result_cache)
    return workflow, executor

import gc

def process_question(q, workflow, executor):
    q_id = q['id']
    q_text = q['question']
    indiv_file = OUTPUT_DIR / f"{q_id}.json"

    # 1. Cache Check
    if indiv_file.exists():
        try:
            with open(indiv_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            ans = cached_data.get('pipeline_answer', '')
            if isinstance(ans, str) and ans.strip():
                return q_id, cached_data, cached_data.get('latency_seconds', 0.0), len(ans), True
        except Exception:
            pass

    # 2. Execution if not cached or empty
    t_single = time.time()
    req = WorkflowExecutionRequest(inputs={'custom-node-1786497067905-2': {'query': q_text}}, use_cache=False)
    run = executor.create_run(workflow, req)
    res_run = executor.execute_all(run.id)
    elapsed = time.time() - t_single
    
    ans, usage = extract_answer(res_run)
    item_res = {
        "id": q_id,
        "scenario": q['scenario'],
        "question": q_text,
        "chatgpt_answer": q['chatgpt'],
        "pipeline_answer": ans,
        "api_usage": usage,
        "latency_seconds": round(elapsed, 3)
    }
    
    with open(indiv_file, 'w', encoding='utf-8') as f:
        json.dump(item_res, f, ensure_ascii=False, indent=2)

    # Clean run files & free memory
    (RUN_DIR / f"{run.id}.json").unlink(missing_ok=True)
    (RUN_DIR / f"{run.id}.summary.json").unlink(missing_ok=True)
    gc.collect()
        
    return q_id, item_res, elapsed, len(ans), False

def main():
    batch_results = {}
    t0 = time.time()

    # Clean old run files in RUN_DIR to reclaim disk space
    for old_run in RUN_DIR.glob('run-*'):
        try:
            old_run.unlink()
        except Exception:
            pass

    workflow, executor = get_shared_executor()

    print(f"Starting batch execution for {len(questions)} questions (checking cache first)...", flush=True)
    completed_count = 0
    cached_count = 0
    executed_count = 0

    # Load initial batch_results if exists
    if BATCH_FILE.exists():
        try:
            with open(BATCH_FILE, 'r', encoding='utf-8') as f:
                batch_results = json.load(f)
        except Exception:
            batch_results = {}

    for q in questions:
        q_id, item_res, elapsed, ans_len, is_cached = process_question(q, workflow, executor)
        batch_results[q_id] = item_res
        completed_count += 1
        
        if is_cached:
            cached_count += 1
            print(f"[Cache Hit {completed_count}/{len(questions)}] {q_id}: ans_len={ans_len}", flush=True)
        else:
            executed_count += 1
            print(f"[Executed {completed_count}/{len(questions)}] {q_id}: ans_len={ans_len} ({elapsed:.2f}s)", flush=True)
        
        # Save batch_results incrementally
        with open(BATCH_FILE, 'w', encoding='utf-8') as f:
            json.dump(batch_results, f, ensure_ascii=False, indent=2)

    print("\nBATCH COMPLETED!", flush=True)
    non_empty = [k for k, v in batch_results.items() if v.get('pipeline_answer')]
    print(f"Summary: {len(non_empty)} / {len(batch_results)} non-empty pipeline answers.", flush=True)
    print(f"Cached hits: {cached_count}, Newly executed: {executed_count}, Total time: {time.time()-t0:.2f}s", flush=True)

if __name__ == "__main__":
    main()
