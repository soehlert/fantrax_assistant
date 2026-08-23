# Fantrax Assistant - Draft Recommendation & Pick Grading Architecture

This document describes the official league settings for **New Draft City** (`ssqyqa4umsqa7n3g`) and the 4 sub-algorithms powering the **Fantrax Assistant Draft Recommendation Engine** (`src/fantrax_assistant/suggest.py`), **Weekly Lineup Manager** (`src/fantrax_assistant/weekly.py`), and **Pick Analyzer** (`src/fantrax_assistant/analysis.py`).

---

## 🏆 Official League Configuration (New Draft City)

- **League ID**: `ssqyqa4umsqa7n3g` | **Max Teams**: 9
- **Active Roster Limits**:
  - **Defender (D)**: Min 3, Max 5 (Max GP: 200)
  - **Midfielder (M)**: Min 3, Max 5 (Max GP: 200)
  - **Forward (F)**: Min 1, Max 4 (Max GP: 200)
  - **Goalkeeper (G)**: Min 1, Max 1 (Max GP: 50)
  - **Total Active Players**: 11 (Roster Min 10, Max 16)
- **Supported Starting Formations**: `3-3-4`, `3-4-3`, `3-5-2`, `4-3-3`, `4-4-2`, `4-5-1`, `5-3-2`, `5-4-1`.
- **Scoring Rules Highlights**:
  - **Goals**: Forward = 4 pts | Midfielder = 5 pts | Defender = 6 pts | Goalkeeper = 6 pts
  - **Assists**: Official = 3 pts | Secondary = 1 pt | Fantasy = 2 pts
  - **Clean Sheets**: Defender = 4 pts | Midfielder = 1 pt | Goalkeeper = 5 pts
  - **Per-Game Cumulative**: Interceptions = +0.333/Int | Tackles Won = +0.333/TkW | Shots on Target = +0.5/SOT | Defender Goals Against = -0.5/GAO

---

## 🏗️ Core Architecture Overview

```
 ┌─────────────────────────────────────────────────────────────┐
 │                1. Player Base Value Engine                  │
 │   Raw Talent, Regressed FP/G & Workload/Rotation Risk       │
 └──────────────────────────────┬──────────────────────────────┘
                                │
 ┌──────────────────────────────▼──────────────────────────────┐
 │             2. Dynamic Draft Context Engine                 │
 │     Sliding Position Multipliers (Early F/M vs Late D/G)    │
 └──────────────────────────────┬──────────────────────────────┘
                                │
 ┌──────────────────────────────▼──────────────────────────────┐
 │              3. Roster Fit & Flex Depth Engine              │
 │     Primary (1.0) / Backup (0.5) Depth & Handcuff Boosts   │
 └──────────────────────────────┬──────────────────────────────┘
                                │
 ┌──────────────────────────────▼──────────────────────────────┐
 │         4. Draft Reaction & Opportunity Cost Analyzer       │
 │       ADP Steals vs Reaches & Organic ESPN Analyst Blurbs   │
 └─────────────────────────────────────────────────────────────┘
```

---

## 1. Player Base Value Engine
> **Goal**: Measure a player's raw fantasy point generation capability in a vacuum.

- **Regressed Sample Size (Effective FP/G)**:
  - Players with fewer than 5 matches played have their sample size regressed toward the league baseline (**2.25 FP/G**) to prevent short-sample flukes from distorting rankings.
- **Workload & Rotation Risk Adjustments (Negative Value Factors)**:
  - **Core Starters** ($\ge 30$ starts or $\ge 2,500$ mins): **1.00** (Full expected value).
  - **Regular Starters** (22–29 starts or $\ge 1,800$ mins): **0.95** (**-5% negative workload adjustment**).
  - **Moderate Workload / Rotation** (14–21 starts): **0.88** (**-12% negative rotation risk adjustment**).
  - **Low Volume / Heavy Rotation** ($<14$ starts): **0.80** (**-20% negative rotation risk adjustment**).
- **New Manager Tactical Reset Adjustment**:
  - Clubs with new managers (`LIV`, `CHE`, `MUN`, `BHA`, `WHU`) apply an additional **-7% negative tactical reset adjustment** (`0.93` factor) for non-core veterans, accounting for line-up reshuffling under fresh management.

---

## 2. Dynamic Draft Context Engine
> **Goal**: Adjust position weights dynamically as the draft progresses across 128 total picks.

- **Attacker Early Premium**:
  - Forwards (`F: 1.40x`) and Midfielders (`M: 1.15x`) are weighted highest early because goal/assist producers are scarce.
- **Sliding Multipliers for Defenders & Goalkeepers**:
  - Draft progress ratio $P = \frac{\text{drafted\_picks}}{128}$.
  - **Defenders (`D`)**: Base `0.45x` early, sliding smoothly up to **`0.80x`** late.
  - **Goalkeepers (`G`)**: Base `0.25x` early, sliding smoothly up to **`0.65x`** late.

---

## 3. Roster Fit & Flex Depth Engine
> **Goal**: Optimize suggestions for YOUR specific roster needs without panic-drafting.

- **Primary vs. Backup Flex Roster Depth**:
  - **Primary Position Match** (first listed position, e.g. `M` for `M,F`): Counts as **`1.0`** roster depth.
  - **Secondary Backup Position Match** (e.g. `F` for `M,F`): Counts as **`0.5`** roster depth.
  - *Example*: Mateta (`F`, 1.0) + Eze (`M,F`, 0.5) + Rayan (`M,F`, 0.5) = **2.0 Forward Depth**. You are 2/4 filled, so Forward is a normal core need (`9.0` pts) rather than an empty panic need (`13.0` pts).
- **Tier Cliff Preservation Bonus**:
  - If drafting a player prevents falling off a steep production drop-off ($\ge 0.8$ FP/G drop to the next 3 available candidates), grants an additional **+2.0 to +3.0 point Tier Cliff Bonus**.
- **Teammate Handcuff Insurance Boost**:
  - If your roster already owns a key player from Club $T$ at Position $Pos$ (e.g. Matheus Nunes, `MCI`, `D`), drafting an available teammate at the same position (e.g. Abdukodir Khusanov, `MCI`, `D`) grants a **+4.0 point Handcuff Insurance Boost**.

---

## 4. Draft Reaction & Opportunity Cost Analyzer
> **Goal**: Grade picks instantly in the live reaction feed.

- **Market Value Steals vs. Reaches**:
  - Calculates $\Delta = \text{pick\_number} - \text{ADP}$.
  - Steals ($\Delta \ge 10$) get an `A+` grade; reaches ($\Delta \le -25$) receive a reach penalty.
- **Positional Opportunity Cost**:
  - Checks if a pick passed on a significantly higher-projected candidate at the same position within 20 picks.
- **Organic ESPN Analyst Blurbs**:
  - Synthesizes value, roster fit, tier cliff timing, and handcuff synergies into 2–3 active, natural sports-journalism sentences without rigid prefix labels.
