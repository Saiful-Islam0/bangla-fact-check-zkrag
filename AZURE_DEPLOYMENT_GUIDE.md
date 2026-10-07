# ☁️ Microsoft Azure Deployment Guide: ZK-RAG Fact-Checking & Blockchain Anchor Stack

This guide details how to deploy the complete Bengali Fake News Detection System—including the Multi-Agent LLM pipeline, Zero-Knowledge cryptographic verification, and on-chain EVM blockchain anchoring—to a **Microsoft Azure Linux Virtual Machine**.

---

## 🏛️ System Architecture in Docker

The entire stack is containerized into two high-performance cooperating microservices managed by `docker-compose.yml`:

```
                       +---------------------------------------+
                       |      Internet / Examiner Browser      |
                       +-------------------+-------------------+
                                           | HTTP Port 80 / 8000
                                           v
                       +---------------------------------------+
                       |          Container 1: `app`           |
                       |  - FastAPI Backend (Python 3.11)      |
                       |  - Bengali Multi-Agent LLM (Groq)     |
                       |  - SnarkJS & Circom ZK Prover         |
                       |  - EasyOCR Bengali Text Recognition   |
                       |  - Serves React SPA directly (/dist)  |
                       +-------------------+-------------------+
                                           | HTTP Port 8787 (Internal Docker Network)
                                           v
                       +---------------------------------------+
                       |        Container 2: `anchor`          |
                       |  - Node.js 20 Express Bridge (:8787)  |
                       |  - Hardhat Local EVM Node (:8545)     |
                       |  - VerificationRecordAnchor.sol       |
                       |    (Auto-deployed on startup)         |
                       +---------------------------------------+
```

---

## 📋 Step 1: Provision the Azure Linux Virtual Machine

