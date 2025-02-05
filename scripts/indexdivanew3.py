import os
import json
import re
from collections import Counter

def load_folder_metadata(folder_path):
    """Load metadata.json if present in a folder."""
    metadata_path = os.path.join(folder_path, "metadata.json")
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Error reading metadata in {folder_path}: {e}")
    return None

def extract_keywords(text, num_keywords=5):
    """Extracts potential keywords from text based on frequency."""
    words = re.findall(r'\b\w{5,}\b', text.lower())  # Consider words with 5+ characters
    common_words = set(["scene", "chapter", "entry", "note", "title"])
    word_counts = Counter(w for w in words if w not in common_words)
    return [word for word, _ in word_counts.most_common(num_keywords)]

def parse_novel(content):
    """Parses novel.md and splits it into structured sections."""
    acts = re.split(r'(?=^## \w+)', content, flags=re.MULTILINE)
    parsed_scenes = []
    keyword_groups = {}
    
    for act in acts:
        act_match = re.match(r'^## (\w+)', act.strip())
        act_title = act_match.group(1) if act_match else "Unknown Act"
        chapters = re.split(r'(?=^### Chapter \d+:)', act, flags=re.MULTILINE)
        
        for chapter in chapters:
            chapter_match = re.match(r'^### (Chapter \d+: .+)', chapter.strip())
            chapter_title = chapter_match.group(1) if chapter_match else "Unknown Chapter"
            scenes = re.split(r'(?=^#### Scene \d+)', chapter, flags=re.MULTILINE)
            
            for i, scene in enumerate(scenes):
                scene_title_match = re.match(r'^#### (Scene \d+)', scene.strip())
                scene_title = scene_title_match.group(1) if scene_title_match else f"Scene {i+1}"
                summary_match = re.search(r'\n\n(.+?)\n\n', scene.strip())
                summary = summary_match.group(1) if summary_match else "No summary available"
                keywords = extract_keywords(scene)
                
                # Assign scene to keyword-based groups
                for kw in keywords:
                    if kw not in keyword_groups:
                        keyword_groups[kw] = []
                    keyword_groups[kw].append(scene_title)
                
                parsed_scenes.append({
                    "act": act_title,
                    "chapter": chapter_title,
                    "title": scene_title,
                    "summary": summary,
                    "content": scene.strip(),
                    "keywords": keywords,
                    "scene_number": i + 1
                })
    
    return parsed_scenes, keyword_groups

def index_files(root_dir):
    data = {
        "novel": [],
        "entries": [],
        "notes": []
    }
    metadata = {}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        folder_metadata = load_folder_metadata(dirpath)  # Load folder metadata if available
        folder_name = os.path.basename(dirpath)

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                print(f"⚠️ Error reading {filepath}: {e}")
                continue

            rel_path = os.path.relpath(filepath, root_dir)
            title = os.path.splitext(filename)[0].replace("entry_", "").replace("note_", "").title()

            if filename.lower() == "novel.md":
                novel_scenes, keyword_groups = parse_novel(content)
                data["novel"] = novel_scenes
                data["keyword_groups"] = keyword_groups
                metadata[rel_path] = {"type": "novel", "folder": "root", "file_name": filename, "description": "Manoscritto suddiviso per atti, capitoli, scene, con sommari e parole chiave"}
            else:
                # Entries & Notes
                entry_data = {
                    "file_name": filename,
                    "folder": folder_name,
                    "title": title,
                    "content": content
                }
                data["entries"].append(entry_data) if "entry" in filename.lower() else data["notes"].append(entry_data)
    
    return data, metadata

if __name__ == "__main__":
    root_dir = os.getcwd()
    data, metadata = index_files(root_dir)

    with open("data.json", "w", encoding="utf-8") as f_data:
        json.dump(data, f_data, indent=2, ensure_ascii=False)

    with open("metadata.json", "w", encoding="utf-8") as f_meta:
        json.dump(metadata, f_meta, indent=2, ensure_ascii=False)

    print("✅ Indexing complete. Files 'data.json' and 'metadata.json' created.")
