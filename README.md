# T118-PS-060: Contractor & Gig-Worker Payout Engine

## Project Overview

The Contractor & Gig-Worker Payout Engine is a Python-based backend application designed to automate weekly earnings calculation and settlements for gig workers and delivery partners.

The system calculates task-based earnings, weekly incentives, penalties, equipment deductions, and Tax Deducted at Source (TDS). It also manages partner registration, bank settlements, payment holds, reversals, and financial ledger records.

The project aims to ensure accurate, transparent, and reliable payout processing for gig workforce platforms.

## Problem Statement

**PS-060 – Contractor and Gig-Worker Payout Engine with TDS and Weekly Settlement**

Gig platforms manage thousands of delivery partners and service professionals. Manually calculating their weekly earnings, incentives, deductions, taxes, and settlements can lead to errors and delays.

This project provides an automated backend engine to handle these financial operations efficiently while following the specified business rules.

## Objectives

- Automate weekly payout calculations.
- Register and manage gig partners.
- Calculate earnings based on completed tasks and distance.
- Apply incentives, penalties, and deductions.
- Calculate TDS under Sections 194C, 194J, and 194-O according to configured business rules.
- Manage bank settlements, payment holds, and reversals.
- Maintain partner-wise financial ledgers.
- Generate weekly payout statements and quarterly TDS summaries.

## Key Features

### 1. Partner Registration
- Register individual and firm partners.
- Maintain PAN verification status.
- Manage contractor categories.
- Store bank verification details.
- Maintain partner onboarding information.

### 2. Task and Earnings Management
- Process completed and cancelled task events.
- Calculate base pay based on distance.
- Apply surge and rain-day multipliers.
- Calculate task-level earnings.

### 3. Weekly Incentive and Penalty Calculation
- Calculate incentives based on weekly completed tasks.
- Apply cancellation-rate and rating conditions.
- Calculate cancellation penalties.
- Apply verified customer complaint deductions.
- Enforce weekly penalty limits.

### 4. TDS Calculation
- Support Sections 194C, 194J, and 194-O.
- Apply the relevant tax rates and thresholds.
- Handle PAN-related tax rules.
- Maintain cumulative financial-year TDS records.

### 5. Weekly Settlement
- Generate weekly payout batches every Monday.
- Process bank verification and payment holds.
- Handle bank-return reversals.
- Manage settlement retries.
- Apply minimum payout and carry-forward rules.

### 6. Financial Ledger and Reports
- Maintain partner-wise earnings and deductions.
- Track earned, withheld, paid, and recovered amounts.
- Generate weekly payout statements.
- Generate quarterly TDS summaries.

## Technology Stack

- **Programming Language:** Python 3.10+
- **Database:** SQLite
- **Database Language:** SQL
- **Testing:** Python unittest
- **Development Environment:** Visual Studio Code
- **Version Control:** Git and GitHub

## Project Structure

```text
T118-PS-060/
│
├── database/
│   ├── __init__.py
│   ├── db.py
│   └── schema.sql
│
├── src/
│   ├── __init__.py
│   ├── ingestion/
│   ├── payouts/
│   ├── settlements/
│   ├── tds/
│   └── reports/
│
├── tests/
│
├── README.md
├── requirements.txt
└── main.py
```

*Note: The directory structure represents the intended project organization and may be updated as development progresses.*

## Installation and Setup

### Step 1: Clone the Repository

```bash
git clone <your-repository-url>
```

### Step 2: Navigate to the Project Directory

```bash
cd T118-PS-060
```

### Step 3: Create a Virtual Environment

```bash
python3 -m venv .venv
```

### Step 4: Activate the Virtual Environment

For macOS/Linux:

```bash
source .venv/bin/activate
```

For Windows:

```bash
.venv\Scripts\activate
```

### Step 5: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 6: Run the Application

```bash
python main.py
```

## Testing

Run the unit tests using:

```bash
python -m unittest discover -s tests -v
```

## Expected Outputs

The system is designed to generate:

- Partner registration details.
- Task-wise earnings.
- Weekly payout statements.
- Incentive and penalty calculations.
- TDS deductions and section details.
- Settlement batch summaries.
- Bank hold and reversal information.
- Quarterly TDS reports.

## Business Rules

The application implements the specified business rules covering:

- Task-based payment calculation.
- Surge and rain-day incentives.
- Weekly incentive eligibility.
- Cancellation and complaint penalties.
- Equipment deductions.
- TDS section selection and thresholds.
- PAN verification and payment holds.
- Weekly settlement and bank reversals.
- Minimum payout and carry-forward.
- Manual adjustment limits.
- IST-based weekly task attribution.

## Project Information

| Field | Details |
|---|---|
| Project ID | T118-PS-060 |
| Problem Statement | PS-060 |
| Project Title | Contractor & Gig-Worker Payout Engine |
| Domain | Enterprise – Gig Workforce Payments |
| Programming Language | Python 3.10+ |
| Database | SQLite |
| Difficulty | High |

## Contributors

Developed as an academic team project.

**Repository:** T118-PS-060 – Contractor & Gig-Worker Payout Engine

---

*This project is developed for academic purposes to demonstrate backend development, database management, financial calculations, automated settlements, and software testing.*
