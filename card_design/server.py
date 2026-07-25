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

            models_data = {}
            for item in os.listdir(BASE_DIR):
                model_dir = os.path.join(BASE_DIR, item)
                if os.path.isdir(model_dir) and not item.startswith("."):
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

        elif self.path == "/" or self.path == "":
            self.path = "/previewer.html"
            
        return super().do_GET()

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
