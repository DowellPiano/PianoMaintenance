#!/bin/bash

echo "🛑 Stopping any running servers..."
lsof -ti :8000 | xargs kill -9 2>/dev/null && echo "  Django (port 8000) stopped." || echo "  No Django server running."
lsof -ti :5173 | xargs kill -9 2>/dev/null && echo "  React (port 5173) stopped." || echo "  No React server running."

echo ""
echo "🚀 Starting servers..."

# Start Django
cd /Users/tom/Desktop/Limble\ Clone && source venv/bin/activate && python manage.py runserver > /tmp/django.log 2>&1 &
echo "  Django starting on http://localhost:8000"

# Start React
cd /Users/tom/Desktop/Limble\ Clone/frontend && npm run dev > /tmp/react.log 2>&1 &
echo "  React starting on http://localhost:5173"

echo ""
echo "⏳ Waiting for servers to come up..."
sleep 4

# Verify
DJANGO_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/)
REACT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/)

echo ""
echo "✅ Status Check:"
[ "$DJANGO_STATUS" != "000" ] && echo "  Django → http://localhost:8000 (HTTP $DJANGO_STATUS)" || echo "  ❌ Django failed to start — check /tmp/django.log"
[ "$REACT_STATUS"  != "000" ] && echo "  React  → http://localhost:5173 (HTTP $REACT_STATUS)"  || echo "  ❌ React failed to start — check /tmp/react.log"
