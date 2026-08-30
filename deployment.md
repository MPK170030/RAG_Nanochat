# Deployment Guide — nanochat RAG on AWS EC2

This guide takes you from a **fresh AWS account** to a fully deployed app. Follow the steps in order — each one depends on the previous.

## What you're building

```
Your browser → Vercel (React frontend, yourdomain.com)
                  └── POST https://api.yourdomain.com/ask
                            └── EC2 t3.micro (your server running Docker)
                                  └── FastAPI + your RAG pipeline
                                        └── Groq API (external, for the LLM)
```

**Monthly cost: ~$8.50** (EC2 t3.micro + Elastic IP, us-east-1)

---

## Phase 0 — One-Time Setup (do this before anything else)

### 0.1 — Create an AWS account

1. Go to [aws.amazon.com](https://aws.amazon.com) → **Create an AWS Account**
2. Enter your email, choose a root account password, and pick an account name (e.g. `manav-projects`)
3. Enter payment info — AWS needs a card on file even for free-tier use
4. Complete phone verification
5. Choose the **Basic (free) support plan**
6. Sign in to the **AWS Management Console** at [console.aws.amazon.com](https://console.aws.amazon.com)

> **Important:** The account you just created is called the "root user". AWS recommends not using it day-to-day. For this guide, you can use it — but never share those credentials.

### 0.2 — Set a billing alert (do this now, before spending anything)

You want to know immediately if costs spike unexpectedly. Set this up first.

1. In the AWS Console, search for **"Billing"** in the top search bar → open it
2. Go to **Billing Preferences** (left sidebar)
3. Enable both:
   - **"Receive AWS Free Tier Alerts"**
   - **"Receive Billing Alerts"**
4. Save preferences
5. Now search for **"Budgets"** → **Create budget**
6. Choose **"Monthly cost budget"** → Next
7. Set budget amount to **$15** (gives you a buffer above the ~$8.50 baseline)
8. Under **"Alert threshold"**, enter `80` (percent) and your email address
9. Create budget

> If you accidentally leave an idle Elastic IP unattached, AWS charges ~$3.60/month for it. This alert will catch that.

### 0.3 — Install tools on your local machine

You need two tools installed locally before continuing.

**Docker Desktop**
- Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
- Install it and make sure it's running (you'll see the Docker whale icon in your taskbar)
- Verify: open a terminal and run `docker --version`

**AWS CLI**
- Download from [docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- Install it, then verify: `aws --version`

### 0.4 — Create an IAM user and configure the AWS CLI

The AWS CLI needs credentials to talk to your account. You'll create a dedicated user for this.

1. In the AWS Console, search for **"IAM"** → open it
2. Go to **Users → Create user**
3. Username: `nanochat-deploy` → Next
4. Choose **"Attach policies directly"** → search for and attach:
   - `AmazonEC2FullAccess`
   - `AmazonECRFullAccess`
   - `AmazonSSMFullAccess`
   - `IAMFullAccess`
   - `AWSBudgetsFullAccess`
5. Create user
6. Click into the new user → **Security credentials** tab → **Create access key**
7. Choose **"Command Line Interface (CLI)"** → Next → Create
8. **Copy both the Access Key ID and Secret Access Key** — you won't be able to see the secret again

Now configure the CLI on your machine:

```bash
aws configure
```

It will prompt for four values:

```
AWS Access Key ID:     [paste your access key]
AWS Secret Access Key: [paste your secret key]
Default region name:   us-east-1
Default output format: json
```

Verify it works:
```bash
aws sts get-caller-identity
```
You should see your account ID printed. If you get an error, double-check your credentials.

---

## Phase 1 — AWS Infrastructure

### Step 1 — Create an IAM Role for the EC2 Instance

**What this is:** Your EC2 server needs permission to do two things — read your API key from AWS's secret store, and accept shell connections via the browser. An IAM "role" is how you grant those permissions to a server (as opposed to an IAM "user" which is for people).

1. In IAM → **Roles → Create role**
2. **Trusted entity type:** AWS service → EC2 → Next
3. Search for and attach both policies:
   - `AmazonSSMManagedInstanceCore` — lets you open a terminal into the server from your browser (no SSH needed)
   - `AmazonSSMReadOnlyAccess` — lets the server read your secret API key
4. Name: `nanochat-rag-role` → Create role

### Step 2 — Store your Groq API key securely

**What this is:** Instead of putting your API key in a file on the server (where it could leak), you'll store it in AWS Parameter Store — an encrypted secrets vault. The server will fetch it at startup using the role you just created.

1. Search for **"Systems Manager"** → open it
2. In the left sidebar → **Parameter Store → Create parameter**
3. Settings:
   - **Name:** `/nanochat-rag/groq-api-key`
   - **Type:** `SecureString` (this encrypts it at rest)
   - **Value:** your actual Groq API key (starts with `gsk_...`)
4. Create parameter

### Step 3 — Create the EC2 Instance

**What this is:** EC2 is AWS's virtual server service. You're renting a small Linux computer in a data center to run your app 24/7.

1. Search for **"EC2"** → open it → **Launch Instance**
2. Fill in the settings:
   - **Name:** `nanochat-rag`
   - **AMI (operating system):** Amazon Linux 2023 (64-bit x86) — this is the default, just make sure it's selected
   - **Instance type:** `t3.micro` (1 vCPU, 1 GB RAM — enough for this app)
   - **Key pair:** Click "Create new key pair" → name it `nanochat-key` → Create. This downloads a `.pem` file — **save it somewhere you won't lose it** (e.g. `~/Downloads/nanochat-key.pem`). You won't need it if you use Session Manager, but it's good to have as a backup.
   - **Network settings:** Click "Edit" → under "Firewall (security groups)", create a new security group with these inbound rules:

     | Type  | Port | Source    | Why |
     |-------|------|-----------|-----|
     | SSH   | 22   | My IP     | Emergency backup access (optional) |
     | HTTP  | 80   | 0.0.0.0/0 | Required for SSL certificate setup |
     | HTTPS | 443  | 0.0.0.0/0 | Your API traffic |

   - **Storage:** 20 GB gp3 (the default 8 GB is too small for Docker images)
   - **Advanced details → IAM instance profile:** select `nanochat-rag-role`

3. Click **Launch instance**
4. Wait about 2 minutes for the instance to reach "running" state (refresh the Instances page)

### Step 4 — Allocate a Static IP Address (Elastic IP)

**What this is:** By default, your server's IP address changes every time it restarts. An Elastic IP is a static IP that stays the same — you need this so your domain always points to the right place.

1. In EC2 → left sidebar → **Elastic IPs → Allocate Elastic IP address → Allocate**
2. Select the new IP that appears → **Actions → Associate Elastic IP address**
3. Under "Instance", select your `nanochat-rag` instance → Associate
4. **Write down the IP address** — you'll need it in the next step

### Step 5 — Connect to Your Server

Now that the instance exists, you can open a terminal into it. There are two ways:

**Option A — Session Manager (recommended, works from any network):**

No `.pem` file needed, no open port 22 required — it tunnels through HTTPS.

```bash
# Find your instance ID
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=nanochat-rag" \
  --query "Reservations[0].Instances[0].InstanceId" \
  --output text

# Open a shell (replace i-xxxx with the ID above)
aws ssm start-session --target i-xxxx --region us-east-1
```

Or from the browser: **EC2 → Instances → nanochat-rag → Connect → Session Manager → Connect**

**Option B — SSH (if you kept port 22 open):**

```bash
chmod 400 ~/Downloads/nanochat-key.pem
ssh -i ~/Downloads/nanochat-key.pem ec2-user@<your-Elastic-IP>
```

Either way, you should see a prompt like `[ec2-user@ip-xxx ~]$` — you're now inside your server.

### Step 6 — Install Software on the Server

Run these commands inside the server shell from Step 5:

```bash
# Update the system
sudo dnf update -y

# Install Docker
sudo dnf install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

# Install Nginx (the web server that sits in front of your app)
sudo dnf install -y nginx
sudo systemctl enable --now nginx

# Install Certbot (for free HTTPS certificates)
sudo dnf install -y certbot python3-certbot-nginx

# Install the AWS CLI (to pull Docker images and read secrets)
sudo dnf install -y awscli
```

> After running `usermod`, log out and reconnect — the Docker group change only takes effect in a new session.

Reconnect (repeat Step 5), then verify Docker works without `sudo`:
```bash
docker ps
```

### Step 7 — Authenticate Docker to ECR from the Server

**What this is:** ECR (Elastic Container Registry) is AWS's private Docker image storage. Your server needs to log in to pull images from it. Because the server has the IAM role from Step 1, it can authenticate automatically — no passwords needed.

On the server, run (replace `123456789012` with your AWS account ID — find it at the top-right of the AWS Console):

```bash
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com
```

You should see `Login Succeeded`.

---

## Phase 2 — Build and Deploy the Application

Run these steps **on your local machine** (not the server).

### Step 8 — Update CORS in api.py

Open `api.py` and update the `allow_origins` list to include your production domain:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://yourdomain.com",
        "https://www.yourdomain.com",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

Replace `yourdomain.com` with your actual domain.

### Step 9 — Verify requirements.txt

The `requirements.txt` should contain exactly what the app needs at runtime:

```
fastapi
uvicorn[standard]
python-dotenv
pydantic
groq
sentence-transformers
chromadb
```

If it's missing or outdated, regenerate it from your venv and trim to just these packages.

### Step 10 — Create the ECR Repository and Push the Docker Image

**What this is:** You'll build a Docker image of your app locally and push it to ECR, so your server can pull and run it.

```bash
# Create the ECR repository (one-time — skip if it already exists)
aws ecr create-repository --repository-name nanochat-rag --region us-east-1

# Log Docker in to ECR from your local machine
# Replace 123456789012 with your AWS account ID
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com

# Build the image (run from the project root — the folder with Dockerfile)
docker build -t nanochat-rag .

# Tag the image with the ECR address
docker tag nanochat-rag:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/nanochat-rag:latest

# Push it
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/nanochat-rag:latest
```

The push will take a few minutes the first time (the image is large due to `sentence-transformers`).

### Step 11 — Create the Startup Script on the Server

Connect to your server again (Step 5), then create this script:

```bash
cat > /home/ec2-user/start.sh << 'EOF'
#!/bin/bash
set -e

# Fetch the API key from Parameter Store (uses the IAM role — no hardcoded credentials)
GROQ_API_KEY=$(aws ssm get-parameter \
  --name /nanochat-rag/groq-api-key \
  --with-decryption \
  --query Parameter.Value \
  --output text \
  --region us-east-1)

# Stop and remove the old container if it's running
docker stop nanochat-rag 2>/dev/null || true
docker rm nanochat-rag 2>/dev/null || true

# Pull the latest image from ECR
docker pull 123456789012.dkr.ecr.us-east-1.amazonaws.com/nanochat-rag:latest

# Start the container
docker run -d \
  --name nanochat-rag \
  --restart unless-stopped \
  -e GROQ_API_KEY="$GROQ_API_KEY" \
  -p 8000:8000 \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/nanochat-rag:latest
EOF

chmod +x /home/ec2-user/start.sh
```

Run it:

```bash
./start.sh
```

Check it started correctly:

```bash
curl http://localhost:8000/health
```

You should get a `{"status": "ok"}` response (or similar). If you get "connection refused", wait 10 seconds and try again — the container may still be starting.

---

## Phase 3 — Domain and HTTPS

### Step 12 — Point Your Domain to the Server

**What this is:** You need `api.yourdomain.com` to resolve to your server's IP. You'll add a DNS record in Vercel's dashboard.

1. Go to your Vercel dashboard → your domain → **DNS**
2. Add a record:

   | Type | Name  | Value                     |
   |------|-------|---------------------------|
   | A    | `api` | `<your Elastic IP from Step 4>` |

3. Save. DNS propagation takes **5–30 minutes**.

To check if it's propagated yet, run this on your local machine:

```bash
nslookup api.yourdomain.com
```

When it returns your Elastic IP, you're ready for the next step. Don't continue until it does.

### Step 13 — Configure Nginx

**What this is:** Your app runs on port 8000 inside Docker, but web traffic comes in on port 80/443. Nginx is a reverse proxy — it receives the traffic and forwards it to your app.

On the server, create the config file:

```bash
sudo tee /etc/nginx/conf.d/nanochat.conf << 'EOF'
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass         http://localhost:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 60s;
    }
}
EOF
```

Replace `api.yourdomain.com` with your actual subdomain. Test and apply the config:

```bash
sudo nginx -t          # should print "syntax is ok" and "test is successful"
sudo systemctl reload nginx
```

Quick test — from your local machine:

```bash
curl http://api.yourdomain.com/health
```

You should get a response from your app over plain HTTP. Next step upgrades it to HTTPS.

### Step 14 — Enable HTTPS with a Free Certificate

**What this is:** Certbot gets a free TLS certificate from Let's Encrypt and configures Nginx to use it automatically. DNS must be working (Step 12) before this step.

On the server:

```bash
sudo certbot --nginx -d api.yourdomain.com
```

Follow the prompts — it will ask for your email and ask you to agree to terms. When it finishes, Nginx is automatically updated to redirect HTTP → HTTPS and serve your certificate.

Verify it works:

```bash
curl https://api.yourdomain.com/health
```

Certbot sets up auto-renewal via a cron job — your certificate renews every 90 days without any action from you.

---

## Phase 4 — Frontend

### Step 15 — Deploy the Frontend to Vercel

On your local machine, update the API URL in `frontend/src/App.tsx`:

```ts
const API_URL = 'https://api.yourdomain.com/ask'
```

Then push to GitHub — Vercel will auto-deploy if you've connected the repo.

If you haven't connected it yet:

```bash
cd frontend
npx vercel --prod
```

Follow the prompts. Vercel will give you a URL like `https://your-app.vercel.app`. You can also add your custom domain from the Vercel dashboard.

Test the full flow end-to-end: open the Vercel URL in your browser, ask a question, and verify you get an answer.

---

## Updating After Code Changes

When you make changes to the backend:

```bash
# On your local machine — rebuild and push
docker build -t nanochat-rag .
docker tag nanochat-rag:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/nanochat-rag:latest
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/nanochat-rag:latest

# On the server — pull the new image and restart
aws ssm start-session --target <instance-id> --region us-east-1
# then inside the session:
./start.sh
```

When you make changes to the frontend, just push to GitHub — Vercel redeploys automatically.

---

## Cost Breakdown

| Service              | Details                                          | $/month   |
|----------------------|--------------------------------------------------|-----------|
| EC2 t3.micro         | 730 hrs, us-east-1                               | ~$8.35    |
| Elastic IP           | Free while attached to a running instance        | $0.00     |
| ECR                  | First 500 MB free, then $0.10/GB                 | ~$0.10    |
| SSM Parameter Store  | Standard parameters are free                     | $0.00     |
| Data transfer        | First 100 GB/month free                          | ~$0.00    |
| **Total**            |                                                  | **~$8.50**|

> If you stop the instance but leave the Elastic IP allocated (not released), AWS charges ~$3.60/month for the idle IP. Either release it or terminate the instance when not in use.

---

## AWS Services Glossary

| Service | What it is |
|---------|------------|
| **EC2** | A virtual Linux server you rent by the hour |
| **Elastic IP** | A static IP address that stays the same across reboots |
| **IAM Role** | A set of permissions you attach to a server (not a person) |
| **IAM User** | A set of credentials for a person or CLI tool |
| **ECR** | A private registry that stores your Docker images |
| **SSM Parameter Store** | An encrypted vault for secrets like API keys |
| **SSM Session Manager** | A way to open a terminal into your server via HTTPS (no SSH port needed) |
| **Nginx** | A web server that forwards traffic from port 443 to your app |
| **Certbot / Let's Encrypt** | Free tool that gets and renews TLS certificates automatically |