1. Log in to the [Azure Portal](https://portal.azure.com/).
2. Click **Create a resource** -> **Virtual Machine**.
3. Fill in the VM configuration:
   - **Subscription & Resource Group**: Select or create a new resource group (e.g., `rg-bangla-factcheck`).
   - **Virtual machine name**: e.g., `vm-factcheck-prod`
   - **Region**: Choose a region close to your target audience (e.g., `Southeast Asia`, `Central India`, or `East US`).
   - **Image**: **Ubuntu Server 22.04 LTS - x64 Gen2** or **Ubuntu Server 24.04 LTS**.
   - **Size**:
     - *Budget / Testing*: **Standard_B2s** (2 vCPUs, 4 GiB memory). *(Our setup script automatically enables a 4GB swapfile so memory spikes during PyTorch/OCR model loading run smoothly).*
     - *Recommended Production / Thesis Defense*: **Standard_D2s_v5** (2 vCPUs, 8 GiB memory) or **Standard_D4s_v5** (4 vCPUs, 16 GiB memory).
   - **Authentication type**: **SSH public key** (recommended) or Password.
   - **Username**: `azureuser` (or your chosen username).
4. Under **Inbound port rules**:
   - Allow **SSH (22)**, **HTTP (80)**, and **HTTPS (443)**.
5. In the **Networking** tab:
   - Under **Network Security Group (NSG)**, click **Advanced** or create a security rule:
     - Add Inbound Rule:
       - **Destination Port**: `8000`
       - **Protocol**: `TCP`
       - **Action**: `Allow`
       - **Name**: `Allow-FastAPI-8000`
6. Click **Review + create**, then click **Create**. Note down your **Public IP address** once provisioned.

---

## 🚀 Step 2: One-Command Server Setup

1. Connect to your Azure VM via SSH from your computer terminal:
   ```bash
   ssh -i /path/to/your/ssh_key azureuser@<AZURE_VM_PUBLIC_IP>
   ```

2. Clone or copy your project repository to the VM:
   ```bash
   git clone <YOUR_GIT_REPO_URL>
   cd "Fake_news_detection-main 2"
   ```
   *(Or transfer the folder using SFTP / `rsync -avz ./ azureuser@<AZURE_VM_PUBLIC_IP>:~/factcheck/`)*

3. Run the automated server initialization script:
   ```bash
   chmod +x setup_azure_vm.sh
   sudo ./setup_azure_vm.sh
   ```
   *This script automatically updates Ubuntu, creates and activates a 4GB swap space (preventing RAM exhaustion), installs Docker & the Docker Compose plugin, configures systemctl, and opens UFW ports 22, 80, 443, and 8000.*

4. Refresh your shell groups to use Docker without `sudo`:
   ```bash
   newgrp docker
   ```

---

## ⚙️ Step 3: Configure Environment Variables

1. Copy `.env.example` to `.env` (or verify your existing `.env`):
   ```bash
   cp .env.example .env
   nano .env
   ```

2. Ensure the required API keys are configured:
   ```env
   GROQ_API_KEY=gsk_...
   SERP_DEV_API_KEY=e5f98...
   IMGBB_API_KEY=625c6...
   SIGHTENGINE_API_USER=189373161
   SIGHTENGINE_API_SECRET=NrS5Y...

   # Docker internal anchor bridge routing
   ZKRAG_ANCHOR_BRIDGE_URL=http://anchor:8787
   ZKRAG_ANCHOR_TIMEOUT_SECONDS=15
   ```

---

## 🚢 Step 4: Build & Launch with Docker Compose

Launch the entire stack in detached background mode:
```bash
docker compose up --build -d
```

### What happens automatically:
1. Docker builds the `anchor` image: compiles `VerificationRecordAnchor.sol`, starts the local EVM blockchain (chain ID 31337), deploys the anchor contract, and launches the Express bridge on port `8787`.
2. Docker builds the `app` image: builds the Vite React frontend into `/dist`, installs PyTorch CPU + OCR system packages, compiles Circom ZK circuits, and launches FastAPI on port `8000` (mapped to port `80` and `8000`).

To monitor the startup logs:
```bash
docker compose logs -f
```
Press `Ctrl+C` to exit log viewing (containers remain running in the background).

---

## ✅ Step 5: Verify Deployment & On-Chain Anchoring

### 1. Test Bridge & Blockchain Health
From your VM terminal:
```bash
curl -s http://localhost:8787/health
```
**Expected response:**
```json
{"ok":true,"chain_id":"31337","contract_address":"0x5FbDB2315678afecb367f032d93F642f64180aa3"}
```

### 2. Test FastAPI Backend Health
```bash
curl -s http://localhost:8000/api/health
```

### 3. Open in Your Web Browser
Open your browser and navigate to:
```
http://<AZURE_VM_PUBLIC_IP>
```
*(or `http://<AZURE_VM_PUBLIC_IP>:8000`)*

1. Submit a Bengali news claim (e.g. `পদ্মা সেতুতে রেল চলাচল শুরু হয়েছে`).
2. After the multi-agent LLM analysis completes, scroll to the **ZK Cryptographic Proof & Input Binding** card.
3. You will see:
   - Status: **`• Anchor: anchored`** (green badge)
   - Badge: **`Local EVM`**
   - Transaction hash: `TX: 0x...`
   - Block details: `Chain: 31337 · Block: <block_number>`
   - Contract address: `Contract: 0x5FbDB2315678afecb367f032d93F642f64180aa3`
   - Button: **`Anchored`**

---

## 🌐 Step 6: Switching to Public Ethereum Sepolia (Optional)

If you wish to anchor claims to the public Ethereum Sepolia testnet so that examiners can click and inspect transactions directly on [Sepolia Etherscan](https://sepolia.etherscan.io/):

1. Edit `.env`:
   ```env
   ZKRAG_EVM_RPC_URL=https://rpc.sepolia.org
   ZKRAG_ANCHOR_CONTRACT_ADDRESS=0x<Your_Deployed_Sepolia_Contract>
   ZKRAG_ANCHOR_PRIVATE_KEY=0x<Your_Sepolia_Wallet_Private_Key>
   ZKRAG_ANCHOR_CONFIRMATIONS=1
   ```
2. Restart the containers:
   ```bash
   docker compose down
   docker compose up -d
   ```
The frontend UI will automatically display a **`Sepolia Testnet`** badge with direct clickable links to `sepolia.etherscan.io/tx/0x...`.

---

## 🔒 Step 7: Custom Domain & Free SSL HTTPS (Recommended)

To assign a custom domain name (e.g. `factcheck.yourdomain.com`) with automated free HTTPS / SSL:

### Option A: Using Caddy (Easiest, zero-config SSL)
1. Install Caddy on Ubuntu:
   ```bash
   sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
   curl -1sLF 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
   curl -1sLF 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
   sudo apt-get update
   sudo apt-get install caddy
   ```
2. In `/etc/caddy/Caddyfile`:
   ```caddy
   factcheck.yourdomain.com {
       reverse_proxy 127.0.0.1:8000
   }
   ```
3. Restart Caddy:
   ```bash
   sudo systemctl restart caddy
   ```
Caddy will automatically obtain and renew a Let's Encrypt SSL certificate!

---

## 🛠️ Operations & Maintenance Cheat Sheet

| Task | Command |
|---|---|
| View real-time logs | `docker compose logs -f` |
| View backend logs only | `docker compose logs -f app` |
| View blockchain logs only | `docker compose logs -f anchor` |
| Restart all services | `docker compose restart` |
| Stop all services | `docker compose down` |
| Rebuild after code updates | `docker compose up --build -d` |
| Check memory & disk usage | `docker stats --no-stream` |
| Backup claim metadata | `docker cp $(docker compose ps -q app):/app/claim_metadata ./backup_claims` |
