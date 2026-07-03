#!/bin/bash
cd "$(dirname "$0")"

# Install deps if missing
python3 -c "import fastapi, uvicorn" 2>/dev/null || pip3 install fastapi uvicorn

echo ""
echo "  ⚡ Quick Tasks rodando em http://localhost:8000"
echo ""
echo "  Para acesso mobile via ngrok:"
echo "    ngrok http 8000"
echo ""

python3 main.py
