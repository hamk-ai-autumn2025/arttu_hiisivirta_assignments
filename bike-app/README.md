# Pyöräsuositussovellus (Prototype)

Tämä on AI-pohjainen pyöräsuositussovellus, joka ehdottaa maantie- tai gravel-pyöriä käyttäjän antamien kriteerien perusteella.

## 🧠 Toiminnallisuus
- Käyttäjä kuvaa tarpeensa vapaamuotoisesti (esim. budjetti, käyttötarkoitus, pituus).
- Backend tulkitsee tekstin, muodostaa vektorikyselyn ja hakee sopivimmat pyörät tietokannasta.
- Tulokset näytetään siistissä korttinäkymässä.

## 🛠️ Teknologiat
- **Backend:** FastAPI, PostgreSQL + pgvector, OpenAI Embeddings
- **Frontend:** Next.js, React, Tailwind CSS
- **Muut:** Docker (PostgreSQL), Python venv

## 🚀 Käynnistys (kehitystilassa)
```bash
# Backend
cd api
source .venv/bin/activate
uvicorn app:app --reload

# Frontend
cd web
npm install
npm run dev

