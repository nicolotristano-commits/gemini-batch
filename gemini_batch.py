#!/usr/bin/env python3
"""Gemini batch: manda una serie di richieste al chatbot di Gemini (gemini.google.com)
dal tuo browser, una chat nuova per ogni richiesta, e scarica le immagini generate.

Le richieste stanno in un file JSON (vedi esempi/). Uso:
    python3 gemini_batch.py --login                         # la prima volta: accedi a Google
    python3 gemini_batch.py esempi/semplice.json            # esegue tutte le richieste
    python3 gemini_batch.py esempi/semplice.json --solo gatto,casa

Chrome viene aperto in modo normale con un profilo separato (cartella profilo_gemini/)
e lo script si collega tramite la porta di debug, così Google accetta l'accesso.
"""
import argparse, base64, json, os, platform, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

QUI = Path(__file__).resolve().parent
URL = os.environ.get("GEMINI_URL", "https://gemini.google.com/app")
CASELLA = 'rich-textarea div[contenteditable="true"], div[contenteditable="true"][role="textbox"]'
RISPOSTA = "model-response"


def trova_chrome():
    if os.environ.get("GEMINI_CHROME"):
        return os.environ["GEMINI_CHROME"]
    candidati = {
        "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        "Windows": [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")],
    }.get(platform.system(), [])
    candidati += [shutil.which(n) or "" for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")]
    for c in candidati:
        if c and Path(c).exists():
            return c
    sys.exit("Non trovo Google Chrome: indica il percorso con la variabile GEMINI_CHROME.")


def chrome_attivo(porta):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        opener.open(f"http://127.0.0.1:{porta}/json/version", timeout=2)
        return True
    except Exception:
        return False


def apri_chrome(porta, profilo):
    if chrome_attivo(porta):
        return
    subprocess.Popen([trova_chrome(), f"--remote-debugging-port={porta}", f"--user-data-dir={profilo}",
                      "--no-first-run", "--no-default-browser-check",
                      # continua a disegnare la pagina anche con la finestra ridotta a icona o coperta
                      "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows", URL],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        if chrome_attivo(porta):
            return
        time.sleep(1)
    sys.exit("Chrome non risponde sulla porta di debug: chiudi le finestre aperte con questo profilo e riprova.")


def carica_richieste(file):
    """File JSON: {"stile": "...", "prefisso": "...", "richieste": [{"id", "prompt", "immagini"}]}.
    Il prompt finale è: prefisso + prompt + stile. Le immagini sono percorsi relativi al file."""
    dati = json.load(open(file, encoding="utf-8"))
    base = Path(file).resolve().parent
    out = []
    for r in dati["richieste"]:
        testo = " ".join(x for x in (dati.get("prefisso", ""), r["prompt"], dati.get("stile", "")) if x)
        imgs = [base / i for i in r.get("immagini", [])]
        for i in imgs:
            if not i.exists():
                sys.exit(f"Immagine non trovata per '{r['id']}': {i}")
        out.append({"id": str(r["id"]), "prompt": testo, "immagini": imgs})
    return out


def allega(page, files):
    inp = page.locator('input[type="file"]')
    if inp.count():
        inp.first.set_input_files([str(f) for f in files])
    else:
        page.get_by_role("button", name=re.compile(r"caricamento|carica|upload|aggiungi|add", re.I)).first.click()
        with page.expect_file_chooser(timeout=15000) as fc:
            page.get_by_role("menuitem", name=re.compile(r"carica|upload|file", re.I)).first.click()
        fc.value.set_files([str(f) for f in files])
    page.wait_for_timeout(3000 + 1000 * len(files))


def immagine_pronta(page, attesa):
    fine = time.time() + attesa
    while time.time() < fine:
        imgs = page.locator(f"{RISPOSTA} img")
        for i in range(imgs.count() - 1, -1, -1):
            img = imgs.nth(i)
            try:
                w = img.evaluate("e => e.complete ? e.naturalWidth : 0")
            except Exception:
                w = 0
            if w >= 512:
                return img
        page.wait_for_timeout(3000)
    raise TimeoutError("nessuna immagine generata entro il tempo di attesa")


def salva(page, ctx, img, dest):
    risposta = page.locator(RISPOSTA).last
    img.hover()
    pulsante = risposta.get_by_role("button", name=re.compile(r"scarica|download", re.I))
    if pulsante.count():
        try:
            with page.expect_download(timeout=20000) as dl:
                pulsante.first.click()
            dl.value.save_as(str(dest))
            return "scaricata"
        except Exception:
            pass
    src = img.get_attribute("src") or ""
    if src.startswith("http"):
        r = ctx.request.get(src)
        if r.ok:
            dest.write_bytes(r.body())
            return "salvata dall'indirizzo"
    if src.startswith(("blob:", "data:")):
        b64 = page.evaluate(
            """async s => { const b = await (await fetch(s)).blob();
                 return await new Promise(r => { const f = new FileReader();
                 f.onload = () => r(f.result.split(',')[1]); f.readAsDataURL(b); }); }""",
            src,
        )
        dest.write_bytes(base64.b64decode(b64))
        return "salvata dalla pagina"
    img.screenshot(path=str(dest))
    return "salvata come foto (qualità più bassa)"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("richieste", nargs="?", help="file JSON con le richieste")
    ap.add_argument("--login", action="store_true", help="apre Chrome per accedere a Google")
    ap.add_argument("--solo", help="id separati da virgola")
    ap.add_argument("--uscita", default="risultati", help="cartella delle immagini (default: risultati)")
    ap.add_argument("--attesa", type=int, default=240, help="secondi massimi per ogni immagine")
    ap.add_argument("--pausa", type=int, default=15, help="secondi tra una richiesta e l'altra")
    ap.add_argument("--porta", type=int, default=9222)
    ap.add_argument("--profilo", default=str(QUI / "profilo_gemini"))
    a = ap.parse_args()

    apri_chrome(a.porta, a.profilo)
    if a.login:
        input("Nella finestra di Chrome accedi a Google e apri Gemini, poi premi Invio qui... ")
        print("Accesso salvato. Lascia Chrome aperto e lancia lo script con il file delle richieste.")
        return
    if not a.richieste:
        ap.error("indica il file JSON delle richieste")

    richieste = carica_richieste(a.richieste)
    if a.solo:
        scelte = {s.strip() for s in a.solo.split(",")}
        richieste = [r for r in richieste if r["id"] in scelte]
    out = Path(a.uscita)
    err = out / "errori"
    err.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{a.porta}")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        for r in richieste:
            dest = out / f"{r['id']}.png"
            if dest.exists():
                print(f"{dest.name}: già presente, salto")
                continue
            print(f"{r['id']}...", flush=True)
            try:
                page.bring_to_front()
                page.goto(URL)  # chat nuova
                casella = page.locator(CASELLA).first
                casella.wait_for(timeout=60000)
                if r["immagini"]:
                    allega(page, r["immagini"])
                casella.click()
                casella.fill(r["prompt"])
                page.wait_for_timeout(1000)
                page.keyboard.press("Enter")
                img = immagine_pronta(page, a.attesa)
                page.wait_for_timeout(3000)
                print("   ", salva(page, ctx, img, dest), "->", dest)
            except Exception as e:
                foto = err / f"{r['id']}_{int(time.time())}.png"
                try:
                    page.screenshot(path=str(foto), timeout=10000)
                except Exception:
                    pass
                print(f"   errore: {e}\n   foto dello schermo in {foto}")
                if "closed" in str(e).lower():
                    sys.exit("La finestra di Chrome è stata chiusa: mi fermo.")
            page.wait_for_timeout(a.pausa * 1000)
        page.close()
    print("Fatto. Le immagini sono in", out)


if __name__ == "__main__":
    main()
