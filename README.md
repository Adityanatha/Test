# Free BDR Pipeline

A self‑contained, free BDR automation system using:
- LinkedIn Sales Navigator (via Playwright)
- HubSpot CRM API
- Open‑source LLM (Hugging Face)
- Streamlit UI dashboard
- Google Sheets for lead storage & reporting

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
5. **Create `config.yaml`** by copying `config.example.yaml` and filling in your own credentials, search URLs, messaging seeds, and Google Sheets settings.
6. **Run the Streamlit dashboard**:
   ```bash
   streamlit run app.py
   ```
   Then click **Login to LinkedIn** in the app and complete authentication before running other tasks.

## Usage

Within the UI, you can:
- Save or update your configuration
- Login to LinkedIn once per session
- Extract leads
- Sync to HubSpot
- Send connection invites
- Process follow-ups
- Push daily reporting metrics
- Monitor pipeline status and lead counts

For automation, schedule individual module scripts under `modules/` via cron or Task Scheduler.

## Google Sheets Setup

1. Create a Google Cloud project and enable the Google Sheets API.
2. Generate a service account and download its credentials JSON file.
3. Share your spreadsheet with the service account email.
4. Set `gsheets.creds_json`, `gsheets.spreadsheet_id`, and the worksheet names (`leads_ws`, `report_ws`) in `config.yaml` accordingly.

## License & Usage

This project is released under the MIT License (see `LICENSE`).
You are responsible for complying with the Terms of Service of LinkedIn, HubSpot, and any other services you connect to, as well as all local regulations.
