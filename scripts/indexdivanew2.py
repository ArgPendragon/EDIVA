import os
import json

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

def index_files(root_dir):
    data = {
        "codex": None,
        "novel": None,
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

            file_metadata = folder_metadata if filename != "metadata.json" else None

            # Handle main files
            if filename.lower() == "codex.html":
                data["codex"] = {
                    "file_name": filename,
                    "folder": "root",
                    "title": "Codex",
                    "content": content
                }
                metadata[rel_path] = {"type": "codex", "folder": "root", "file_name": filename, "description": "File HTML del Codex"}
            elif filename.lower() == "novel.md":
                data["novel"] = {
                    "file_name": filename,
                    "folder": "root",
                    "title": "Novel",
                    "content": content
                }
                metadata[rel_path] = {"type": "novel", "folder": "root", "file_name": filename, "description": "Manoscritto completo in markdown"}
            else:
                # Entries & Notes
                entry_data = {
                    "file_name": filename,
                    "folder": folder_name,
                    "title": title,
                    "content": content
                }

                if file_metadata:
                    entry_data.update({
                        "id": file_metadata.get("id"),
                        "type": file_metadata["attributes"].get("type"),
                        "aliases": file_metadata["attributes"].get("aliases", []),
                        "tags": file_metadata["attributes"].get("tags", []),
                        "relationships": file_metadata.get("relationships", {})
                    })

                if "entry" in filename.lower():
                    data["entries"].append(entry_data)
                    metadata[rel_path] = {
                        "type": "entry",
                        "folder": folder_name,
                        "file_name": filename,
                        "description": f"Informazioni su '{title}'",
                        "metadata_id": file_metadata.get("id") if file_metadata else None,
                        "tags": file_metadata["attributes"].get("tags", []) if file_metadata else [],
                        "aliases": file_metadata["attributes"].get("aliases", []) if file_metadata else [],
                        "related_entries": file_metadata["relationships"].get("nestedEntries", []) if file_metadata else []
                    }
                else:
                    data["notes"].append(entry_data)

    return data, metadata

if __name__ == "__main__":
    root_dir = os.getcwd()
    data, metadata = index_files(root_dir)

    with open("data.json", "w", encoding="utf-8") as f_data:
        json.dump(data, f_data, indent=2, ensure_ascii=False)

    with open("metadata.json", "w", encoding="utf-8") as f_meta:
        json.dump(metadata, f_meta, indent=2, ensure_ascii=False)

    print("✅ Indexing complete. Files 'data.json' and 'metadata.json' created.")
