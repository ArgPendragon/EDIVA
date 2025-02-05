import os
import json
import re
import argparse

# --- Predefined Keywords ---
PREDEFINED_KEYWORDS = {
    "personaggi": [
        "Gaia", "Parvati", "Maya", "Farhad", "Abbas", "Anahita", "Mohammadi", "Omar", "Al-Fayed",
        "Aurora", "Biancofiore", "Shabtai", "Klein", "Fei", "Shenlong", "Ilya", "Ivanov",
        "Robert Davis", "Kali"
    ],
    "concetti": [
        "IA", "Plasma Cosmology", "Universo Elettrico",
        "Cybergnostici", "Teoria Polare di Saturno", "Avatar Olografico",
        "Singolarità Tecnologica", "Mondi Virtuali", "Olympus Mons", "Albero dei Pensieri",
        "Teddy", "AI MaIA", "Sette Dee"
    ],
    "ambientazioni": [
        "Red Palace", "Orbital City", "Shamash Wheel", "Proxima Centauri", "Alpha Centauri",
        "Luna", "Terra", "Singapore", "Janus HQ", "Bougainville", "Birkeland Sail"
    ],
    "fazioni": [
        "Janus Dynamics", "Figli di Nun", "Legione", "New Thunderbolt",
        "Colonia Lunare", "Esercito Cinese", "CCP", "USA", "ONU", "IA Militari"
    ]
}

# --- Extended Stop Words (Italian and English) ---
STOP_WORDS = {
    # Italian stop words
    "il", "la", "lo", "i", "gli", "le", "un", "una", "uno", "no", "ma", "non", "dopo", "solo", "era", "erano",
    "per", "tra", "fra", "dei", "degli", "delle", "del", "della", "e", "di", "a", "al", "da", "in", "con", "su",
    "ogni", "quando", "sullo", "sulla", "sul", "sulle", "sulle", "alcuni", "questi", "questa", "questo",
    "tutti", "tutto", "nessun", "qualcuno", "nessuno","tutte", "altri", "altro", "nella", "dentro", "fuori",
    "certo", "immagina", "anche", "alla", "ed", "se", "dall", "torna", "uso", "atto", "cosa", "cose", "prendi",
    "rappresenta", 

    # English stop words
    "the", "The", "and", "or", "but", "if", "then", "with", "a", "an", "of", "for", "some", "many", "much",
    "both", "follow", "in", "on", "at", "to", "by", "is", "are", "was", "were", "be", "been", "am",
    "take", "like", "just", "so", "then", "now", "well", "also", "though", "because", "as", "until",
    "between", "among", "without", "within", "against", "during", "along", "following", "across",
    "behind", "beside", "opposed", "regarding", "concerning", "about", "above", "below", "over",
    "under", "again", "further",
}

# --- Image File Extensions to Skip ---
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg'}

def normalize_keyword(keyword):
    """Normalize a candidate keyword by stripping extra whitespace and removing duplicate repetition."""
    keyword = keyword.strip()
    words = keyword.split()
    if len(words) >= 2 and len(words) % 2 == 0:
        half = len(words) // 2
        if words[:half] == words[half:]:
            return " ".join(words[:half])
    return keyword

