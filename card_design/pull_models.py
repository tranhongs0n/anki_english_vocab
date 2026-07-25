import urllib.request
import json
import os
import re

ANKI_CONNECT_URL = "http://127.0.0.1:8765"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def invoke(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    req = urllib.request.Request(ANKI_CONNECT_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if data.get("error"):
            raise Exception(f"AnkiConnect error ({action}): {data['error']}")
        return data["result"]

def clean_folder_name(name):
    return re.sub(r'[\\/*?:"<>|]', "_", name)

def get_sample_data_for_model(model_name, fields):
    # Try to fetch 1 real note from Anki DB for realistic sample data
    try:
        note_ids = invoke("findNotes", query=f'"note:{model_name}"')
        if note_ids:
            notes = invoke("notesInfo", notes=[note_ids[0]])
            if notes and len(notes) > 0:
                fields_data = notes[0].get("fields", {})
                return {fname: fields_data.get(fname, {}).get("value", f"Sample {fname}") for fname in fields}
    except Exception as e:
        print(f"  [Warn] Could not fetch real sample note for {model_name}: {e}")

    # Fallback default sample data
    default_samples = {
        "Word": "ephemeral",
        "Vocab": "serendipity",
        "word": "ubiquitous",
        "IPA": "/ɪˈfem.ər.əl/",
        "us_ipa": "ɪˈfem.ər.əl",
        "Definition": "Lasting for a very short time; transitory; short-lived.",
        "Meaning": "Rất ngắn ngủi, phù du, thoáng qua.",
        "Sentence": "The autumn leaves provided an ephemeral burst of color across the valley.",
        "Setence": "The autumn leaves provided an ephemeral burst of color across the valley.",
        "Synonym": "fleeting, transient, momentary, brief",
        "Reference": "https://dictionary.cambridge.org/dictionary/english/ephemeral",
        "Audio": "",
        "audio": "",
        "Picture": "<div style='padding: 20px; background: #333; color: #fff; text-align: center; border-radius: 8px;'>[Sample Image Placeholder]</div>"
    }
    return {fname: default_samples.get(fname, f"Sample {fname}") for fname in fields}

def main():
    print("Connecting to AnkiConnect...")
    try:
        models = invoke("modelNames")
    except Exception as e:
        print(f"Failed to connect to AnkiConnect at {ANKI_CONNECT_URL}: {e}")
        return

    print(f"Found {len(models)} note types: {', '.join(models)}")

    valid_folders = {clean_folder_name(m) for m in models}
    for item in os.listdir(BASE_DIR):
        item_path = os.path.join(BASE_DIR, item)
        if os.path.isdir(item_path) and not item.startswith(".") and item != "__pycache__" and item not in valid_folders:
            import shutil
            shutil.rmtree(item_path, ignore_errors=True)
            print(f"Removed obsolete model folder: '{item}'")

    for model_name in models:
        folder_name = clean_folder_name(model_name)
        model_dir = os.path.join(BASE_DIR, folder_name)
        os.makedirs(model_dir, exist_ok=True)
        print(f"\nProcessing model: '{model_name}' -> folder '{folder_name}'")

        # Get Styling CSS
        css = invoke("modelStyling", modelName=model_name)
        css_path = os.path.join(model_dir, "Styling.css")
        with open(css_path, "w", encoding="utf-8") as f:
            f.write(css.get("css", ""))
        print(f"  Saved Styling.css ({len(css.get('css', ''))} bytes)")

        # Get Templates (Front and Back)
        templates = invoke("modelTemplates", modelName=model_name)
        for card_name, tpl in templates.items():
            # For multi-card models, save as Front_Card1.html or Front.html if only 1 card
            suffix = f"_{clean_folder_name(card_name)}" if len(templates) > 1 else ""
            front_path = os.path.join(model_dir, f"Front{suffix}.html")
            back_path = os.path.join(model_dir, f"Back{suffix}.html")

            with open(front_path, "w", encoding="utf-8") as f:
                f.write(tpl.get("Front", ""))
            with open(back_path, "w", encoding="utf-8") as f:
                f.write(tpl.get("Back", ""))
            print(f"  Saved {card_name}: Front{suffix}.html & Back{suffix}.html")

        # Get Fields & generate sample_data.json
        fields = invoke("modelFieldNames", modelName=model_name)
        sample_path = os.path.join(model_dir, "sample_data.json")
        sample_data = get_sample_data_for_model(model_name, fields)
        with open(sample_path, "w", encoding="utf-8") as f:
            json.dump(sample_data, f, indent=2, ensure_ascii=False)
        print(f"  Saved sample_data.json with {len(fields)} fields.")

    print("\n[OK] All models successfully pulled from Anki!")

if __name__ == "__main__":
    main()
