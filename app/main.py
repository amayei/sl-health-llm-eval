"""Launcher for the SL-Health-LLM-Eval Workbench.

Starts the local server on 127.0.0.1 and opens it in a native window (pywebview) when available,
otherwise in the default browser.
"""
import sys
import threading
import webbrowser

from app.workbench.server import serve


def main():
    wb, httpd = serve()
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    if "--no-window" in sys.argv:
        print(f"Workbench running at {url} (Ctrl+C to stop)")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            return
    try:
        import webview  # type: ignore

        webview.create_window("SL-Health-LLM-Eval Workbench", url, width=1280, height=860, min_size=(900, 600))
        webview.start()
    except Exception:
        webbrowser.open(url)
        print(f"Workbench running at {url}. Close this window to stop it.")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    httpd.shutdown()


if __name__ == "__main__":
    main()