def extract_keywords(text, num_keywords=10):
    """
    Extract keywords from text.
    First checks predefined keywords, then uses regex for multiword and single-word proper names.
    Excludes keywords that are in the STOP_WORDS set.
    """
    keywords = []
    normalized_set = set()

    def try_add_keyword(candidate):
        normalized = normalize_keyword(candidate)
        if normalized.lower() in STOP_WORDS:
            return
        if normalized.lower() in normalized_set:
            return
        normalized_set.add(normalized.lower())
        keywords.append(normalized)

    for group in ["personaggi", "concetti", "ambientazioni", "fazioni"]:
        for keyword in PREDEFINED_KEYWORDS.get(group, []):
            if re.search(r'\b' + re.escape(keyword) + r'\b', text, flags=re.IGNORECASE):
                try_add_keyword(keyword)
                if len(keywords) >= num_keywords:
                    return keywords[:num_keywords]

    multiword = re.findall(r'\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text)
    for phrase in multiword:
        try_add_keyword(phrase)
        if len(keywords) >= num_keywords:
            return keywords[:num_keywords]

    single_words = re.findall(r'\b[A-Z][a-z]+\b', text)
    for word in single_words:
        try_add_keyword(word)
        if len(keywords) >= num_keywords:
            break

    return keywords[:num_keywords]

def extract_folder_info(folder_name):
    """
    Extract folder information.
    Returns a tuple (main_part, folder_id) if the folder name ends with a dash-separated unique ID.
    Otherwise returns (folder_name, None).
    """
    parts = folder_name.rsplit("-", 1)
    if len(parts) == 2 and re.match(r'^[0-9A-Za-z]{6,}$', parts[1]):
        return parts[0], parts[1]
    return folder_name, None

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

def clean_directory_name(directory):
    """Return directory name if it contains only alphanumeric characters, dashes, or underscores."""
    if re.match(r'^[a-zA-Z0-9_-]+$', directory):
        return directory
    return None

def clean_title_from_folder(folder_name):
    """
    Clean the folder name to derive a human-readable title.
    For example, if the folder name is:
      "999-guerriere-di-giada-yujun-玉军-2beCrJrUys9PfglXxOBmG4k2zBQ"
    then this function returns a tuple:
      ("999 guerriere di giada", "yujun-玉军-2beCrJrUys9PfglXxOBmG4k2zBQ")
    Adjust the splitting logic as needed.
    """
    parts = folder_name.split("-")
    if len(parts) > 4:
        title = " ".join(parts[:4])
        nested = "-".join(parts[4:])
        return title, nested
    else:
        return folder_name.replace("-", " "), None

# --- Older version of parse_entry (integrated) ---
def parse_entry(content):
    """
    Parses an entry file (YAML frontmatter, JSON, or line-based)
    and extracts metadata, keywords, and cleaned content.
    """
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            rest = parts[2]
            fm_metadata = {}
            for line in frontmatter.splitlines():
                if ':' in line:
                    key, val = line.split(':', 1)
                    fm_metadata[key.strip()] = val.strip().strip('"')
            metadata = {}
            if "title" in fm_metadata and fm_metadata["title"]:
                metadata["title"] = fm_metadata["title"]
            cleaned_content = rest.strip()
            keywords = extract_keywords(cleaned_content, num_keywords=10)
            if "title" not in metadata or not metadata["title"]:
                words = cleaned_content.split()
                metadata["title"] = " ".join(words[:5]) + ("..." if len(words) > 5 else "")
            return metadata, keywords, cleaned_content

    try:
        json_data = json.loads(content)
        if isinstance(json_data, dict) and "attributes" in json_data:
            attributes = json_data["attributes"]
            friendly_title = attributes.get("name", None)
            metadata = {"title": friendly_title} if friendly_title else {}
            if "relationships" in json_data and "nestedEntries" in json_data["relationships"]:
                metadata["nestedEntries"] = json_data["relationships"]["nestedEntries"]
            cleaned_content = json.dumps(json_data, indent=2, ensure_ascii=False)
            keywords = extract_keywords(friendly_title, num_keywords=10) if friendly_title else []
            return metadata, keywords, cleaned_content
    except json.JSONDecodeError:
        pass

    metadata = {}
    for line in content.splitlines():
        if line.startswith("Title:"):
            metadata["title"] = line.split(":", 1)[1].strip()
        elif line.startswith("Author:"):
            metadata["author"] = line.split(":", 1)[1].strip()
        elif line.startswith("Date:"):
            metadata["date"] = line.split(":", 1)[1].strip()

    cleaned_content = " ".join(content.splitlines()).strip()
    if "title" not in metadata or not metadata["title"]:
        words = cleaned_content.split()
        metadata["title"] = " ".join(words[:5]) + ("..." if len(words) > 5 else "")
    keywords = extract_keywords(cleaned_content, num_keywords=10)
    return metadata, keywords, cleaned_content

def parse_novel(content):
    scenes = []
    metadata = {}
    keyword_groups = {}
    current_act = None
    current_chapter = None
    current_scene_title = None
    summary_lines = []
    content_lines = []
    mode = "summary"
    sequence_number = 1

    def finalize_scene():
        nonlocal sequence_number, current_scene_title, summary_lines, content_lines, mode
        if current_scene_title:
            scene_content = " ".join(content_lines).strip() if content_lines else " ".join(summary_lines).strip()
            scene_summary = " ".join(summary_lines).strip()
            keywords = extract_keywords(scene_summary)
            for kw in keywords:
                keyword_groups.setdefault(kw, []).append(current_scene_title)
            scenes.append({
                "act": current_act,
                "chapter": current_chapter,
                "title": current_scene_title,
                "summary": scene_summary,
                "content": scene_content,
                "keywords": keywords,
                "scene_index": sequence_number
            })
            metadata.setdefault(current_act, {"chapters": {}})
            metadata[current_act]["chapters"].setdefault(current_chapter, [])
            metadata[current_act]["chapters"][current_chapter].append({
                "title": current_scene_title,
                "i": sequence_number
            })
            sequence_number += 1

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current_act = stripped[3:].strip()
            if current_act not in metadata:
                metadata[current_act] = {"chapters": {}}
            continue
        if stripped.startswith("### "):
            current_chapter = stripped[4:].strip()
            if current_act is None:
                current_act = "Unknown Act"
                metadata.setdefault(current_act, {"chapters": {}})
            if current_chapter not in metadata[current_act]["chapters"]:
                metadata[current_act]["chapters"][current_chapter] = []
            continue
        if stripped.startswith("#### "):
            if current_scene_title:
                finalize_scene()
            current_scene_title = stripped[5:].strip()
            summary_lines = []
            content_lines = []
            mode = "summary"
            continue
        if current_scene_title:
            if stripped == "---" and mode == "summary":
                mode = "content"
            else:
                if mode == "summary":
                    summary_lines.append(stripped)
                else:
                    content_lines.append(stripped)

    if current_scene_title:
        finalize_scene()

    return scenes, metadata, keyword_groups

def index_files(root_dir):
    data = {
        "novel": [],
        "entries": [],
        "notes": [],
        "keyword_groups": {}
    }
    metadata_all = {}  # For novel files only

    for dirpath, _, filenames in os.walk(root_dir):
        load_folder_metadata(dirpath)
        rel_dir = os.path.relpath(dirpath, root_dir)
        parts = [] if rel_dir == "." else rel_dir.split(os.sep)
        
        # Check if the file is inside a "chats" or "snippets" folder
        if parts and parts[0].lower() in ["chats", "snippets"]:
            # In these cases we use only one folder level.
            type_field = parts[0].replace('-', ' ').title()
            entry_folder = None  # no second level exists
        else:
            # Otherwise, expect two folder levels:
            #   parts[0] is the type, parts[1] is the folder providing the title.
            if len(parts) >= 2:
                type_field = parts[0].replace('-', ' ').title()
                entry_folder = parts[1]
            else:
                # fallback if directory structure is not as expected
                type_field = "Unknown"
                entry_folder = parts[0] if parts else None

        # If we have an entry_folder (i.e. non-chats/snippets), clean it for title extraction.
        if entry_folder:
            cleaned_entry_folder = clean_directory_name(entry_folder)
        else:
            cleaned_entry_folder = None

        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in IMAGE_EXTENSIONS or filename.lower() == "metadata.json":
                continue

            filepath = os.path.join(dirpath, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    file_content = f.read()
            except Exception as e:
                print(f"⚠️ Error reading {filepath}: {e}")
                continue

            rel_path = os.path.relpath(filepath, root_dir)

            if filename.lower() == "novel.md":
                novel_scenes, novel_metadata, keyword_groups = parse_novel(file_content)
                data["novel"] = novel_scenes
                for kw, scenes_list in keyword_groups.items():
                    data["keyword_groups"].setdefault(kw, []).extend(scenes_list)
                metadata_all[rel_path] = novel_metadata
            else:
                entry_metadata, keywords, cleaned_content = parse_entry(file_content)

                # Determine title and unique ID based on folder structure.
                if entry_folder and cleaned_entry_folder:
                    # For non-chats/snippets, extract title from the second-level folder.
                    final_title, nested_code = clean_title_from_folder(cleaned_entry_folder)
                    # Optionally merge any nested code into the metadata.
                    if nested_code:
                        if "nestedEntries" in entry_metadata:
                            if isinstance(entry_metadata["nestedEntries"], list):
                                if nested_code not in entry_metadata["nestedEntries"]:
                                    entry_metadata["nestedEntries"].append(nested_code)
                            else:
                                entry_metadata["nestedEntries"] = [entry_metadata["nestedEntries"], nested_code]
                        else:
                            entry_metadata["nestedEntries"] = [nested_code]
                    entry_id = nested_code if nested_code else None
                else:
                    # For chats/snippets, derive title from metadata or content.
                    final_title = entry_metadata.get("title", cleaned_content[:30] + "...")
                    entry_id = None
                    # Additional adjustments for chats/snippets can be done here.
                    if type_field.lower() == "snippets":
                        pattern = r'^\d{4}-\d{2}-\d{2}\s+(.*?)(?:\s+-\s+.*)?\.md$'
                        m = re.match(pattern, filename)
                        if m:
                            final_title = m.group(1).strip().title()
                    if type_field.lower() == "chats":
                        if "## User" in cleaned_content or final_title.strip().lower() == "chats":
                            final_title = " ".join(extract_keywords(cleaned_content, num_keywords=5))

                # Determine category based on filename conventions.
                if filename.lower() == "entry.md":
                    category = "official"
                elif filename.lower() == "notes.md":
                    category = "unofficial"
                else:
                    category = "official" if "entry" in filename.lower() else "unofficial"

                ordered_entry_data = {
                    "title": final_title,
                    "category": category,
                    "ty": type_field,
                    "keywords": keywords,
                    "content": cleaned_content,
                }
                if entry_id:
                    ordered_entry_data["id"] = entry_id
                relationships = {}
                if cleaned_entry_folder:
                    folder_main, folder_id = extract_folder_info(cleaned_entry_folder)
                    if folder_id:
                        relationships["folder_id"] = folder_id
                        if not ordered_entry_data.get("id"):
                            ordered_entry_data["id"] = folder_id
                if relationships:
                    ordered_entry_data["relationships"] = relationships
                if "nestedEntries" in entry_metadata:
                    ordered_entry_data["nestedEntries"] = entry_metadata["nestedEntries"]

                if category == "official":
                    data["entries"].append(ordered_entry_data)
                else:
                    data["notes"].append(ordered_entry_data)
    
    return data, metadata_all

def resolve_connections(entries):
    """
    Build a lookup keyed by each entry's unique id.
    Then, for each entry that has raw nestedEntries,
    resolve them into a "connections" field containing expanded connection objects.
    Option 2: Expanded objects.
    """
    lookup = {}
    # Build the lookup. Only for official entries that have an "id".
    for entry in entries:
        entry_id = entry.get("id")
        if entry_id:
            lookup[entry_id] = entry

    # Now, resolve each entry's nestedEntries into connections.
    for entry in entries:
        resolved = []
        for sub_id in entry.get("nestedEntries", []):
            if sub_id in lookup:
                connected = lookup[sub_id]
                resolved.append({
                    "id": sub_id,
                    "t": connected.get("title"),
                    "ty": connected.get("ty")
                })
        if resolved:
            entry["connections"] = resolved
        # Optionally, remove the raw nestedEntries field:
        if "nestedEntries" in entry:
            del entry["nestedEntries"]

def build_structure_map(full_index, novel_structure):
    # Resolve connections in the official entries.
    resolve_connections(full_index.get("entries", []))
    structure_map = {"novel": {}, "database": []}
    structure_map["novel"] = novel_structure
    for entry in full_index.get("entries", []) + full_index.get("notes", []):
        database_entry = {"t": entry.get("title"), "ty": entry.get("ty")}
        if entry.get("id"):
            database_entry["id"] = entry.get("id")
        # Include slim connection data if available.
        if entry.get("connections"):
            slim_connections = []
            for conn in entry["connections"]:
                slim_connections.append({
                    "id": conn.get("id"),
                    "t": conn.get("t"),
                    "ty": conn.get("ty")
                })
            database_entry["c"] = slim_connections
        structure_map["database"].append(database_entry)
    return structure_map

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index a novel directory structure.")
    parser.add_argument(
        "input_dir",
        type=str,
        default=os.getcwd(),
        nargs="?",
        help="Input directory containing the novel files (default: current directory)"
    )
    args = parser.parse_args()
    
    full_index, metadata_all = index_files(args.input_dir)
    
    novel_structure = {}
    if metadata_all:
        novel_structure = next(iter(metadata_all.values()))
    
    structure_map = build_structure_map(full_index, novel_structure)
    
    with open(os.path.join(args.input_dir, "indexdiva.json"), "w", encoding="utf-8") as f_full:
        json.dump(full_index, f_full, indent=2, ensure_ascii=False)
    
    with open(os.path.join(args.input_dir, "metadiva.json"), "w", encoding="utf-8") as f_map:
        json.dump(structure_map, f_map, indent=2, ensure_ascii=False)
    
    print(f"✅ Indexing complete. Files 'indexdiva.json' and 'metadiva.json' created in {args.input_dir}.")