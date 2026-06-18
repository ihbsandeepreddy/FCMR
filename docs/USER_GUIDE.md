# User Guide — SanGir Automations

Welcome to SanGir Automations, a deterministic audit analytics tool for NBFC loan portfolios.

## Installation

1. **Download** the latest installer from [https://github.com/ihbsandeepreddy/sangir-releases/releases](https://github.com/ihbsandeepreddy/sangir-releases/releases)
2. **Run** `SAND-Setup-<version>.exe`
3. Follow the installer steps
4. **Launch** from your Start Menu or Desktop shortcut

## Data Storage

All your data is stored locally in:

```
C:\Users\<YourName>\AppData\Local\SanGirAutomations\data\
```

This means:

- ✅ **No data is sent to the cloud**
- ✅ **Your data persists across app updates**
- ✅ **You control backups**

## Workflow

### 1. Create an Engagement

An engagement is an audit job — one per client, period, or project.

- Click **Engagements** in the sidebar
- Click **New Engagement**
- Fill in the details (name, client name, period)
- Click **Open Engagement** to activate it

### 2. Upload Your Data

Select your CSV files (customer master, collection, disbursement, etc.).

- Click **New Upload**
- Select **Report Type** (must match your CSV structure)
- Drag and drop or browse for files
- Click **Upload & Continue**

### 3. Map Columns

Match your CSV headers to standard fields.

- The app auto-suggests matches with **confidence %**
- Review the suggestions (green = auto-mapped)
- Adjust manually if needed (dropdown **Map To**)
- Already-mapped fields are hidden from other dropdowns
- Click **Confirm Mapping & Ingest**

The app streams your file to a local Parquet format for fast analysis.

### 4. Run Analytics

Analytics runs 27 deterministic validation rules:

- **KYC format**: PAN, Aadhaar, Voter ID, Passport, DL, mobile, email, DOB
- **PIN & address**: Existence, state/district match, completeness
- **Duplicates**: PAN, Aadhaar, mobile, bank, voter ID, address, name+DOB
- **UCID**: Union-find grouping and KYC consistency checks
- **Data quality**: Email domain, age range, bank account length

To run:

- Click **Run** on a ready upload
- Watch the progress (auto-refreshes every 4 seconds)

### 5. Review Results

Once complete:

- **Donut chart**: Status breakdown (OK, WARN, ERROR)
- **Bar chart**: Top exception codes by frequency
- **Exception table**: Detailed breakdown with categories
- **Print / PDF**: Export via browser print

### 6. Download Reports

Three output formats:

1. **Audit Workpaper (.xlsx)**
   - Lead sheet (executive summary)
   - Detailed exceptions (all records)
   - TOC/TOD (test of controls with sampling)
   - Methodology (deterministic sampling approach)

2. **Wide CSV**
   - One row per customer
   - All exceptions in one line (pipe-delimited)

3. **Long CSV**
   - One row per exception
   - Useful for filtering and pivot tables

## Settings

### Fuzzy Match Threshold

Controls how strict column name matching is:

- **0.5**: More lenient (e.g., "customer name" → "full_name")
- **0.6**: Default (e.g., "cust_id" → "customer_id")
- **0.8**: Strict (e.g., "PAN" → "pan" only)

Adjust if auto-mapping misses your column names.

### Backup Your Data

Click **Download Backup** to create a `.zip` of:

- Your catalog (audit history)
- All generated reports
- Session credentials (for restore)

**Best practice**: Download a backup monthly.

## Privacy & Security

- **Aadhaar**: Displayed as `XXXXXXXX1234` (last 4 digits only)
- **PAN**: Never persisted in full; only hashed for duplicate detection
- **All data**: Stays on your machine; no uploads to cloud
- **Logs**: Stored locally in `data/logs/` with no sensitive details

## Auto-Update

The app checks for updates every 12 hours. If a new version is available:

1. A notification appears
2. Click **Restart Now** to install
3. App updates on next launch
4. Your data is not affected

To disable auto-update, edit `.env` in your data folder:

```
AUTO_UPDATE_ENABLED=false
```

## Troubleshooting

### App won't start

- Check `data/logs/app.log` for errors
- Ensure Windows admin rights (if installed to Program Files)
- Restart your computer

### Backend won't respond

- Close the app completely
- Wait 10 seconds
- Reopen

### Upload stuck on "Mapping Pending"

- Click **Map Columns** to retry
- If headers aren't recognized, adjust the fuzzy threshold in **Settings**

### Out of disk space

- Delete old backups from `data/backups/`
- Remove old engagement outputs from `data/outputs/`

### Need to reinstall

- Your data is safe in `C:\Users\<YourName>\AppData\Local\SanGirAutomations\data\`
- Uninstall and reinstall the app
- Data will be preserved

## Getting Help

- **Logs**: Check `data/logs/error.log` for detailed error messages
- **Bug report**: Open an issue at [https://github.com/ihbsandeepreddy/FCMR/issues](https://github.com/ihbsandeepreddy/FCMR/issues)
- **Feature request**: Same GitHub issues page

---

**Questions?** Reach out to [ihbsandeepreddy@gmail.com](mailto:ihbsandeepreddy@gmail.com).
