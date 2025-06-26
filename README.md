# Free BDR Pipeline

A self‑contained, free BDR automation system using:
- LinkedIn Sales Navigator (via Playwright)
- HubSpot CRM API
- Open‑source LLM (Hugging Face)
- Streamlit UI dashboard
- SQLite for local state & reporting

## Setup

1. **Download or copy the project to your local machine**:
   ```bash
   cd /path/to/free-bdr-pipeline
   ```
2. **(Optional) Initialize Git**:
   ```bash
   git init
   git add .
   git commit -m "Initial scaffold of free BDR pipeline"
   # Later, you can add a remote:
   # git remote add origin git@github.com:<your-org>/free-bdr-pipeline.git
   # git push -u origin main
   ```
3. **Create & activate a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # mac/linux
   venv\Scripts\activate    # windows
   ```
4. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   playwright install
   ```
5. **Initialize the SQLite database**:
   ```bash
   python init_db.py
   ```
6. **Configure `config.yaml`** with your LinkedIn, HubSpot, and Hugging Face credentials, search URLs, and messaging seeds.
7. **Run the Streamlit dashboard**:
   ```bash
   streamlit run app.py
   ```

## Usage

Within the UI, you can:
- Save or update your configuration
- Extract leads
- Sync to HubSpot
- Send connection invites
- Process follow-ups
- Push daily reporting metrics
- Monitor pipeline status and lead counts

For automation, schedule individual module scripts under `modules/` via cron or Task Scheduler.
