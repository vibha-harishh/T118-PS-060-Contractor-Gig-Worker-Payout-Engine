-- ==============================================================================
-- Schema for T118-PS-060: Contractor & Gig-Worker Payout Engine
-- Module: Member 1 (Payout and Earnings Module)
-- Database Engine: SQLite 3.10+
-- Financial Standard: All monetary amounts are stored as INTEGER PAISE (₹1 = 100 paise)
-- Timezone Standard: All event timestamps and weekly cycles are in Asia/Kolkata (IST)
-- ==============================================================================

PRAGMA foreign_keys = ON;

-- 1. Delivery / Gig Partners Table
CREATE TABLE IF NOT EXISTS partners (
    partner_id TEXT PRIMARY KEY,
    partner_name TEXT NOT NULL,
    partner_type TEXT NOT NULL CHECK (partner_type IN ('INDIVIDUAL', 'FIRM')),
    pan TEXT,                                       -- Nullable: PAN is not mandatory for initial registration
    pan_status TEXT NOT NULL DEFAULT 'MISSING' CHECK (pan_status IN ('VALID', 'INVALID', 'MISSING')),
    category TEXT NOT NULL CHECK (category IN ('DELIVERY', 'SERVICE_PROFESSIONAL')),
    phone TEXT,
    bank_account_number TEXT,                       -- Nullable: Bank details can be provided/verified later
    ifsc_code TEXT,
    bank_verification_status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        bank_verification_status IN ('VERIFIED', 'UNVERIFIED', 'FAILED', 'PENDING')
    ),
    city TEXT DEFAULT 'Bangalore',
    rating REAL DEFAULT 5.0 CHECK (rating IS NULL OR (rating >= 1.0 AND rating <= 5.0)),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED')),
    bag_deduction_balance_paise INTEGER NOT NULL DEFAULT 180000 CHECK (bag_deduction_balance_paise >= 0), -- Initial loan ₹1,800 = 180,000 paise
    onboarding_date DATE NOT NULL,                  -- Date of partner onboarding (YYYY-MM-DD)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- PAN Consistency Constraint:
    -- If MISSING, pan must be NULL; if VALID or INVALID, pan must be provided (NOT NULL).
    CONSTRAINT chk_pan_consistency CHECK (
        (pan_status = 'MISSING' AND pan IS NULL) OR
        (pan_status IN ('VALID', 'INVALID') AND pan IS NOT NULL)
    )
);

-- Partial index: PAN is unique across registered partners when provided (allows multiple NULLs)
CREATE UNIQUE INDEX IF NOT EXISTS idx_partners_pan ON partners(pan) WHERE pan IS NOT NULL;

-- 2. Delivery / Gig Tasks Table (Unambiguous event_type, Distance, Slot, Weather Surge, Rating)
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    partner_id TEXT NOT NULL,
    task_type TEXT NOT NULL DEFAULT 'DELIVERY' CHECK (task_type IN ('DELIVERY', 'SERVICE')),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'TASK_COMPLETED',                  -- Completed task: base pay * surge multiplier
        'CUSTOMER_CANCELLED_POST_PICKUP',  -- Cancelled after pickup: ₹20 flat (2,000 paise)
        'CUSTOMER_CANCELLED_PRE_PICKUP',   -- Cancelled before pickup: ₹0 pay
        'PARTNER_CANCELLED'                -- Cancelled by partner: ₹0 pay, penalty applies
    )),
    distance_km REAL NOT NULL DEFAULT 0.0 CHECK (distance_km >= 0.0),
    duration_minutes REAL DEFAULT 0.0 CHECK (duration_minutes >= 0.0),
    slot_type TEXT DEFAULT 'REGULAR',                   -- e.g. 'LUNCH_PEAK', 'DINNER_PEAK', 'REGULAR'
    is_slot_surge INTEGER NOT NULL DEFAULT 0 CHECK (is_slot_surge IN (0, 1)),
    is_rain_surge INTEGER NOT NULL DEFAULT 0 CHECK (is_rain_surge IN (0, 1)),
    rating REAL CHECK (rating IS NULL OR (rating >= 1.0 AND rating <= 5.0)),
    cancellation_reason TEXT,
    base_pay_paise INTEGER NOT NULL DEFAULT 0 CHECK (base_pay_paise >= 0),
    surge_multiplier REAL NOT NULL DEFAULT 1.0 CHECK (surge_multiplier IN (1.0, 1.3, 1.5)),
    final_task_pay_paise INTEGER NOT NULL DEFAULT 0 CHECK (final_task_pay_paise >= 0),
    task_timestamp TIMESTAMP NOT NULL,                  -- Precise event timestamp in IST
    task_date DATE NOT NULL,                            -- Event date in IST (YYYY-MM-DD)
    week_identifier TEXT NOT NULL,                      -- ISO week in IST, e.g. '2026-W45'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (partner_id) REFERENCES partners(partner_id) ON DELETE CASCADE
);

