# ruff: noqa: E501
"""Seed the demo catalog (idempotent) — one property per ownership model.

Migrates the content that used to live in the frontend mock file
(src/data/sampleProperties.ts) into real ``properties`` rows with status
``active`` so the marketplace + model pages render live DB data at launch and
existing demo deep-links keep working. Re-running is safe: rows are matched by
slug and skipped if already present.

Usage:
    python scripts/seed_properties.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
from decimal import Decimal

from sqlalchemy import select

from app.core.db import session_scope
from app.models import Property, PropertyMilestone
from app.models.base import MilestoneStatus, PropertyStatus
from app.services.milestone_service import timeline_to_milestone_rows

_BASE_DOCS = [
    {"name": "Subscription Agreement", "type": "PDF", "size": "1.2 MB"},
    {"name": "SPV Articles", "type": "PDF", "size": "880 KB"},
    {"name": "Independent Valuation", "type": "PDF", "size": "2.4 MB"},
    {"name": "Risk Disclosure", "type": "PDF", "size": "640 KB"},
]

# Each entry mirrors the old SampleProperty objects 1:1. Scalar columns are split
# out; the rich/model-specific fields live in ``content`` (the JSONB the frontend
# adapter reconstructs into its SampleProperty shape).
# fmt: off
SAMPLES: list[dict] = [
    {
        "slug": "demo-ready-income-marina-loft",
        "model": "ready-income",
        "property_type": "apartment",
        "title": "Sample • Marina Loft Income Suite",
        "subtitle": "Fully leased 1-bedroom apartment generating monthly rental income",
        "location": "Dubai Marina, UAE",
        "country": "UAE",
        "city": "Dubai",
        "total_value": 1450000,
        "minimum_investment": 100,
        "expected_yield": 8.4,
        "capital_appreciation": 4.8,
        "total_return": 13.2,
        "funding_progress": 62,
        "investors_count": 218,
        "description": (
            "Educational sample of a ready, fully leased income-producing apartment. "
            "Investors purchase fractional ownership through the SPV and receive monthly "
            "net rental distributions plus long-term capital appreciation."
        ),
        "images": [
            "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=1200&auto=format&fit=crop&q=80",
            "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=1200&auto=format&fit=crop&q=80",
        ],
        "content": {
            "badge": "Ready • Income Generating",
            "badgeTone": "ready",
            "developer": {"name": "Elite Gate Properties", "rating": 4.7, "projectsCompleted": 42},
            "ownershipStructure": [
                {"label": "Ownership Vehicle", "value": "DIFC SPV"},
                {"label": "Token Standard", "value": "Fractional Equity Units"},
                {"label": "Income Type", "value": "Monthly Net Rental + Appreciation"},
                {"label": "Custody", "value": "Independent Trustee"},
            ],
            "investmentStructure": [
                {"label": "Min. Ticket", "value": "$100"},
                {"label": "Distribution Frequency", "value": "Monthly"},
                {"label": "Holding Period", "value": "Open-ended"},
                {"label": "Lock-up", "value": "None (secondary market)"},
            ],
            "timeline": [
                {"label": "Listed", "date": "Today", "progress": 100, "valueIndex": 100, "status": "done"},
                {"label": "Funding Closes", "date": "+30d", "progress": 62, "valueIndex": 100, "status": "active"},
                {"label": "First Distribution", "date": "+60d", "progress": 0, "valueIndex": 102, "status": "upcoming"},
                {"label": "Annual Revaluation", "date": "+12m", "progress": 0, "valueIndex": 105, "status": "upcoming"},
            ],
            "scenarios": [
                {"label": "Base case", "outcome": "8.4% yield + 4.8% appreciation = 13.2% total", "tone": "positive"},
                {"label": "Vacancy 1 month", "outcome": "~7.7% yield + appreciation", "tone": "neutral"},
                {"label": "Market downturn", "outcome": "Income unaffected, NAV may dip 3–6%", "tone": "negative"},
            ],
            "exitMechanisms": [
                {"name": "Secondary Market", "description": "List units to other investors at market price.", "eta": "1–7 days"},
                {"name": "Liquidity Provider", "description": "Instant exit at a small discount.", "eta": "Same day"},
            ],
            "risks": [
                {"label": "Vacancy", "level": "low", "note": "Leased to long-term tenant, 12-month contract."},
                {"label": "Liquidity", "level": "low", "note": "Active secondary market."},
                {"label": "Market", "level": "medium", "note": "Subject to property cycle."},
            ],
            "documents": _BASE_DOCS,
            "marketAnalysis": [
                {"label": "Avg. Rent (1BR Marina)", "value": "$2,850 / mo"},
                {"label": "Occupancy Rate", "value": "94%"},
                {"label": "12m Price Δ", "value": "+5.6%"},
            ],
        },
    },
    {
        "slug": "demo-installment-creek-tower",
        "model": "installment",
        "property_type": "apartment",
        "title": "Sample • Creek Tower Installment Suite",
        "subtitle": "Pay in monthly installments while the property is built",
        "location": "Dubai Creek Harbour, UAE",
        "country": "UAE",
        "city": "Dubai",
        "total_value": 2100000,
        "minimum_investment": 100,
        "capital_appreciation": 18,
        "funding_progress": 41,
        "investors_count": 134,
        "description": (
            "Educational sample of an installment-based ownership. Investors commit to a "
            "payment schedule aligned with construction milestones. Ownership vests "
            "progressively until handover."
        ),
        "images": ["https://images.unsplash.com/photo-1486325212027-8081e485255e?w=1200&auto=format&fit=crop&q=80"],
        "content": {
            "badge": "Under Construction • Installment",
            "badgeTone": "installment",
            "developer": {"name": "Capimax Development", "rating": 4.6, "projectsCompleted": 28},
            "ownershipStructure": [
                {"label": "Ownership Vehicle", "value": "DIFC SPV"},
                {"label": "Vesting", "value": "Progressive — per installment"},
                {"label": "Title Transfer", "value": "On full settlement"},
            ],
            "investmentStructure": [
                {"label": "Down Payment", "value": "20%"},
                {"label": "Installment Plan", "value": "24 months"},
                {"label": "Monthly Payment", "value": "$66.67 per $100 unit"},
                {"label": "Final Settlement", "value": "On handover"},
            ],
            "installmentTerms": {
                "downPayment": "20% upfront",
                "months": 24,
                "monthly": "Equal monthly payments tracked on-chain",
                "completionUnlock": "Full ownership at handover, then yield begins",
            },
            "timeline": [
                {"label": "Down Payment", "date": "Today", "progress": 100, "valueIndex": 100, "status": "done"},
                {"label": "Foundation", "date": "+6m", "progress": 25, "valueIndex": 105, "status": "active"},
                {"label": "Structure", "date": "+14m", "progress": 60, "valueIndex": 115, "status": "upcoming"},
                {"label": "Handover", "date": "+24m", "progress": 100, "valueIndex": 130, "status": "upcoming"},
            ],
            "scenarios": [
                {"label": "On-time delivery", "outcome": "Capital appreciation ~18% by handover", "tone": "positive"},
                {"label": "3-month delay", "outcome": "Schedule extended, no extra cost to investor", "tone": "neutral"},
                {"label": "Project default", "outcome": "Escrow returns paid installments minus fees", "tone": "negative"},
            ],
            "exitMechanisms": [
                {"name": "Transfer Installment", "description": "Sell remaining position to another investor.", "eta": "3–10 days"},
                {"name": "Secondary Market", "description": "Unit-level resale post-handover.", "eta": "Post-delivery"},
            ],
            "risks": [
                {"label": "Construction delay", "level": "medium", "note": "Mitigated by escrow + milestone audits."},
                {"label": "Payment default", "level": "medium", "note": "Position can be re-listed; partial recovery."},
                {"label": "Market", "level": "medium", "note": "Appreciation linked to delivery cycle."},
            ],
            "documents": _BASE_DOCS,
            "marketAnalysis": [
                {"label": "Off-plan vs. ready spread", "value": "−22%"},
                {"label": "Area pipeline", "value": "12 active towers"},
            ],
        },
    },
    {
        "slug": "demo-future-business-bay",
        "model": "future",
        "property_type": "apartment",
        "title": "Sample • Business Bay Future Tower",
        "subtitle": "Lock today's price, settle at delivery — capture full appreciation",
        "location": "Business Bay, UAE",
        "country": "UAE",
        "city": "Dubai",
        "total_value": 3200000,
        "minimum_investment": 250,
        "capital_appreciation": 22,
        "funding_progress": 28,
        "investors_count": 76,
        "description": (
            "Educational sample of a future-based agreement. The investor signs a forward "
            "purchase contract at today's price, with settlement at a future delivery date. "
            "Appreciation between today and settlement accrues to the holder."
        ),
        "images": ["https://images.unsplash.com/photo-1497366216548-37526070297c?w=1200&auto=format&fit=crop&q=80"],
        "content": {
            "badge": "Future Model",
            "badgeTone": "future",
            "developer": {"name": "TDH Development", "rating": 4.5, "projectsCompleted": 31},
            "ownershipStructure": [
                {"label": "Instrument", "value": "Forward Purchase Agreement"},
                {"label": "Settlement", "value": "Cash or Unit Delivery"},
                {"label": "Custodian", "value": "Independent Trustee"},
            ],
            "investmentStructure": [
                {"label": "Reservation", "value": "10% of forward value"},
                {"label": "Settlement Date", "value": "T + 24 months"},
                {"label": "Locked-in Price", "value": "$1,000 / sqft"},
            ],
            "futureTerms": {
                "settlementDate": "24 months from listing",
                "futurePrice": "$1,000 / sqft locked today",
                "appreciationProjection": "Projected delivery price: $1,220 / sqft (+22%)",
                "constructionMilestoneImpact": (
                    "NAV steps up at each milestone (foundation +5%, structure +12%, "
                    "fit-out +18%, handover +22%)."
                ),
            },
            "timeline": [
                {"label": "Forward signed", "date": "Today", "progress": 100, "valueIndex": 100, "status": "done"},
                {"label": "Foundation", "date": "+6m", "progress": 25, "valueIndex": 105, "status": "active"},
                {"label": "Structure", "date": "+14m", "progress": 60, "valueIndex": 112, "status": "upcoming"},
                {"label": "Settlement", "date": "+24m", "progress": 100, "valueIndex": 122, "status": "upcoming"},
            ],
            "scenarios": [
                {"label": "Delivery as planned", "outcome": "Settle at $1,000, market at $1,220 → +22%", "tone": "positive"},
                {"label": "Flat market", "outcome": "Break-even, settle and hold for rental income", "tone": "neutral"},
                {"label": "Market down 10%", "outcome": "Settlement obligation remains; loss until recovery", "tone": "negative"},
            ],
            "exitMechanisms": [
                {"name": "Secondary Market", "description": "Assign forward contract to another investor.", "eta": "5–14 days"},
                {"name": "Liquidity Provider", "description": "Discounted instant assignment.", "eta": "Same day"},
            ],
            "risks": [
                {"label": "Settlement obligation", "level": "high", "note": "Investor must fund or assign before delivery."},
                {"label": "Market volatility", "level": "medium", "note": "Appreciation not guaranteed."},
                {"label": "Construction risk", "level": "medium", "note": "Milestone audits and escrow mitigate."},
            ],
            "documents": _BASE_DOCS,
            "marketAnalysis": [
                {"label": "5y CAGR (Business Bay)", "value": "+7.2%"},
                {"label": "Forward discount today", "value": "−18%"},
            ],
        },
    },
    {
        "slug": "demo-option-palm-residences",
        "model": "option",
        "property_type": "villa",
        "title": "Sample • Palm Residences Option Position",
        "subtitle": "Pay an option premium today, decide whether to activate later",
        "location": "Palm Jumeirah, UAE",
        "country": "UAE",
        "city": "Dubai",
        "total_value": 4800000,
        "minimum_investment": 500,
        "capital_appreciation": 35,
        "funding_progress": 19,
        "investors_count": 48,
        "description": (
            "Educational sample of an option-based position. The investor pays a small "
            "option premium that locks in the right — but not the obligation — to acquire "
            "the underlying unit at a fixed strike price before a deadline."
        ),
        "images": ["https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=1200&auto=format&fit=crop&q=80"],
        "content": {
            "badge": "Option Model",
            "badgeTone": "option",
            "developer": {"name": "Capimax Development", "rating": 4.6, "projectsCompleted": 28},
            "ownershipStructure": [
                {"label": "Instrument", "value": "Call-style Real Estate Option"},
                {"label": "Underlying", "value": "Branded Villa Unit"},
                {"label": "Settlement", "value": "Cash or Physical"},
            ],
            "investmentStructure": [
                {"label": "Option Premium", "value": "5% of strike"},
                {"label": "Strike Price", "value": "$5,000 / sqft"},
                {"label": "Activation Window", "value": "12 months"},
            ],
            "optionTerms": {
                "optionPremium": "$5,000 (5% of $100,000 allocation)",
                "activationDeadline": "12 months from listing",
                "lockedPrice": "$5,000 / sqft (strike)",
                "futureValue": "Projected $6,750 / sqft at expiry (+35%)",
            },
            "timeline": [
                {"label": "Premium paid", "date": "Today", "progress": 100, "valueIndex": 100, "status": "done"},
                {"label": "Mid-window NAV", "date": "+6m", "progress": 50, "valueIndex": 118, "status": "active"},
                {"label": "Decision window", "date": "+10m", "progress": 80, "valueIndex": 128, "status": "upcoming"},
                {"label": "Activation / Expiry", "date": "+12m", "progress": 100, "valueIndex": 135, "status": "upcoming"},
            ],
            "scenarios": [
                {"label": "Activated — market +35%", "outcome": "$5k premium → ~$30k notional gain", "tone": "positive"},
                {"label": "Not activated — flat market", "outcome": "Premium expires worthless, capped loss = $5k", "tone": "negative"},
                {"label": "Sold on secondary", "outcome": "Option transferred at intrinsic + time value", "tone": "neutral"},
            ],
            "exitMechanisms": [
                {"name": "Activate", "description": "Convert to unit ownership at strike.", "eta": "On settlement"},
                {"name": "Sell Option", "description": "Transfer position on secondary market.", "eta": "1–7 days"},
                {"name": "Expire", "description": "Walk away; loss capped at premium.", "eta": "Deadline"},
            ],
            "risks": [
                {"label": "Time decay", "level": "high", "note": "Option value decays toward expiry."},
                {"label": "Activation funding", "level": "medium", "note": "Investor must fund strike or assign."},
                {"label": "Market", "level": "medium", "note": "Underlying volatility drives option value."},
            ],
            "documents": _BASE_DOCS,
            "marketAnalysis": [
                {"label": "Palm 12m Δ", "value": "+11.4%"},
                {"label": "Implied vol (NAV)", "value": "Medium"},
            ],
        },
    },
    {
        "slug": "demo-shared-jeddah-tower",
        "model": "shared-development",
        "property_type": "commercial",
        "title": "Sample • Jeddah Shared Development Tower",
        "subtitle": "Co-invest in land + construction; share profits pro-rata",
        "location": "Obhur, Jeddah, KSA",
        "country": "Saudi Arabia",
        "city": "Jeddah",
        "total_value": 6500000,
        "minimum_investment": 1000,
        "expected_yield": 0,
        "capital_appreciation": 28,
        "funding_progress": 33,
        "investors_count": 54,
        "description": (
            "Educational sample of a shared development partnership. Investors co-fund both "
            "the land acquisition and the construction expenses alongside the developer, then "
            "share the resulting profits pro-rata to capital contributed."
        ),
        "images": ["https://images.unsplash.com/photo-1613490493576-7fde63acd811?w=1200&auto=format&fit=crop&q=80"],
        "content": {
            "badge": "Shared Development",
            "badgeTone": "shared",
            "developer": {"name": "Elite Gate Properties", "rating": 4.7, "projectsCompleted": 42},
            "ownershipStructure": [
                {"label": "Vehicle", "value": "Project SPV (LP / GP)"},
                {"label": "Investor Role", "value": "Limited Partner"},
                {"label": "Developer Role", "value": "General Partner"},
            ],
            "investmentStructure": [
                {"label": "Capital Stack", "value": "60% land / 40% build"},
                {"label": "Profit Split", "value": "70% LPs / 30% GP after hurdle"},
                {"label": "Hurdle Rate", "value": "8% pref"},
            ],
            "sharedTerms": {
                "landShare": "Investors fund 60% of land acquisition",
                "constructionShare": "Investors fund 40% of construction draws",
                "profitSplit": "70/30 split of net profit after 8% preferred return",
                "governance": "Quarterly LP reporting + major-decision voting rights",
            },
            "timeline": [
                {"label": "Land closed", "date": "Today", "progress": 100, "valueIndex": 100, "status": "done"},
                {"label": "Permits", "date": "+4m", "progress": 20, "valueIndex": 104, "status": "active"},
                {"label": "Construction", "date": "+18m", "progress": 70, "valueIndex": 118, "status": "upcoming"},
                {"label": "Sale / Stabilization", "date": "+30m", "progress": 100, "valueIndex": 128, "status": "upcoming"},
            ],
            "scenarios": [
                {"label": "Sell on completion", "outcome": "Investor IRR ~22% (after pref + split)", "tone": "positive"},
                {"label": "Hold and lease", "outcome": "Convert to income-generating ownership", "tone": "neutral"},
                {"label": "Cost overrun 15%", "outcome": "Margin compresses to ~10% IRR", "tone": "negative"},
            ],
            "exitMechanisms": [
                {"name": "LP Interest Sale", "description": "Transfer LP interest to qualified investor.", "eta": "Quarterly window"},
                {"name": "Project Sale", "description": "Distribute proceeds at exit.", "eta": "On completion"},
            ],
            "risks": [
                {"label": "Cost overrun", "level": "medium", "note": "Fixed-price contract on 80% of scope."},
                {"label": "Permit delay", "level": "medium", "note": "Standard regulatory risk."},
                {"label": "Liquidity", "level": "high", "note": "Limited interim liquidity until exit."},
            ],
            "documents": _BASE_DOCS,
            "marketAnalysis": [
                {"label": "Jeddah waterfront demand", "value": "Strong"},
                {"label": "Comparable JV IRRs", "value": "18–24%"},
            ],
        },
    },
    {
        "slug": "demo-portfolio-gcc-income",
        "model": "ready-portfolio",
        "property_type": "apartment",
        "title": "Sample • GCC Income Portfolio (8 assets)",
        "subtitle": "Diversified basket of leased ready properties across the GCC",
        "location": "GCC Diversified",
        "country": "UAE",
        "city": "Multi-city",
        "total_value": 18500000,
        "minimum_investment": 200,
        "expected_yield": 8.1,
        "capital_appreciation": 4.2,
        "total_return": 12.3,
        "funding_progress": 51,
        "investors_count": 312,
        "description": (
            "Educational sample of a ready-property portfolio. A single subscription gives the "
            "investor diversified exposure to eight leased income-producing properties across "
            "multiple GCC cities."
        ),
        "images": ["https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=1200&auto=format&fit=crop&q=80"],
        "content": {
            "badge": "Ready Portfolio",
            "badgeTone": "portfolio",
            "developer": {"name": "Capimax Portfolio Mgmt.", "rating": 4.8, "projectsCompleted": 60},
            "ownershipStructure": [
                {"label": "Vehicle", "value": "Master Portfolio SPV"},
                {"label": "Holdings", "value": "8 underlying SPVs"},
                {"label": "Rebalancing", "value": "Annual"},
            ],
            "investmentStructure": [
                {"label": "Distribution", "value": "Monthly blended yield"},
                {"label": "Fees", "value": "0.6% management"},
                {"label": "Lock-up", "value": "None"},
            ],
            "portfolioHoldings": [
                {"name": "Marina Bay Residences", "weight": "18%", "yield": "8.5%"},
                {"name": "Downtown Tower Suite", "weight": "14%", "yield": "9.2%"},
                {"name": "Abu Dhabi Waterfront", "weight": "12%", "yield": "8.8%"},
                {"name": "Doha Pearl Towers", "weight": "12%", "yield": "8.0%"},
                {"name": "Riyadh Plaza Retail", "weight": "11%", "yield": "9.5%"},
                {"name": "Muscat Hills Estate", "weight": "11%", "yield": "8.2%"},
                {"name": "Jeddah Seaside Villas", "weight": "11%", "yield": "7.5%"},
                {"name": "Manama Office", "weight": "11%", "yield": "9.8%"},
            ],
            "timeline": [
                {"label": "Subscription opens", "date": "Today", "progress": 100, "valueIndex": 100, "status": "done"},
                {"label": "First distribution", "date": "+45d", "progress": 0, "valueIndex": 101, "status": "upcoming"},
                {"label": "Annual rebalance", "date": "+12m", "progress": 0, "valueIndex": 105, "status": "upcoming"},
            ],
            "scenarios": [
                {"label": "Diversified base case", "outcome": "12.3% total return, low single-asset risk", "tone": "positive"},
                {"label": "1 asset vacant", "outcome": "Blended yield ~7.6%", "tone": "neutral"},
                {"label": "GCC-wide downturn", "outcome": "NAV down 4–7%, income resilient", "tone": "negative"},
            ],
            "exitMechanisms": [
                {"name": "Secondary Market", "description": "Resell portfolio units like a fund share.", "eta": "1–7 days"},
                {"name": "Liquidity Provider", "description": "Instant exit at slight discount.", "eta": "Same day"},
            ],
            "risks": [
                {"label": "Concentration", "level": "low", "note": "Diversified across 8 assets and 5 cities."},
                {"label": "Liquidity", "level": "low", "note": "Active secondary market on units."},
                {"label": "Market", "level": "medium", "note": "Macro property cycle exposure."},
            ],
            "documents": _BASE_DOCS,
            "marketAnalysis": [
                {"label": "GCC residential yield", "value": "7–9%"},
                {"label": "Portfolio NAV vol (1y)", "value": "Low"},
            ],
        },
    },
    {
        "slug": "demo-portfolio-construction-pipeline",
        "model": "construction-portfolio",
        "property_type": "commercial",
        "title": "Sample • Off-Plan Pipeline Portfolio (5 projects)",
        "subtitle": "Diversified basket of under-construction projects across cycles",
        "location": "Multi-city Pipeline",
        "country": "UAE",
        "city": "Multi-city",
        "total_value": 24000000,
        "minimum_investment": 500,
        "capital_appreciation": 24,
        "funding_progress": 22,
        "investors_count": 88,
        "description": (
            "Educational sample of an under-construction portfolio. Investors gain diversified "
            "exposure to 5 off-plan projects at different construction stages, smoothing "
            "milestone-based appreciation."
        ),
        "images": ["https://images.unsplash.com/photo-1577415124269-fc1140815c3b?w=1200&auto=format&fit=crop&q=80"],
        "content": {
            "badge": "Construction Portfolio",
            "badgeTone": "portfolio",
            "developer": {"name": "Capimax Pipeline", "rating": 4.6, "projectsCompleted": 35},
            "ownershipStructure": [
                {"label": "Vehicle", "value": "Pipeline SPV"},
                {"label": "Holdings", "value": "5 off-plan projects"},
                {"label": "Stage Mix", "value": "Land → Foundation → Structure → Fit-out"},
            ],
            "investmentStructure": [
                {"label": "Capital Call", "value": "Single upfront subscription"},
                {"label": "Settlement", "value": "Per project handover"},
                {"label": "Fees", "value": "0.8% management + 15% perf > 8%"},
            ],
            "portfolioHoldings": [
                {"name": "Creek Tower (installment)", "weight": "25%"},
                {"name": "Business Bay Future", "weight": "22%"},
                {"name": "Riyadh Central Plaza", "weight": "20%"},
                {"name": "Bahrain Financial District", "weight": "18%"},
                {"name": "Palm Option Residences", "weight": "15%"},
            ],
            "timeline": [
                {"label": "Subscribed", "date": "Today", "progress": 100, "valueIndex": 100, "status": "done"},
                {"label": "First milestone", "date": "+6m", "progress": 25, "valueIndex": 106, "status": "active"},
                {"label": "Mid pipeline", "date": "+18m", "progress": 60, "valueIndex": 116, "status": "upcoming"},
                {"label": "Final delivery", "date": "+30m", "progress": 100, "valueIndex": 124, "status": "upcoming"},
            ],
            "scenarios": [
                {"label": "Pipeline delivers", "outcome": "+24% blended appreciation", "tone": "positive"},
                {"label": "1 project delayed", "outcome": "Slight IRR drag (~2%)", "tone": "neutral"},
                {"label": "Sector slowdown", "outcome": "NAV volatility, mitigated by stage diversification", "tone": "negative"},
            ],
            "exitMechanisms": [
                {"name": "Secondary Market", "description": "Sell portfolio units pre-completion.", "eta": "5–14 days"},
                {"name": "Liquidity Provider", "description": "Instant discounted exit.", "eta": "Same day"},
            ],
            "risks": [
                {"label": "Construction risk", "level": "medium", "note": "Diversified across stages and developers."},
                {"label": "Liquidity", "level": "medium", "note": "Pre-completion liquidity is reduced."},
                {"label": "Market", "level": "medium", "note": "Cycle exposure across 5 assets."},
            ],
            "documents": _BASE_DOCS,
            "marketAnalysis": [
                {"label": "Off-plan vs ready spread", "value": "−20%"},
                {"label": "Pipeline IRR target", "value": "16–20%"},
            ],
        },
    },
    {
        "slug": "demo-land-neom-coinvest",
        "model": "shared-development",
        "property_type": "land",
        "title": "Sample - NEOM Land Co-Investment",
        "subtitle": "Co-invest in prime development land ahead of infrastructure delivery",
        "location": "NEOM, Tabuk, KSA",
        "country": "Saudi Arabia",
        "city": "NEOM",
        "total_value": 9000000,
        "minimum_investment": 500,
        "capital_appreciation": 40,
        "funding_progress": 15,
        "investors_count": 37,
        "description": (
            "Educational sample of a land co-investment. Investors pool capital to acquire a "
            "plot of development land alongside the developer and share the uplift as "
            "infrastructure and permits mature toward a build or resale exit."
        ),
        "images": ["https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=1200&auto=format&fit=crop&q=80"],
        "content": {
            "badge": "Land - Shared Development",
            "badgeTone": "shared",
            "developer": {"name": "Vision Land Partners", "rating": 4.5, "projectsCompleted": 19},
            "ownershipStructure": [
                {"label": "Vehicle", "value": "Land SPV (LP / GP)"},
                {"label": "Investor Role", "value": "Limited Partner"},
                {"label": "Asset", "value": "Freehold development plot"},
            ],
            "investmentStructure": [
                {"label": "Min. Ticket", "value": "$500"},
                {"label": "Profit Split", "value": "75% LPs / 25% GP after hurdle"},
                {"label": "Hurdle Rate", "value": "8% pref"},
            ],
            "sharedTerms": {
                "landShare": "Investors fund 100% of the land acquisition",
                "constructionShare": "Build phase funded in a later round (optional)",
                "profitSplit": "75/25 split of net profit after 8% preferred return",
                "governance": "Quarterly LP reporting + major-decision voting rights",
            },
            "timeline": [
                {"label": "Land acquired", "date": "Today", "progress": 100, "valueIndex": 100, "status": "done"},
                {"label": "Master-plan approval", "date": "+8m", "progress": 30, "valueIndex": 112, "status": "active"},
                {"label": "Infrastructure", "date": "+20m", "progress": 60, "valueIndex": 128, "status": "upcoming"},
                {"label": "Build / Resale", "date": "+36m", "progress": 100, "valueIndex": 140, "status": "upcoming"},
            ],
            "scenarios": [
                {"label": "Resale post-permits", "outcome": "Projected +40% land uplift", "tone": "positive"},
                {"label": "Hold to build", "outcome": "Convert to a development co-investment", "tone": "neutral"},
                {"label": "Permit delay", "outcome": "Timeline extends; land value resilient", "tone": "negative"},
            ],
            "exitMechanisms": [
                {"name": "LP Interest Sale", "description": "Transfer LP interest to a qualified investor.", "eta": "Quarterly window"},
                {"name": "Land Resale", "description": "Distribute proceeds on plot sale.", "eta": "On exit"},
            ],
            "risks": [
                {"label": "Liquidity", "level": "high", "note": "Land is illiquid until a resale/build event."},
                {"label": "Permit", "level": "medium", "note": "Zoning/approval timing risk."},
                {"label": "Market", "level": "medium", "note": "Regional land-cycle exposure."},
            ],
            "documents": _BASE_DOCS,
            "marketAnalysis": [
                {"label": "Regional land 3y change", "value": "+31%"},
                {"label": "Comparable plot IRRs", "value": "18-26%"},
            ],
        },
    },
    {
        "slug": "demo-ready-income-emirates-hills-villa",
        "model": "ready-income",
        "property_type": "villa",
        "title": "Sample - Emirates Hills Income Villa",
        "subtitle": "Leased luxury villa generating monthly rental income",
        "location": "Emirates Hills, Dubai, UAE",
        "country": "UAE",
        "city": "Dubai",
        "total_value": 5200000,
        "minimum_investment": 250,
        "expected_yield": 6.8,
        "capital_appreciation": 5.2,
        "total_return": 12.0,
        "funding_progress": 44,
        "investors_count": 129,
        "description": (
            "Educational sample of a ready, leased luxury villa. Investors own fractional "
            "shares through the SPV and receive monthly net rental distributions plus "
            "long-term capital appreciation."
        ),
        "images": ["https://images.unsplash.com/photo-1613977257363-707ba9348227?w=1200&auto=format&fit=crop&q=80"],
        "content": {
            "badge": "Ready - Income Villa",
            "badgeTone": "ready",
            "developer": {"name": "Prime Villas Estate", "rating": 4.8, "projectsCompleted": 33},
            "ownershipStructure": [
                {"label": "Ownership Vehicle", "value": "DIFC SPV"},
                {"label": "Income Type", "value": "Monthly Net Rental + Appreciation"},
                {"label": "Custody", "value": "Independent Trustee"},
            ],
            "investmentStructure": [
                {"label": "Min. Ticket", "value": "$250"},
                {"label": "Distribution Frequency", "value": "Monthly"},
                {"label": "Holding Period", "value": "Open-ended"},
                {"label": "Lock-up", "value": "None (secondary market)"},
            ],
            "timeline": [
                {"label": "Listed", "date": "Today", "progress": 100, "valueIndex": 100, "status": "done"},
                {"label": "Funding Closes", "date": "+30d", "progress": 44, "valueIndex": 100, "status": "active"},
                {"label": "First Distribution", "date": "+60d", "progress": 0, "valueIndex": 101, "status": "upcoming"},
                {"label": "Annual Revaluation", "date": "+12m", "progress": 0, "valueIndex": 105, "status": "upcoming"},
            ],
            "scenarios": [
                {"label": "Base case", "outcome": "6.8% yield + 5.2% appreciation = 12% total", "tone": "positive"},
                {"label": "Vacancy 1 month", "outcome": "~6.2% yield + appreciation", "tone": "neutral"},
                {"label": "Market downturn", "outcome": "Income steady, NAV may dip 4-7%", "tone": "negative"},
            ],
            "exitMechanisms": [
                {"name": "Secondary Market", "description": "List units to other investors.", "eta": "1-7 days"},
                {"name": "Liquidity Provider", "description": "Instant exit at a small discount.", "eta": "Same day"},
            ],
            "risks": [
                {"label": "Vacancy", "level": "medium", "note": "Premium segment, longer re-let cycle."},
                {"label": "Liquidity", "level": "low", "note": "Active secondary market."},
                {"label": "Market", "level": "medium", "note": "Prime-villa cycle exposure."},
            ],
            "documents": _BASE_DOCS,
            "marketAnalysis": [
                {"label": "Avg. Villa Rent (Emirates Hills)", "value": "$29,000 / mo"},
                {"label": "Occupancy Rate", "value": "88%"},
                {"label": "12m Price change", "value": "+6.1%"},
            ],
        },
    },
    {
        "slug": "demo-ready-income-difc-office",
        "model": "ready-income",
        "property_type": "commercial",
        "title": "Sample - DIFC Grade-A Office Floor",
        "subtitle": "Fully leased office floor with a blue-chip corporate tenant",
        "location": "DIFC, Dubai, UAE",
        "country": "UAE",
        "city": "Dubai",
        "total_value": 7800000,
        "minimum_investment": 200,
        "expected_yield": 9.1,
        "capital_appreciation": 3.6,
        "total_return": 12.7,
        "funding_progress": 57,
        "investors_count": 241,
        "description": (
            "Educational sample of a ready, fully leased Grade-A office floor. Investors "
            "receive monthly net rental income from a blue-chip corporate tenant on a "
            "multi-year lease, plus capital appreciation."
        ),
        "images": ["https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=1200&auto=format&fit=crop&q=80"],
        "content": {
            "badge": "Ready - Commercial Income",
            "badgeTone": "ready",
            "developer": {"name": "Gulf Commercial REIT Mgmt.", "rating": 4.7, "projectsCompleted": 51},
            "ownershipStructure": [
                {"label": "Ownership Vehicle", "value": "DIFC SPV"},
                {"label": "Income Type", "value": "Monthly Net Rental + Appreciation"},
                {"label": "Lease", "value": "5-year corporate lease"},
            ],
            "investmentStructure": [
                {"label": "Min. Ticket", "value": "$200"},
                {"label": "Distribution Frequency", "value": "Monthly"},
                {"label": "Holding Period", "value": "Open-ended"},
                {"label": "Lock-up", "value": "None (secondary market)"},
            ],
            "timeline": [
                {"label": "Listed", "date": "Today", "progress": 100, "valueIndex": 100, "status": "done"},
                {"label": "Funding Closes", "date": "+30d", "progress": 57, "valueIndex": 100, "status": "active"},
                {"label": "First Distribution", "date": "+45d", "progress": 0, "valueIndex": 101, "status": "upcoming"},
                {"label": "Annual Revaluation", "date": "+12m", "progress": 0, "valueIndex": 104, "status": "upcoming"},
            ],
            "scenarios": [
                {"label": "Base case", "outcome": "9.1% yield + 3.6% appreciation = 12.7% total", "tone": "positive"},
                {"label": "Tenant renewal", "outcome": "Rent step-up on renewal", "tone": "positive"},
                {"label": "Vacancy risk", "outcome": "Single-tenant re-let exposure", "tone": "negative"},
            ],
            "exitMechanisms": [
                {"name": "Secondary Market", "description": "Resell units to other investors.", "eta": "1-7 days"},
                {"name": "Liquidity Provider", "description": "Instant exit at a small discount.", "eta": "Same day"},
            ],
            "risks": [
                {"label": "Single-tenant", "level": "medium", "note": "Concentration on one corporate lease."},
                {"label": "Liquidity", "level": "low", "note": "Active secondary market."},
                {"label": "Market", "level": "medium", "note": "Office-sector cycle exposure."},
            ],
            "documents": _BASE_DOCS,
            "marketAnalysis": [
                {"label": "DIFC Grade-A yield", "value": "8-10%"},
                {"label": "Occupancy Rate", "value": "92%"},
                {"label": "12m Rent change", "value": "+4.3%"},
            ],
        },
    },
]
# fmt: on


def _to_property(s: dict) -> Property:
    unit_price = Decimal(str(s["minimum_investment"]))
    total_value = Decimal(str(s["total_value"]))
    total_units = max(int(total_value / unit_price), 1)
    return Property(
        owner_id=None,
        title=s["title"],
        subtitle=s["subtitle"],
        description=s["description"],
        location=s["location"],
        country=s["country"],
        city=s["city"],
        property_type=s["property_type"],
        model=s["model"],
        slug=s["slug"],
        status=PropertyStatus.active,
        total_value=total_value,
        unit_price=unit_price,
        total_units=total_units,
        available_units=total_units,
        minimum_investment=Decimal(str(s["minimum_investment"])),
        target_yield=(Decimal(str(s["expected_yield"])) if s.get("expected_yield") else None),
        expected_yield=(
            Decimal(str(s["expected_yield"])) if s.get("expected_yield") is not None else None
        ),
        capital_appreciation=(
            Decimal(str(s["capital_appreciation"]))
            if s.get("capital_appreciation") is not None
            else None
        ),
        total_return=(
            Decimal(str(s["total_return"])) if s.get("total_return") is not None else None
        ),
        funding_progress=Decimal(str(s["funding_progress"])),
        investors_count=int(s["investors_count"]),
        funded_amount=(total_value * Decimal(str(s["funding_progress"])) / Decimal(100)),
        images=s["images"],
        content=s["content"],
    )


async def _seed() -> int:
    created = 0
    milestones_added = 0
    async with session_scope() as session:
        for s in SAMPLES:
            res = await session.execute(select(Property).where(Property.slug == s["slug"]))
            prop = res.scalar_one_or_none()
            if prop is None:
                prop = _to_property(s)
                session.add(prop)
                await session.flush()  # populate prop.id for the milestone FK
                created += 1
            # Phase 15b — idempotent milestone seed: only when this property has none
            # (covers fresh seeds; existing properties were backfilled by migration 0015).
            has_m = await session.execute(
                select(PropertyMilestone.id)
                .where(PropertyMilestone.property_id == prop.id)
                .limit(1)
            )
            if has_m.first() is None:
                timeline = (prop.content or {}).get("timeline") or []
                anchor = prop.created_at.date() if prop.created_at else dt.date.today()
                for r in timeline_to_milestone_rows(
                    timeline, anchor=anchor, created_by=prop.owner_id
                ):
                    session.add(
                        PropertyMilestone(
                            property_id=prop.id,
                            **{**r, "status": MilestoneStatus(r["status"])},
                        )
                    )
                    milestones_added += 1
    print(
        f"OK: seeded {created} demo properties "
        f"({len(SAMPLES) - created} already present); {milestones_added} milestones added."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_seed()))
