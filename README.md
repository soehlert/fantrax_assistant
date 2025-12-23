# Player Evaluation Pipeline
Help me draft better on Fantrax

## Plain Language Algorithm Explanation
Your algorithm scores each player on 8 different factors that together give you a final draft value score (out of ~100). Here's what each factor evaluates:

### The 8 Scoring Components
#### 1. Base Value (30% weight)

Looks at how many fantasy points per game (FP/G) the player averages
Your league's scoring rules are already baked into Fantrax's FP/G calculation
Attackers (forwards) get a higher position weight (1.25×) than defenders (0.50×) because they're harder to find in your league
Caps out at 30 points max

#### 2. ADP Value (7% weight)

Rewards "value picks" - players that analysts thought would go earlier but are still available
Player with ADP 10 if still available = great value
Player with ADP 150 if still available = not good value
Caps at 7 points max

#### 3. Recent Form (20% weight)

Checks if they've been performing well lately (last 30-60 days)
Falls back to "how many matches have they played this season" if recent data not available
A hot player gets boosted

#### 4. Club Bonus (bonus points)

Your league awards extra points for most goals by non-top-8 clubs
If player is from non-top-8 (not City, Arsenal, Liverpool, etc.) AND has 5+ goals, add 2 bonus points
No cap on this

#### 5. Missed Time Penalty (15% weight)

Severely punishes AFCON players (reduces to 30% of what they'd score)
Reduces based on injury status:
Healthy: 100% score
Questionable: 85%
Doubtful: 60%
Short Term: 40%
Medium Term: 25%
Long Term: 10%
This is multiplicative, so injuries can tank scores

#### 6. Position Need (10% weight, multiplied by position multiplier)

Checks if you already have enough players at that position
You have 0 forwards (max 4)? This is CRITICAL → 15 points base
You have 1 forward (max 4)? You need more → 10 points base
You already have 4 forwards (max 4)? Not needed → 3 points base
Then multiplies by position multiplier (attackers worth more):
Forward × 1.25 = more valuable for position need
Defender × 0.50 = less valuable for position need
Versatility bonus: Players with 2+ positions get +15% per extra position (F,M player = 1.15× multiplier)

#### 7. Position Scarcity (5% weight)

Measures the drop-off in quality at this position
If you're picking the #1 forward available, massive drop-off to #2 → high scarcity (2-5 points)
If you're picking the #18 forward, small drop-off to #19-23 → low scarcity (0.5-3 points)
Shows how thin the talent is at each position

#### 8. Positional Value (5% weight)

Compares this player to the AVERAGE player at their position
If a forward averages 5 FP/G when forwards average 3.5 → he's 43% above average → gets bonus points
Shows who's truly elite vs just "good" at their position


┌────────────────────────────────────────────────────────────────┐
│            Player Evaluation Pipeline                          |
└────────────────────────────────────────────────────────────────┘

┌─────────────────────────── INPUT DATA ─────────────────────────┐
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ ADP Rankings │  │ Current      │  │ Injuries &   │          │
│  │              │  │ Season Stats │  │ AFCON Status │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Recent Form  │  │ League       │  │ Drafted      │          │
│  │ (30/60 days) │  │ Configuration│  │ Players Set  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                │
└────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                 ┌─────────────────────────┐
                 │ Get Available Players   │
                 │ (filter drafted)        │
                 │ Return: list of N       │
                 └─────────────────────────┘
                               │
                               ▼
         ┌─────────────────────────────────────────┐
         │  EVALUATE EACH PLAYER (8 FACTORS)       │
         └─────────────────────────────────────────┘
             │         │        │        │        │        │       │       │
        ┌────▼──┐  ┌───▼──┐  ┌─▼──┐  ┌─▼──┐  ┌──▼─┐  ┌──▼──┐ ┌──▼──┐ ┌──▼──┐
        │ Base  │  │ Club │  │ADP │  │Form│  │Inj.│  │Need │ │Scar.│ │Pos. │
        │ Value │  │ Bonus│  │Val.│  │Val.│  │Pen.│  │Score│ │ Val.│ │ Val.│
        │ 30%   │  │Extra │  │15% │  │20% │  │15% │  │10%  │ │ 5%  │ │ 5%  │
        └────┬──┘  └───┬──┘  └─┬──┘  └─┬──┘  └──┬─┘  └──┬──┘ └──┬──┘ └──┬──┘
             │         │       │       │        │       │       │       │
             └─────────┴───────┴───────┴────────┴───────┴───────┴───────┘
                                      │
                            ┌─────────▼──────────────┐
                            │   SUM ALL SCORES       │
                            │   (typically 60-90)    │
                            └────────────────────────┘
                                      │
                            ┌─────────▼──────────────┐
                            │  SORT BY TOTAL SCORE   │
                            │  (descending)          │
                            └────────────────────────┘
                                      │
                            ┌─────────▼──────────────┐
                            │  RETURN TOP N PLAYERS  │
                            │  (user specified)      │
                            └────────────────────────┘