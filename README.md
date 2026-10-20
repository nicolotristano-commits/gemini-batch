# Gemini batch

Automatizza il chatbot di Gemini (gemini.google.com) dal tuo browser: per ogni richiesta di una lista apre una chat nuova, allega le eventuali immagini, scrive il prompt, aspetta l'immagine generata e la scarica.

Usa il tuo account Gemini normale, senza chiave API.

## Requisiti

- Python 3.9 o successivo
- Google Chrome installato (macOS, Windows o Linux)
- Playwright: `python3 -m pip install -r requirements.txt`

Non serve `playwright install`: lo script usa il tuo Chrome.

## Primo avvio

```bash
python3 gemini_batch.py --login
```

Si apre Chrome con un profilo separato (`profilo_gemini/`). Accedi a Google, apri Gemini, poi premi Invio nel terminale. Lascia Chrome aperto.

Chrome viene aperto in modo normale e lo script si collega dopo, tramite la porta di debug. Se invece fosse lo script ad avviare Chrome, Google rifiuterebbe l'accesso ("Questo browser potrebbe non essere sicuro").

## Esecuzione

```bash
python3 gemini_batch.py esempi/semplice.json
python3 gemini_batch.py esempi/semplice.json --solo gatto     # solo alcune richieste
python3 gemini_batch.py lista.json --uscita immagini --attesa 300 --pausa 20
```

Le immagini vengono salvate in `risultati/<id>.png`. Le richieste già scaricate vengono saltate, quindi se lo script si ferma basta rilanciarlo. Quando qualcosa va storto, una foto dello schermo finisce in `risultati/errori/`.

## Il file delle richieste

```json
{
  "prefisso": "Generate an image:",
  "stile": "Clean black and white line art for a coloring book, square 1:1.",
  "richieste": [
    {"id": "gatto", "prompt": "a cat sleeping on a windowsill."},
    {"id": "foto_1", "prompt": "Redraw this picture as a watercolor.", "immagini": ["immagini/foto_1.png"]}
  ]
}
```

- Ogni richiesta parte in una chat nuova. Il testo inviato è `prefisso + prompt + stile`.
- `immagini` è facoltativo: sono percorsi relativi al file JSON e vengono allegati alla chat.
- `id` diventa il nome del file scaricato.

## Opzioni

| Opzione | Default | Cosa fa |
|---|---|---|
| `--login` | | apre Chrome per accedere a Google |
| `--solo id1,id2` | tutte | esegue solo alcune richieste |
| `--uscita` | `risultati` | cartella delle immagini |
| `--attesa` | 240 | secondi massimi di attesa per ogni immagine |
| `--pausa` | 15 | secondi tra una richiesta e l'altra |
| `--porta` | 9222 | porta di debug di Chrome |
| `--profilo` | `profilo_gemini/` | cartella del profilo Chrome |

Per indicare a mano il percorso di Chrome usa la variabile `GEMINI_CHROME`.

## Note

- Durante l'esecuzione non usare la finestra di Chrome dello script e non mandare il computer in stop.
- Gemini ha un limite giornaliero di immagini: oltre quel limite le richieste falliscono. Riprendi il giorno dopo, lo script salta quelle già fatte.
- L'interfaccia di Gemini cambia nel tempo. I punti più delicati sono `CASELLA`, `RISPOSTA`, `allega()` e `salva()` in `gemini_batch.py`.
- I termini di Google non prevedono l'uso automatico del sito. Usalo con poche richieste e con calma, a tuo rischio.
