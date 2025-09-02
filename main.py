import os
import psutil
import requests
import xml.etree.ElementTree as ET
import concurrent.futures
import torch
from tqdm import tqdm
import whisper

def lecture_exists(lecture_name):
    """Check if the lecture folder exists."""
    return os.path.exists(lecture_name + "_Vorlesungen") and os.path.exists(lecture_name + "_Transkription")

def create_new_lecture(lecture_name):
    """Create a new lecture folder and get RSS link from the user."""
    rss_filelink = input('Gib den RSS-File Link an: ')
    with open(f"{lecture_name}_rss_link.txt", "w") as f:
        f.write(rss_filelink)
    return rss_filelink

def get_rss_link(lecture_name):
    """Retrieve the RSS link for an existing lecture."""
    rss_file_path = f"{lecture_name}_rss_link.txt"
    if os.path.exists(rss_file_path):
        with open(rss_file_path, "r") as f:
            return f.read().strip()
    return None

def parse_rss_feed(rss_filelink, lecture_name):
    """Parse the RSS feed and extract video links."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36"}

    try:
        response = requests.get(rss_filelink, headers=headers, timeout=60)
        response.raise_for_status()
        xml_path = os.path.join(lecture_name + "_Vorlesungen", "rss_feed.xml")
        with open(xml_path, "wb") as f:
            f.write(response.content)

        tree = ET.parse(xml_path)
        root = tree.getroot()
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP-Fehler: {http_err}")
        return []
    except requests.exceptions.RequestException as req_err:
        print(f"Verbindungsfehler: {req_err}")
        return []
    except Exception as e:
        print(f"Fehler beim Abrufen/Parsen der RSS-Datei: {e}")
        return []

    video_links = []
    for item in root.findall(".//item"):
        enclosure = item.find("enclosure")
        pub_date = item.find("pubDate")
        if enclosure is not None and pub_date is not None:
            url = enclosure.attrib.get("url")
            title = pub_date.text.split("T")[0]
            video_links.append((title, url))
    return video_links

def is_download_complete(filepath, expected_size):
    return os.path.exists(filepath) and os.path.getsize(filepath) >= expected_size

def download_video(url, title, download_dir):
    """Download a video if it does not already exist."""
    video_filename = os.path.join(download_dir, f"{title}.mp4")
    transcription_filename = os.path.join(transcriptions_dir, f"{title}.txt")
    if os.path.exists(transcription_filename) or os.path.exists(video_filename):
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

def load_whisper_model(model_name):
    return whisper.load_model(model_name)

def is_transcription_complete(video_filename, transcriptions_dir):
    transcription_filename = os.path.join(transcriptions_dir, f"{os.path.splitext(video_filename)[0]}.txt")
    return os.path.exists(transcription_filename)

def get_available_vram_gb():
    try:
        return torch.cuda.mem_get_info(0)/(1024**3)
    except Exception:
        return None

def get_available_ram_gb():
    try:
        return psutil.virtual_memory().available/(1024**3)
    except Exception:
        return None

def choose_whisper_model():
    """Decide model_name based on available memory."""

    # model list
    whisper_memory_dic = {
        "tiny": {"vram": 1.0, "ram": 1.0},
        "base": {"vram": 1.0, "ram": 1.0},
        "small": {"vram": 2.0, "ram": 3.0},
        "medium": {"vram": 5.0, "ram": 6.0},
        "large": {"vram": 10.0, "ram": 10.0},
        "turbo": {"vram": 6.0, "ram": 7.0},
    }

    # in greedy order
    model_ordered = ["large", "turbo", "medium", "small", "base", "tiny"]

    # get memory info
    free_vram_gb = get_available_vram_gb()
    free_ram_gb = get_available_ram_gb()

    # try gpu
    if free_vram_gb is not None:
        for name in model_ordered:
            need = whisper_memory_dic[name]["vram"]
            if free_vram_gb//2 >= need:
                print(f"Nutze Model: {name} auf GPU.")
                return name

    # or cpu
    else:
        for name in model_ordered:
            need = whisper_memory_dic[name]["ram"]
            if free_ram_gb//2 >= need:
                print(f"Nutze Model: {name} auf CPU.")
                return name

    raise RuntimeError("Zu wenig RAM/VRAM.")

def transcribe_audio(file_path, output_path):
    """Transcribe an audio file using Whisper."""
    try:
        chosen_model = choose_whisper_model()
        model = load_whisper_model(chosen_model)
        result = model.transcribe(file_path)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result['text'])
    except Exception as e:
        print(f"Fehler bei der Transkription von {file_path}: {e}")


""" Hauptprozess """

lecture = input('Welche Vorlesung möchtest du herunterladen und transkribieren: ')

if lecture_exists(lecture):
    print("Vorlesung existiert bereits. Verwende gespeicherten RSS-Link.")
    rss_filelink = get_rss_link(lecture)
    if not rss_filelink:
        rss_filelink = create_new_lecture(lecture)
else:
    print("Erstelle neue Vorlesung.")
    rss_filelink = create_new_lecture(lecture)

download_dir = lecture + "_Vorlesungen"
transcriptions_dir = lecture + "_Transkription"
os.makedirs(download_dir, exist_ok=True)
os.makedirs(transcriptions_dir, exist_ok=True)

video_links = parse_rss_feed(rss_filelink, lecture)
if not video_links:
    print("Keine Videos gefunden. Beende Skript.")
    exit()

# download
with tqdm(total=len(video_links), desc="Download Fortschritt", unit="Video", dynamic_ncols=True) as progress_bar:
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(download_video, url, title, download_dir) for title, url in video_links]
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                progress_bar.update(1)

video_files = [f for f in os.listdir(download_dir) if f.endswith(".mp4")]

# transcribe
with tqdm(total=len(video_files), desc="Transkriptionsfortschritt", unit="Video", dynamic_ncols=True) as progress_bar:
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for video_file in video_files:
            input_path = os.path.join(download_dir, video_file)
            output_path = os.path.join(transcriptions_dir, f"{os.path.splitext(video_file)[0]}.txt")
            if is_transcription_complete(video_file, transcriptions_dir):
                progress_bar.update(1)
                continue
            futures.append(executor.submit(transcribe_audio, input_path, output_path))
        for future in concurrent.futures.as_completed(futures):
            progress_bar.update(1)

print("Alle Videos wurden heruntergeladen, transkribiert und die Ergebnisse gespeichert.")

