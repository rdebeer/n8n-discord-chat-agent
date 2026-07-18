# Transcript Service (yt-dlp + Whisper sidecar for n8n)

Small API that the workflow's `get_video_transcript` tool calls. It downloads a video's audio with **yt-dlp** (YouTube, Facebook, and most other video sites), transcribes it, and returns JSON with the transcript.

## Run it next to n8n (docker-compose)

Add this service to the same `docker-compose.yml` as n8n:

```yaml
  transcript-service:
    build: ./transcript-service
    restart: unless-stopped
    environment:
      - WHISPER_MODEL=base            # tiny | base | small | medium
      - MAX_DURATION_SECONDS=5400     # reject videos longer than 90 min
      # - OPENAI_API_KEY=sk-...       # uncomment to use OpenAI API instead of local whisper
      # - COOKIES_FILE=/data/cookies.txt   # needed for private/login-gated Facebook videos
      # - AUTH_TOKEN=some-shared-secret    # optional request auth
    # volumes:
    #   - ./cookies.txt:/data/cookies.txt:ro
```

`docker compose up -d --build transcript-service`, then check `http://localhost:8000/health` (add `ports: ["8000:8000"]` temporarily if you want to hit it from the host).

## Point the n8n workflow at it

In the **get_video_transcript** tool node, change the URL to:

```
http://transcript-service:8000/transcript?url={video_url}
```

(Containers on the same compose network reach each other by service name — no IP or port mapping needed.)

If you set `AUTH_TOKEN`, also enable "Send Headers" on that tool node and add `X-Auth-Token: <your token>`.

**Important — timeout:** local Whisper on CPU takes roughly 10–25% of the video's length to transcribe (a 20-min video ≈ 2–5 min). In the tool node's **Options**, raise the timeout to e.g. `600000` ms (10 min). If that's too slow for your videos, set `OPENAI_API_KEY` — the API transcribes a 20-min video in ~30 s for about $0.12.

## Model size guidance (local mode)

| Model | Speed (CPU) | Quality | RAM |
|-------|-------------|---------|-----|
| tiny  | fastest     | rough   | ~1 GB |
| base  | fast        | good for clear speech | ~1 GB |
| small | moderate    | noticeably better | ~2 GB |
| medium| slow        | best practical CPU option | ~5 GB |

The model downloads automatically on the first request (so the first call is slow — hit `/transcript` once with a short video to warm it up).

## Facebook notes

- Public Facebook videos usually work out of the box via yt-dlp.
- Private, group, or login-gated videos need cookies: export a `cookies.txt` from your browser (any "cookies.txt" export extension) while logged into Facebook, mount it into the container, and set `COOKIES_FILE`. Refresh it when it expires.
- If a video fails, the service returns a clear 422 error that the AI agent will see and can relay to you in Discord.

## Test it directly

```bash
curl "http://localhost:8000/transcript?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```
