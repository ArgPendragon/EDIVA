README: Novel & Database Index Structure
This system indexes a structured dataset containing a novel and a database of entities (characters, locations, concepts, factions, etc.). The indexer produces two files:

indexdiva.json - The full (detailed) index of all entries.
metadiva.json - A slimmed-down structured map for faster querying and relationship analysis.
File Breakdown
1. indexdiva.json (Full Index)
📌 Purpose:
This file contains all the indexed data in full detail, including:

Novel Scenes (full text, summaries, structure, keywords)
Database Entries (characters, locations, events, etc., with full descriptions)
Notes (unofficial database elements)
Keyword Groups (linking keywords to the scenes where they appear)
📌 Structure:

json
Copia
Modifica
{
  "novel": [
    {
      "act": "Antefatto",
      "chapter": "Krug",
      "title": "Scene 1",
      "summary": "...",
      "content": "...",
      "keywords": ["Krug", "Tarn", "Nara"],
      "scene_index": 1
    }
  ],
  "entries": [
    {
      "title": "Battaglia di Roma",
      "category": "official",
      "ty": "Event",
      "keywords": ["Markelos"],
      "content": "... full text ...",
      "id": "a7b92c3d",
      "nestedEntries": ["2lF0JpnxOTbIfFZ8uGlAqAMrUWu"]
    }
  ],
  "notes": [...],
  "keyword_groups": { "Krug": ["Scene 1", "Scene 2"] }
}
2. metadiva.json (Slim Structured Map)
📌 Purpose:
This file is a compact version optimized for navigation, relationship search, and efficient AI querying.

📌 Structure:

json
Copia
Modifica
{
  "novel": {
    "Antefatto": {
      "Krug": [
        {"title": "Scene 1", "i": 1},
        {"title": "Scene 2", "i": 2}
      ]
    }
  },
  "database": [
    {
      "t": "Battaglia di Roma",
      "ty": "Event",
      "id": "a7b92c3d",
      "c": [
        {"id": "2lF0JpnxOTbIfFZ8uGlAqAMrUWu", "t": "Assedio di Milano", "ty": "Event"}
      ]
    }
  ]
}
📌 Key Changes in the Slim Map:

Novel Structure is Hierarchical (act → chapter → scenes).
Database Entries Use Compact Labels:
t → title
ty → type (e.g., "Character", "Location")
id → unique identifier
c → connections (resolved relationships to other entries)
How to Use the Index
✅ For Full Data (Full Text, Rich Details): Use indexdiva.json.
✅ For Fast Queries (Structure, Relationships, Lookups): Use metadiva.json.

Searching for a Scene
To find a scene by title, look inside:

indexdiva.json → novel (for full text)
metadiva.json → novel (for a structured view)
Searching for a Database Entry
Check metadiva.json → database for a compact overview of an entity and its relationships.
If full content is needed, find the same entity in indexdiva.json → entries.
Finding Related Entries
Use connections (c) in metadiva.json to find related database entries.
Example:
"Battaglia di Roma" is connected to "Assedio di Milano", so you can follow id: "2lF0JpnxOTbIfFZ8uGlAqAMrUWu".