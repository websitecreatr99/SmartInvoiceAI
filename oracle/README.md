# InvoiceAI on Oracle Cloud Always Free

The whole stack on one free Ampere A1 VM (arm64, up to 4 OCPU / 24 GB): Caddy (HTTPS) → Next.js frontend,
FastAPI, RabbitMQ and 2 OCR/Gemini workers, all from `docker-compose.yml`. Costs nothing as long as you stay
within Always Free limits; Gemini's free tier covers extraction.

```
Internet ─► Caddy :443 ─┬─► frontend :3000          (frontend branch)
                        └─► /api/jobs* ─► api :5000 (fastapi branch) ─► RabbitMQ ─► worker ×2 (worker branch)
```

## 1. Create the VM (Oracle console)

1. Sign up at cloud.oracle.com (a card is needed for verification; Always Free resources are never charged).
2. **Compute → Instances → Create instance**
   - Image: **Canonical Ubuntu 22.04** (or 24.04)
   - Shape: **Ampere → VM.Standard.A1.Flex**, 4 OCPU, 24 GB memory
   - Networking: create a public subnet, keep **Assign a public IPv4 address** on
   - Add your SSH public key, boot volume 100 GB (up to 200 GB is free)
   - "Out of capacity"? Try another availability domain, fewer OCPUs, or retry later.
3. **Networking → Virtual cloud networks → your VCN → Security Lists → Default** → add ingress rules
   for TCP **80** and **443** from `0.0.0.0/0`.

## 2. Deploy

```bash
ssh ubuntu@<public-ip>
curl -fsSL https://raw.githubusercontent.com/kishannextq/hackathon/infra/oracle/setup.sh | bash
nano ~/invoiceai/infra/oracle/.env        # GOOGLE_API_KEY=... (aistudio.google.com/apikey)
bash ~/invoiceai/infra/oracle/setup.sh    # first build takes ~10-15 min (PaddlePaddle)
```

The script installs Docker, opens 80/443 in the VM's iptables (Oracle's Ubuntu image blocks them), clones the
`fastapi`, `worker`, `frontend` and `infra` branches into `~/invoiceai`, generates a RabbitMQ password and sets
`DOMAIN=<ip-with-dashes>.sslip.io`, so Caddy gets a Let's Encrypt certificate without you buying a domain.
Open `https://<ip-with-dashes>.sslip.io`. To use your own domain, point an A record at the IP and change `DOMAIN`.

If the repository is private, clone with a token first: `REPO=https://<user>:<token>@github.com/kishannextq/hackathon.git bash setup.sh`
(download setup.sh by `scp` instead of `curl`).

## Operate

```bash
cd ~/invoiceai/infra/oracle
bash setup.sh                                  # pull every branch and rebuild
sudo docker compose logs -f worker api         # logs
sudo docker compose up -d --scale worker=3     # more workers
```

- Only Caddy is reachable from the internet. The browser can reach `/api/jobs*` and `/api/health`;
  `/metrics`, `/upload`, `/delete` and the blocking `/process` return 404.
- PDFs travel inline through RabbitMQ (no `STORAGE_BUCKET`), which is fine on one VM; keep `MAX_FILE_MB` modest.
- Job results live in the `storage` volume and survive restarts.
- Oracle reclaims Always Free instances that sit idle (CPU < 20% for 7 days) on free-tier accounts; upgrading
  to Pay As You Go keeps them, and Always Free resources stay free.
