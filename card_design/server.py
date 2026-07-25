import http.server
import socketserver
import json
import os
import glob
import urllib.request

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANKI_CONNECT_URL = "http://127.0.0.1:8765"

def invoke_anki(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    req = urllib.request.Request(ANKI_CONNECT_URL, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if data.get("error"):
            raise Exception(data["error"])
        return data["result"]

class CardDevHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        if self.path == "/api/models":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()

            active_models = set()
            try:
                active_models = set(invoke_anki("modelNames"))
            except Exception:
                pass

            models_data = {}
            for item in os.listdir(BASE_DIR):
                model_dir = os.path.join(BASE_DIR, item)
                if os.path.isdir(model_dir) and not item.startswith(".") and item != "__pycache__":
                    if active_models and item not in active_models:
                        continue
                    css_path = os.path.join(model_dir, "Styling.css")
                    front_path = os.path.join(model_dir, "Front.html")
                    back_path = os.path.join(model_dir, "Back.html")
                    sample_path = os.path.join(model_dir, "sample_data.json")

                    if os.path.exists(css_path) and os.path.exists(front_path):
                        with open(css_path, "r", encoding="utf-8") as f:
                            css = f.read()
                        with open(front_path, "r", encoding="utf-8") as f:
                            front = f.read()
                        back = ""
                        if os.path.exists(back_path):
                            with open(back_path, "r", encoding="utf-8") as f:
                                back = f.read()
                        
                        sample_data = {}
                        if os.path.exists(sample_path):
                            try:
                                with open(sample_path, "r", encoding="utf-8") as f:
                                    sample_data = json.load(f)
                            except Exception:
                                pass

                        models_data[item] = {
                            "css": css,
                            "front": front,
                            "back": back,
                            "sample_data": sample_data
                        }
            
            self.wfile.write(json.dumps({"status": "ok", "models": models_data}, ensure_ascii=False).encode("utf-8"))
            return

        elif self.path == "/api/push":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            try:
                import push_models
                push_models.main()
                res = {"status": "ok", "message": "Successfully pushed all templates to Anki!"}
            except Exception as e:
                res = {"status": "error", "message": str(e)}
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif self.path == "/api/pull":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            try:
                import pull_models
                pull_models.main()
                res = {"status": "ok", "message": "Successfully pulled latest templates from Anki!"}
            except Exception as e:
                res = {"status": "error", "message": str(e)}
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        elif self.path.startswith("/api/real_notes"):
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            try:
                import urllib.parse
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                model_name = params.get("model", [""])[0]
                
                # Try exact match, then wildcard match
                nids_img = []
                try:
                    nids_img = invoke_anki("findNotes", query=f'note:"{model_name}" "Image:*<img*"')
                except Exception:
                    pass
                nids_all = invoke_anki("findNotes", query=f'note:"{model_name}"')
                if not nids_all and " " in model_name:
                    nids_all = invoke_anki("findNotes", query=f'note:*{model_name.split()[0]}*')
                
                nids_no_img = [nid for nid in nids_all if nid not in set(nids_img[:50])][:10]
                nids_img_sample = nids_img[:10]
                
                info_no = invoke_anki("notesInfo", notes=nids_no_img) if nids_no_img else []
                info_img = invoke_anki("notesInfo", notes=nids_img_sample) if nids_img_sample else []
                
                notes_data = []
                max_len = max(len(info_no), len(info_img))
                for i in range(max_len):
                    if i < len(info_no):
                        n = info_no[i]
                        notes_data.append({"noteId": n.get("noteId"), "fields": {k: v.get("value", "") for k, v in n.get("fields", {}).items()}})
                    if i < len(info_img):
                        n = info_img[i]
                        notes_data.append({"noteId": n.get("noteId"), "fields": {k: v.get("value", "") for k, v in n.get("fields", {}).items()}})
                
                res = {"status": "ok", "notes": notes_data, "count": len(notes_data)}
            except Exception as e:
                res = {"status": "error", "message": str(e), "notes": []}
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        elif self.path == "/" or self.path == "":
            self.path = "/previewer.html"
            
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/save_model":
            content_len = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_len).decode("utf-8")
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            try:
                data = json.loads(post_body)
                model_name = data.get("model")
                css = data.get("css")
                front = data.get("front")
                back = data.get("back")
                
                model_dir = os.path.join(BASE_DIR, model_name)
                if os.path.exists(model_dir):
                    if css is not None:
                        with open(os.path.join(model_dir, "Styling.css"), "w", encoding="utf-8") as f:
                            f.write(css)
                        invoke_anki("updateModelStyling", model={"name": model_name, "css": css})
                    
                    if front is not None and back is not None:
                        # Find main card name
                        with open(os.path.join(model_dir, "Front.html"), "w", encoding="utf-8") as f:
                            f.write(front)
                        with open(os.path.join(model_dir, "Back.html"), "w", encoding="utf-8") as f:
                            f.write(back)
                        
                        templates = {"Card 1": {"Front": front, "Back": back}}
                        try:
                            invoke_anki("updateModelTemplates", model={"name": model_name, "templates": templates})
                        except Exception:
                            pass
                            
                res = {"status": "ok", "message": f"Saved and pushed '{model_name}' to disk & Anki!"}
            except Exception as e:
                res = {"status": "error", "message": str(e)}
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

def run():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), CardDevHandler) as httpd:
        print(f"\n[SERVER] Card Dev Server running at: http://localhost:{PORT}")
        print("   Open this URL in your web browser to preview PC, Android, iPhone, and iPad modes!")
        print("   Press Ctrl+C to stop the server.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")

if __name__ == "__main__":
    run()
