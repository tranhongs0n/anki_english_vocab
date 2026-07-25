import urllib.request
import json
import os
import sys
import time
import glob

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

def push_model(model_name, model_dir):
    try:
        # 1. Update CSS
        css_path = os.path.join(model_dir, "Styling.css")
        if os.path.exists(css_path):
            with open(css_path, "r", encoding="utf-8") as f:
                css_content = f.read()
            invoke("updateModelStyling", model={"name": model_name, "css": css_content})
            print(f"  [CSS] Updated styling for '{model_name}'")

        # 2. Update Templates
        front_files = sorted(glob.glob(os.path.join(model_dir, "Front*.html")))
        if front_files:
            templates_payload = {}
            for f_path in front_files:
                b_path = f_path.replace("Front", "Back")
                if not os.path.exists(b_path):
                    continue
                
                # Determine card name from filename e.g. Front_Card_1.html -> Card 1, or Front.html -> Card 1
                fname = os.path.basename(f_path)
                if fname == "Front.html":
                    card_name = "Card 1"
                else:
                    # Front_Card_1.html -> Card 1
                    raw_suffix = fname[5:-5].lstrip("_") # remove Front and .html
                    card_name = raw_suffix.replace("_", " ") if raw_suffix else "Card 1"
                
                with open(f_path, "r", encoding="utf-8") as f:
                    front_content = f.read()
                with open(b_path, "r", encoding="utf-8") as f:
                    back_content = f.read()

                templates_payload[card_name] = {
                    "Front": front_content,
                    "Back": back_content
                }

            if templates_payload:
                invoke("updateModelTemplates", model={"name": model_name, "templates": templates_payload})
                print(f"  [Templates] Updated {len(templates_payload)} template(s) for '{model_name}'")
        return True
    except Exception as e:
        print(f"  [Error] Failed to update '{model_name}': {e}")
        return False

def get_dir_mtimes():
    mtimes = {}
    for root, dirs, files in os.walk(BASE_DIR):
        for f in files:
            if f.endswith(".html") or f.endswith(".css"):
                p = os.path.join(root, f)
                try:
                    mtimes[p] = os.path.getmtime(p)
                except Exception:
                    pass
    return mtimes

def main():
    watch_mode = "--watch" in sys.argv or "-w" in sys.argv
    print("Connecting to AnkiConnect...")
    try:
        models = invoke("modelNames")
    except Exception as e:
        print(f"Failed to connect to AnkiConnect: {e}")
        return

    # Create mapping of folder name to actual model name
    model_map = {m.replace("/", "_").replace("\\", "_").replace(":", "_"): m for m in models}

    def run_all_push(silent=False):
        if not silent:
            print("\nPushing local templates to Anki...")
        count = 0
        for item in os.listdir(BASE_DIR):
            model_dir = os.path.join(BASE_DIR, item)
            if os.path.isdir(model_dir) and item in model_map:
                model_name = model_map[item]
                if not silent:
                    print(f"\nPushing '{model_name}'...")
                if push_model(model_name, model_dir):
                    count += 1
        if not silent:
            print(f"\n[OK] Pushed {count} note types to Anki successfully!")

    run_all_push()

    if watch_mode:
        print("\n[WATCH MODE] Watching HTML and CSS files for changes... (Press Ctrl+C to stop)")
        last_mtimes = get_dir_mtimes()
        try:
            while True:
                time.sleep(1)
                cur_mtimes = get_dir_mtimes()
                changed = False
                for p, mt in cur_mtimes.items():
                    if p not in last_mtimes or mt > last_mtimes[p]:
                        print(f"\n[Change Detected] {os.path.basename(p)}")
                        changed = True
                if changed:
                    run_all_push(silent=True)
                    print("  -> Sync to Anki complete at " + time.strftime("%H:%M:%S"))
                last_mtimes = cur_mtimes
        except KeyboardInterrupt:
            print("\n[Watch Mode Stopped]")

if __name__ == "__main__":
    main()
