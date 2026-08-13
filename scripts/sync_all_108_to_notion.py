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

def load_results():
    results = {}
    outputs_dir = Path("outputs")
    for qf in sorted(outputs_dir.glob("Q*.json")):
        try:
            data = json.loads(qf.read_text(encoding="utf-8"))
            q_id = data["id"]
            ans = data.get("pipeline_answer", "").strip()
            if ans:
                results[q_id] = ans
        except Exception as e:
            print(f"Error reading {qf}: {e}")
    print(f"Loaded {len(results)} question results from outputs/")
    return results

def get_all_blocks(block_id):
    blocks = []
    has_more = True
    start_cursor = None

    while has_more:
        url = f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=100"
        if start_cursor:
            url += f"&start_cursor={start_cursor}"
        
        res = requests.get(url, headers=HEADERS)
        if res.status_code != 200:
            print(f"Error fetching blocks for {block_id}: {res.status_code} {res.text}")
            break
        
        data = res.json()
        results = data.get("results", [])
        blocks.extend(results)
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor", None)

    return blocks

def update_notion_page():
    results = load_results()
    if not results:
        print("No results loaded!")
        return

    print(f"Fetching top-level blocks for page {PAGE_ID}...")
    top_blocks = get_all_blocks(PAGE_ID)
    print(f"Fetched {len(top_blocks)} top-level blocks.")

    updated_count = 0
    not_found_count = 0

    for idx, block in enumerate(top_blocks, 1):
        block_id = block["id"]
        block_type = block["type"]

        # Check toggle or template block
        if block_type in ["toggle", "template", "column_list", "column", "bulleted_list_item", "paragraph"]:
            children = get_all_blocks(block_id)
            if not children:
                continue

            q_id = None
            code_block = None

            for cb in children:
                cb_type = cb["type"]
                if cb_type == "bulleted_list_item":
                    text_content = "".join([t.get("plain_text", "") for t in cb["bulleted_list_item"].get("rich_text", [])])
                    if "문항 ID" in text_content:
                        m = re.search(r"Q\d+", text_content)
                        if m:
                            q_id = m.group(0)
                elif cb_type == "code":
                    code_block = cb

            if q_id and code_block:
                if q_id in results:
                    answer_text = results[q_id]
                    patch_url = f"https://api.notion.com/v1/blocks/{code_block['id']}"
                    
                    # Truncate rich_text content to 2000 chars per object if needed for Notion API limit
                    rich_text_array = []
                    for i in range(0, len(answer_text), 1900):
                        rich_text_array.append({
                            "type": "text",
                            "text": {"content": answer_text[i:i+1900]}
                        })

                    patch_payload = {
                        "code": {
                            "rich_text": rich_text_array,
                            "language": "plain text"
                        }
                    }
                    res = requests.patch(patch_url, headers=HEADERS, json=patch_payload)
                    if res.status_code == 200:
                        updated_count += 1
                        print(f"[{idx}/{len(top_blocks)}] Updated Notion block for {q_id}")
                    else:
                        print(f"[{idx}/{len(top_blocks)}] Failed {q_id}: {res.status_code} {res.text}")
                    time.sleep(0.1)
                else:
                    not_found_count += 1

    print("\n=== Notion Update Completed ===")
    print(f"Updated blocks: {updated_count}")
    print(f"Questions without cached answer: {not_found_count}")

if __name__ == "__main__":
    update_notion_page()
