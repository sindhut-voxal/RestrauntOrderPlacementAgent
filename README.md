# End-to-end web food-ordering voice agent

Browser-only Pipecat agent: order food by voice, collect pickup or delivery details, mock-pay, and persist an order ID. No phone/Twilio and no real payments.

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash
pip install -r server/requirements.txt
cp server/.env.example server/.env
# Fill GOOGLE_API_KEY and DEEPGRAM_API_KEY
# Keep GOOGLE_MODEL=gemini-2.5-flash (tool calling)

cd frontend
npm install
npm run build
cd ..
```

## Run

```bash
cd server
python bot.py
```

Open http://localhost:7860/app/

Frontend dev (hot reload, proxies the bot):

```bash
cd frontend
npm run dev
```

Then start `python bot.py` in `server/` and open http://localhost:5173/app/

## Tests

```bash
pytest
```