-- 3. Customer Complaints Table (for Verified Complaints Penalty: ₹200 / 20,000 paise each)
CREATE TABLE IF NOT EXISTS complaints (
    complaint_id TEXT PRIMARY KEY,
    partner_id TEXT NOT NULL,
    week_identifier TEXT NOT NULL,                      -- ISO week in IST, e.g. '2026-W45'
    is_verified INTEGER NOT NULL DEFAULT 1 CHECK (is_verified IN (0, 1)),
    complaint_date DATE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (partner_id) REFERENCES partners(partner_id) ON DELETE CASCADE
);

-- 4. Weekly Payout & Earnings Summary Table (before TDS handover to Member 2)
CREATE TABLE IF NOT EXISTS weekly_earnings (
    earnings_id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_id TEXT NOT NULL,
    week_identifier TEXT NOT NULL,                      -- ISO week in IST, e.g. '2026-W45'
    total_tasks_assigned INTEGER NOT NULL DEFAULT 0 CHECK (total_tasks_assigned >= 0),
    completed_tasks INTEGER NOT NULL DEFAULT 0 CHECK (completed_tasks >= 0),
    partner_cancellations INTEGER NOT NULL DEFAULT 0 CHECK (partner_cancellations >= 0),
    cancellation_rate REAL NOT NULL DEFAULT 0.0 CHECK (cancellation_rate >= 0.0 AND cancellation_rate <= 1.0),
    average_rating REAL NOT NULL DEFAULT 5.0 CHECK (average_rating >= 1.0 AND average_rating <= 5.0),
    gross_task_pay_paise INTEGER NOT NULL DEFAULT 0 CHECK (gross_task_pay_paise >= 0),
    incentive_amount_paise INTEGER NOT NULL DEFAULT 0 CHECK (incentive_amount_paise >= 0),
    incentive_forfeited INTEGER NOT NULL DEFAULT 0 CHECK (incentive_forfeited IN (0, 1)),
    gross_weekly_earnings_paise INTEGER NOT NULL DEFAULT 0 CHECK (gross_weekly_earnings_paise >= 0),
    raw_cancellation_penalty_paise INTEGER NOT NULL DEFAULT 0 CHECK (raw_cancellation_penalty_paise >= 0),
    raw_complaint_penalty_paise INTEGER NOT NULL DEFAULT 0 CHECK (raw_complaint_penalty_paise >= 0),
    raw_total_penalties_paise INTEGER NOT NULL DEFAULT 0 CHECK (raw_total_penalties_paise >= 0),
    capped_total_penalties_paise INTEGER NOT NULL DEFAULT 0 CHECK (capped_total_penalties_paise >= 0),
    net_before_bag_deduction_paise INTEGER NOT NULL DEFAULT 0,
    bag_deduction_applied_paise INTEGER NOT NULL DEFAULT 0 CHECK (bag_deduction_applied_paise >= 0),
    bag_deduction_paused INTEGER NOT NULL DEFAULT 0 CHECK (bag_deduction_paused IN (0, 1)),
    remaining_bag_balance_paise INTEGER NOT NULL DEFAULT 0 CHECK (remaining_bag_balance_paise >= 0),
    net_payable_before_tds_paise INTEGER NOT NULL DEFAULT 0, -- Member 1 final output handed over to Member 2
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (partner_id) REFERENCES partners(partner_id) ON DELETE CASCADE,
    UNIQUE (partner_id, week_identifier)
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_partner_id ON tasks(partner_id);
CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(task_date);
CREATE INDEX IF NOT EXISTS idx_tasks_week_partner ON tasks(partner_id, week_identifier);
CREATE INDEX IF NOT EXISTS idx_tasks_timestamp ON tasks(task_timestamp);
CREATE INDEX IF NOT EXISTS idx_complaints_partner_week ON complaints(partner_id, week_identifier);
CREATE INDEX IF NOT EXISTS idx_weekly_partner_week ON weekly_earnings(partner_id, week_identifier);
