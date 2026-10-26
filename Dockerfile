FROM python:3.12-slim

LABEL org.opencontainers.image.title="Kardo" \
      org.opencontainers.image.source="https://github.com/Echosky/kardo" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.description="Self-hosted spaced-repetition flashcards that import Anki decks"

ENV PORT=8484 KARDO_DATA=/data PYTHONUNBUFFERED=1
WORKDIR /app
COPY server.py lab.py lab_exercises.txt /app/
COPY static /app/static
RUN mkdir -p /data && chown -R 99:100 /data

# Unraid's nobody:users, so files in appdata stay editable from the share
USER 99:100
VOLUME /data
EXPOSE 8484
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/api/health')"
CMD ["python", "/app/server.py"]
