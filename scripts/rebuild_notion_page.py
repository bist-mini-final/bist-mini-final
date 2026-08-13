import os
import sys
import json
import re
import time
import requests
from pathlib import Path

# Add project root directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.chat_completion import _project_env_value

NOTION_TOKEN = _project_env_value("NOTION_API_KEY") or _project_env_value("NOTION_TOKEN") or ""
PAGE_ID = "3b5edca2-9a15-8034-9c5d-f40a5fbcfcec"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def load_questions_and_answers():
    # 1. Load questions and answers from outputs/notion_runs/updated_notion_page.md
    md_path = PROJECT_ROOT / "outputs" / "notion_runs" / "updated_notion_page.md"
    if not md_path.exists():
        print(f"Error: {md_path} does not exist!")
        return []

    raw_md = md_path.read_text(encoding="utf-8")
    details_blocks = re.findall(r"<details>.*?</details>", raw_md, re.DOTALL)
    print(f"Parsed {len(details_blocks)} questions from updated_notion_page.md.")

    # 2. Load cached pipeline answers
    results = {}
    outputs_dir = Path("outputs")
    for qf in sorted(outputs_dir.glob("Q*.json")):
        try:
            data = json.loads(qf.read_text(encoding="utf-8"))
            q_id = data["id"]
            ans = data.get("pipeline_answer", "").strip()
            if ans:
                results[q_id] = ans
        except Exception:
            pass

    print(f"Loaded {len(results)} pipeline answers from outputs/")

    # 3. Build question items list
    items = []
    for d in details_blocks:
        q_id_m = re.search(r"\*\*문항 ID\*\*:\s*([^\n\r]+)", d)
        q_sc_m = re.search(r"\*\*시나리오\*\*:\s*([^\n\r]+)", d)
        q_text_m = re.search(r"\*\*질문 원문\*\*:\s*([^\n\r]+)", d)
        q_gpt_m = re.search(r"\*\*ChatGPT 답변 원문\*\*:\s*([^\n\r]+)", d)

        if q_id_m and q_text_m:
            q_id = q_id_m.group(1).strip()
            sc = q_sc_m.group(1).strip() if q_sc_m else "미분류"
            q_text = q_text_m.group(1).strip()
            gpt_ans = q_gpt_m.group(1).strip() if q_gpt_m else "-"
            pipe_ans = results.get(q_id, "")

            items.append({
                "id": q_id,
                "scenario": sc,
                "question": q_text,
                "chatgpt_answer": gpt_ans,
                "pipeline_answer": pipe_ans,
            })

    print(f"Total structured items ready: {len(items)}")
    return items

def build_notion_toggle_block(item):
    q_id = item["id"]
    question = item["question"]
    sc = item["scenario"]
    gpt_ans = item["chatgpt_answer"]
    pipe_ans = item["pipeline_answer"]

    # Split long pipeline answer into chunks of 1900 chars for Notion API rich_text limit
    code_rich_text = []
    if pipe_ans:
        for i in range(0, len(pipe_ans), 1900):
            code_rich_text.append({
                "type": "text",
                "text": {"content": pipe_ans[i:i+1900]}
            })
    else:
        code_rich_text.append({
            "type": "text",
            "text": {"content": ""}
        })

    return {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": f"[{q_id}] {question}"}
                }
            ],
            "children": [
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": f"문항 ID: {q_id}"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": f"시나리오: {sc}"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": f"질문 원문: {question}"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": f"ChatGPT 답변 원문: {gpt_ans}"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": "1차 파이프라인 답변 원문:"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "code",
                    "code": {
                        "rich_text": code_rich_text,
                        "language": "plain text"
                    }
                }
            ]
        }
    }

def clear_existing_blocks():
    url = f"https://api.notion.com/v1/blocks/{PAGE_ID}/children?page_size=100"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        blocks = res.json().get("results", [])
        print(f"Clearing {len(blocks)} existing blocks from Notion page...")
        for b in blocks:
            del_url = f"https://api.notion.com/v1/blocks/{b['id']}"
            requests.delete(del_url, headers=HEADERS)
            time.sleep(0.05)
        print("Existing blocks cleared.")

def append_blocks_in_batches(items):
    url = f"https://api.notion.com/v1/blocks/{PAGE_ID}/children"
    
    # Notion API allows max 100 blocks per request. We send 20 toggle blocks per request to be safe with child limits.
    batch_size = 20
    for i in range(0, len(items), batch_size):
        chunk = items[i:i+batch_size]
        blocks_payload = [build_notion_toggle_block(item) for item in chunk]
        
        payload = {"children": blocks_payload}
        res = requests.patch(url, headers=HEADERS, json=payload)
        
        if res.status_code == 200:
            print(f"Appended questions {i+1} to {i+len(chunk)} (Q{chunk[0]['id']} - Q{chunk[-1]['id']})")
        else:
            print(f"Failed to append batch {i+1}-{i+len(chunk)}: {res.status_code} {res.text}")
        
        time.sleep(0.5)

def main():
    print("=== Notion Page Rebuilder (All 108 Questions) ===")
    items = load_questions_and_answers()
    if not items:
        print("No items to push!")
        return

    clear_existing_blocks()
    print("Pushing all 108 questions with pipeline answers to Notion...")
    append_blocks_in_batches(items)
    print("\n=== Notion Page Rebuild Completed Successfully! ===")

if __name__ == "__main__":
    main()
