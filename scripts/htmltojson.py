from bs4 import BeautifulSoup
import json

# Leggi il file HTML
with open("input.html", "r", encoding="utf-8") as f:
    html_content = f.read()

# Parsing dell'HTML
soup = BeautifulSoup(html_content, "html.parser")

# Esempio di estrazione: titolo e paragrafi
data = {}
data["title"] = soup.title.string if soup.title else "No title"
data["paragraphs"] = [p.get_text() for p in soup.find_all("p")]

# Salva i dati in un file JSON
with open("output.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4, ensure_ascii=False)

print("Dati estratti e salvati in output.json")
