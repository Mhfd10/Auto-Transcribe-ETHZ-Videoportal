import os
import requests
import xml.etree.ElementTree as ET
import concurrent.futures
from tqdm import tqdm
import whisper

# Verzeichnisse für Downloads und Transkriptionen
download_dir = ("NAME_Vorlesungen")
transcriptions_dir = ("NAME_Transkription")
os.makedirs(download_dir, exist_ok=True)
os.makedirs(transcriptions_dir, exist_ok=True)

# Pfad zur XML-Datei
rss_file = "XXX-XXXX-XXL.rss.xml"

# XML-Datei parsen
try:
    tree = ET.parse(rss_file)
    root = tree.getroot()
except Exception as e:
    print(f"Fehler beim Parsen der XML-Datei: {e}")
    exit()

# Video-Links extrahieren
video_links = []
for item in root.findall(".//item"):
    enclosure = item.find("enclosure")
    pub_date = item.find("pubDate")
    if enclosure is not None and pub_date is not None:
        url = enclosure.attrib.get("url")
        title = pub_date.text.split("T")[0]  # Verwende das Datum als Titel
        video_links.append((title, url))

# Funktion zum Überprüfen, ob ein Download vollständig ist
def is_download_complete(filepath, expected_size):
    return os.path.exists(filepath) and os.path.getsize(filepath) >= expected_size

# Funktion zum Herunterladen eines Videos
def download_video(url, title):
    video_filename = os.path.join(download_dir, f"{title}.mp4")
    if os.path.exists(video_filename):
        return video_filename

    try:
        response = requests.get(url, stream=True, timeout=120)
        total_size = int(response.headers.get('content-length', 0))
        with open(video_filename, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        if not is_download_complete(video_filename, total_size):
            print(f"Download von {title} unvollständig")
            return None
        return video_filename
    except Exception as e:
        print(f"Fehler beim Herunterladen von {title}: {e}")
        return None

# Videos herunterladen
with tqdm(total=len(video_links), desc="Download Fortschritt", unit="Video", dynamic_ncols=True) as progress_bar:
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for title, url in video_links:
            futures.append(executor.submit(download_video, url, title))

        for future in concurrent.futures.as_completed(futures):
            if future.result():
                progress_bar.update(1)

# Liste der heruntergeladenen Videos abrufen
video_files = [f for f in os.listdir(download_dir) if f.endswith(".mp4")]

# model loader
def load_whisper_model(model_name="base"):
    return whisper.load_model(model_name)

# Funktion zum Überprüfen, ob eine Transkription bereits existiert
def is_transcription_complete(video_filename):
    transcription_filename = os.path.join(transcriptions_dir, f"{os.path.splitext(video_filename)[0]}.txt")
    return os.path.exists(transcription_filename)

# Funktion zum Transkribieren eines Videos mit Whisper
def transcribe_audio(file_path, output_path):
    try:
        model = load_whisper_model("base")
        result = model.transcribe(file_path)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result['text'])
    except Exception as e:
        print(f"Fehler bei der Transkription von {file_path}: {e}")

# Transkription der Videos
with tqdm(total=len(video_files), desc="Transkriptionsfortschritt", unit="Video", dynamic_ncols=True) as progress_bar:
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for video_file in video_files:
            input_path = os.path.join(download_dir, video_file)
            output_path = os.path.join(transcriptions_dir, f"{os.path.splitext(video_file)[0]}.txt")

            if is_transcription_complete(video_file):
                progress_bar.update(1)
                continue

            futures.append(executor.submit(transcribe_audio, input_path, output_path))

        for future in concurrent.futures.as_completed(futures):
            progress_bar.update(1)

print("Alle Videos wurden heruntergeladen, transkribiert und die Ergebnisse gespeichert.")
