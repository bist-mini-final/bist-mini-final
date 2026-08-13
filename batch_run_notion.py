import argparse
import gc
import json
import os
import re
import sys
import time
from pathlib import Path
import requests

from backend.answer_cache import AnswerCacheRepository
from backend.chat_completion import ChatCompletionClient
from backend.embedding_artifacts import EmbeddingArtifactStore
from backend.vector_index_store import VectorIndexStore
from backend.config import (
    CACHE_DIR,
    EMBEDDING_ARTIFACT_DIR,
    RUN_DIR,
    VECTOR_INDEX_DIR,
    WORKFLOW_DIR,
)
from backend.module_registry import ModuleRegistry
from backend.workflows.store import ResultCache, RunStore, WorkflowStore
from backend.workflows.executor import WorkflowExecutor
from backend.workflows.models import WorkflowExecutionRequest

DEFAULT_PAGE_ID = "3b5edca2-9a15-8034-9c5d-f40a5fbcfcec"
OUTPUT_DIR = Path("outputs/notion_runs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_shared_executor(workflow_name: str = "workflow"):
    """Initialize module registry and workflow executor."""
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

    workflow = workflow_store.load(workflow_name)
    executor = WorkflowExecutor(registry, run_store, result_cache)

    # Find query_input node ID and reader node ID
    query_node_id = None
    reader_node_id = None
    for node in workflow.graph.nodes:
        if node.module_type == "query_input" and not query_node_id:
            query_node_id = node.id
        elif node.module_type == "reader" and not reader_node_id:
            reader_node_id = node.id

    if not query_node_id:
        query_node_id = "custom-node-1786497067905-2"
    if not reader_node_id:
        reader_node_id = "custom-node-1786497793017-1"

    return workflow, executor, query_node_id, reader_node_id


def extract_reader_answer(res_run, reader_node_id: str):
    """Extract reader module answer from execution result."""
    # 1. Primary reader node
    reader_node = res_run.nodes.get(reader_node_id)
    if reader_node and isinstance(reader_node.output, dict):
        ans_json = reader_node.output.get("answer_json")
        if isinstance(ans_json, dict) and isinstance(ans_json.get("answer"), str):
            ans = ans_json["answer"].strip()
            if ans:
                return ans, ans_json.get("api_usage", {})
        ans = reader_node.output.get("answer")
        if isinstance(ans, str) and ans.strip():
            return ans.strip(), reader_node.output.get("api_usage", {})

    # 2. Fallback to json inspector or any node with answer
    for nid, node in res_run.nodes.items():
        if isinstance(node.output, dict):
            ans = node.output.get("answer")
            if isinstance(ans, str) and ans.strip():
                return ans.strip(), node.output.get("api_usage", {})
            ans_json = node.output.get("answer_json")
            if isinstance(ans_json, dict) and isinstance(ans_json.get("answer"), str):
                ans = ans_json["answer"].strip()
                if ans:
                    return ans, ans_json.get("api_usage", {})

    return "", {}


def process_single_question(q_id: str, question_text: str, workflow, executor, query_node_id: str, reader_node_id: str, use_cache: bool = True):
    """Run pipeline for a single question with disk caching."""
    cache_file = OUTPUT_DIR / f"{q_id}.json"
    legacy_cache_file = Path("outputs") / f"{q_id}.json"
    
    if use_cache:
        for cf in [cache_file, legacy_cache_file]:
            if cf.exists():
                try:
                    with open(cf, "r", encoding="utf-8") as f:
                        cached_data = json.load(f)
                    ans = cached_data.get("pipeline_answer", "")
                    if isinstance(ans, str) and ans.strip():
                        print(f"[{q_id}] Loaded from local cache ({cf.name}).", flush=True)
                        return cached_data, True
                except Exception:
                    pass

    print(f"[{q_id}] Executing pipeline for question: {question_text[:50]}...", flush=True)
    t0 = time.time()
    req = WorkflowExecutionRequest(
        inputs={query_node_id: {"query": question_text}},
        use_cache=False,
    )
    run = executor.create_run(workflow, req)
    res_run = executor.execute_all(run.id)
    elapsed = time.time() - t0

    answer, usage = extract_reader_answer(res_run, reader_node_id)

    result_data = {
        "id": q_id,
        "question": question_text,
        "pipeline_answer": answer,
        "api_usage": usage,
        "latency_seconds": round(elapsed, 3),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    # Clean run temporary files
    (RUN_DIR / f"{run.id}.json").unlink(missing_ok=True)
    (RUN_DIR / f"{run.id}.summary.json").unlink(missing_ok=True)
    gc.collect()

    print(f"[{q_id}] Done in {elapsed:.2f}s (Answer len: {len(answer)})", flush=True)
    return result_data, False


def update_notion_via_api(notion_key: str, page_id: str, results_by_id: dict):
    """Update Notion page blocks directly via Notion API if NOTION_API_KEY is available."""
    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    
    # Retrieve top-level page blocks
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        print(f"Notion API error fetching blocks: {res.status_code} {res.text}")
        return False

    blocks = res.json().get("results", [])
    print(f"Fetched {len(blocks)} top-level blocks from Notion page.")

    updated_count = 0
    for block in blocks:
        block_id = block["id"]
        block_type = block["type"]
        
        # Check toggle / details block
        if block_type in ["toggle", "template"]:
            # Check children of toggle block
            child_url = f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=100"
            c_res = requests.get(child_url, headers=headers)
            if c_res.status_code == 200:
                c_blocks = c_res.json().get("results", [])
                q_id = None
                code_block_id = None
                
                for cb in c_blocks:
                    cb_type = cb["type"]
                    if cb_type == "bulleted_list_item":
                        text_content = "".join([t.get("plain_text", "") for t in cb["bulleted_list_item"].get("rich_text", [])])
                        if "문항 ID" in text_content:
                            m = re.search(r"Q\d+", text_content)
                            if m:
                                q_id = m.group(0)
                    elif cb_type == "code":
                        code_block_id = cb["id"]

                if q_id and code_block_id and q_id in results_by_id:
                    answer_text = results_by_id[q_id].get("pipeline_answer", "")
                    if answer_text:
                        patch_url = f"https://api.notion.com/v1/blocks/{code_block_id}"
                        patch_data = {
                            "code": {
                                "rich_text": [{"type": "text", "text": {"content": answer_text}}],
                                "language": "plain text",
                            }
                        }
                        p_res = requests.patch(patch_url, headers=headers, json=patch_data)
                        if p_res.status_code == 200:
                            updated_count += 1
                            print(f"Updated Notion block for [{q_id}]")
                        else:
                            print(f"Failed to patch block for [{q_id}]: {p_res.status_code} {p_res.text}")

    print(f"Successfully updated {updated_count} blocks in Notion.")
    return True


def build_updated_markdown(dump_path: Path, results_by_id: dict, output_md_path: Path):
    """Generate full updated page markdown containing pipeline reader answers inside code blocks."""
    if not dump_path.exists():
        return ""

    with open(dump_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    md = data.get("markdown", "")

    def replace_block(match):
        block = match.group(0)
        q_id_m = re.search(r"\*\*문항 ID\*\*:\s*([^\n\r]+)", block)
        if not q_id_m:
            return block
        q_id = q_id_m.group(1).strip()
        if q_id in results_by_id:
            ans = results_by_id[q_id].get("pipeline_answer", "").strip()
            indented_ans = "\n".join(["\t" + line if line.strip() else "" for line in ans.splitlines()])
            target = "\t- **1차 파이프라인 답변 원문**:\n\t```javascript\n\n\t```"
            replacement = f"\t- **1차 파이프라인 답변 원문**:\n\t```javascript\n{indented_ans}\n\t```"
            if target in block:
                return block.replace(target, replacement)
            return re.sub(
                r"(\t- \*\*1차 파이프라인 답변 원문\*\*:\s*\n\t```javascript\n).*?(\n\t```)",
                lambda m: f"{m.group(1)}{indented_ans}{m.group(2)}",
                block,
                flags=re.DOTALL,
            )
        return block

    updated_md = re.sub(r"<details>.*?</details>", replace_block, md, flags=re.DOTALL)
    
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(updated_md)

    print(f"Updated full page Markdown written to: {output_md_path.resolve()}", flush=True)
    return updated_md


from backend.chat_completion import _project_env_value

def main():
    default_notion_key = _project_env_value("NOTION_API_KEY") or _project_env_value("NOTION_TOKEN") or ""
    parser = argparse.ArgumentParser(description="Batch execute pipeline on Notion questions.")
    parser.add_argument("--page-id", type=str, default=DEFAULT_PAGE_ID, help="Notion page ID")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of questions to process (0 = all)")
    parser.add_argument("--no-cache", action="store_true", help="Bypass local cache")
    parser.add_argument("--notion-key", type=str, default=default_notion_key, help="Notion API Key")
    parser.add_argument("--questions-file", type=str, default="", help="Path to JSON/txt file containing questions list")
    args = parser.parse_args()

    print("=== Notion Pipeline Batch Execution Script ===", flush=True)
    print(f"Page ID: {args.page_id}", flush=True)

    # 1. Initialize Pipeline Executor
    workflow, executor, query_node_id, reader_node_id = get_shared_executor()
    print(f"Workflow loaded. Query Node: {query_node_id}, Reader Node: {reader_node_id}", flush=True)

    # 2. Parse Questions List
    questions = []
    dump_path = Path("/Users/pileuszu/.gemini/antigravity-ide/brain/f28cca4f-7811-4234-b7eb-5fbce0e1450f/.system_generated/steps/48/output.txt")
    
    # Try reading from questions-file if provided
    if args.questions_file and os.path.exists(args.questions_file):
        with open(args.questions_file, "r", encoding="utf-8") as f:
            questions = json.load(f)
    else:
        # Check latest saved dump or parse output step file if available
        if dump_path.exists():
            with open(dump_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            md = data.get("markdown", "")
            details_blocks = re.findall(r"<details>.*?</details>", md, re.DOTALL)
            for d in details_blocks:
                q_id_m = re.search(r"\*\*문항 ID\*\*:\s*([^\n\r]+)", d)
                q_text_m = re.search(r"\*\*질문 원문\*\*:\s*([^\n\r]+)", d)
                if q_id_m and q_text_m:
                    q_id = q_id_m.group(1).strip()
                    q_text = q_text_m.group(1).strip()
                    questions.append({"id": q_id, "question": q_text, "raw_block": d})

    if not questions:
        print("Error: No questions found. Provide --questions-file or verify Notion page output.", flush=True)
        sys.exit(1)

    if args.limit > 0:
        questions = questions[: args.limit]

    print(f"Total questions to process: {len(questions)}", flush=True)

    # 3. Iterative Execution Loop
    results_by_id = {}
    cached_count = 0
    executed_count = 0

    for idx, q in enumerate(questions, 1):
        q_id = q["id"]
        q_text = q["question"]
        print(f"\n--- Progress ({idx}/{len(questions)}): {q_id} ---", flush=True)
        
        result_data, is_cached = process_single_question(
            q_id=q_id,
            question_text=q_text,
            workflow=workflow,
            executor=executor,
            query_node_id=query_node_id,
            reader_node_id=reader_node_id,
            use_cache=not args.no_cache,
        )
        
        results_by_id[q_id] = result_data
        if is_cached:
            cached_count += 1
        else:
            executed_count += 1

    # Save summary batch file
    summary_file = OUTPUT_DIR / "batch_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(results_by_id, f, ensure_ascii=False, indent=2)

    # Generate updated full markdown
    output_md_file = OUTPUT_DIR / "updated_notion_page.md"
    build_updated_markdown(dump_path, results_by_id, output_md_file)

    print("\n=== Execution Summary ===", flush=True)
    print(f"Total Processed: {len(questions)}", flush=True)
    print(f"From Cache: {cached_count}", flush=True)
    print(f"Newly Executed: {executed_count}", flush=True)
    print(f"Summary Saved To: {summary_file.resolve()}", flush=True)

    # 4. Notion Page Block Updating
    if args.notion_key:
        print("\nUpdating Notion page directly via REST API...", flush=True)
        update_notion_via_api(args.notion_key, args.page_id, results_by_id)
    else:
        print("\nNote: NOTION_API_KEY not provided. Results saved to local cache/summary and updated_notion_page.md.", flush=True)
        print("To update Notion directly, pass --notion-key or set NOTION_API_KEY in .env.", flush=True)


if __name__ == "__main__":
    main()
