#!/usr/bin/env bash
# Recording day: fresh demo data, then the API (:8000) and dashboard (:3000). Ctrl+C stops both.
# Uses backend/data/demo.db, so your normal data in alaap.db is never touched.
set -e
cd "$(dirname "$0")"
export DATABASE_URL="sqlite:///$(pwd)/backend/data/demo.db"
( cd backend && ../.venv/bin/python -m alaap.admin demo-reset )
( cd backend && ../.venv/bin/uvicorn alaap.api.main:app --port 8000 ) &
API=$!
( cd dashboard && rm -rf .next && npx next dev -p 3000 ) &
DASH=$!
trap 'kill $API $DASH 2>/dev/null' EXIT INT TERM
echo "Demo running: http://localhost:3000/welcome  (owner: owner@glow.demo / demo1234, team: http://localhost:3000/ops)"
wait
