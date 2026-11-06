# InvoiceAI for free: Vercel + Hugging Face Spaces

> **Note:** Hugging Face Docker Spaces now need a paid plan, so this bundle no longer runs for free. The free deployment in use is the `lite` branch on Render (see its README).

```
Browser ─► Vercel (frontend branch, Next.js)
   └─────► https://<user>-<space>.hf.space  ── one free HF Space (2 vCPU / 16 GB):
                                               RabbitMQ + API (fastapi branch) + worker (worker branch)
                                               └─► Gemini API (free tier)
```

Why one Space instead of separate services: Spaces only allow outbound connections on ports 80, 443 and 8080,
so they can't reach a hosted RabbitMQ (CloudAMQP listens on 5671). Running the broker in the same container
also removes the need for object storage: files travel inline through the local broker.

## 1. Backend on Hugging Face

1. Create a Space at huggingface.co/new-space: **SDK: Docker**, blank template, hardware **CPU basic (free)**.
2. In the Space's **Settings → Variables and secrets**:
   - New secret `GOOGLE_API_KEY` = your Gemini key (aistudio.google.com/apikey)
   - New variable `CORS_ORIGINS` = your Vercel URL (set it after step 2, e.g. `https://invoiceai.vercel.app`;
     several are comma-separated)
3. Create a **write** token at huggingface.co/settings/tokens, then from the repo root (Git Bash):
   ```bash
   HF_TOKEN=hf_xxx HF_SPACE=<user>/<space> bash huggingface/deploy.sh
   ```
   The first build takes ~10 minutes (PaddlePaddle). Check `https://<user>-<space>.hf.space/health`.
   The first PDF is slower too: PaddleOCR downloads its models on first use.

`deploy.sh` copies only the code files from `origin/fastapi` and `origin/worker` (push those branches first)
plus [space/](space/) and force-pushes them to the Space. Re-run it after changing either branch.

## 2. Frontend on Vercel

1. vercel.com → **Add New → Project** → import `kishannextq/hackathon`.
2. **Settings → Git → Production Branch**: `frontend`. Framework preset: Next.js (auto-detected).
3. **Settings → Environment Variables**: `NEXT_PUBLIC_API_URL` = `https://<user>-<space>.hf.space`
4. Deploy, then put the Vercel URL into the Space's `CORS_ORIGINS` variable (the Space restarts).

## Limits of the free setup

- The Space sleeps after 48 h without visits; the next request wakes it, which takes a minute or two.
  Jobs and queued messages live on the container's disk and are lost when it restarts or sleeps.
- One worker on 2 vCPUs: documents are processed one at a time.
- The whole API is public on the Space URL, including `/metrics` and the blocking `/process`.
- Gemini free tier rate limits apply; the worker retries 429s.
