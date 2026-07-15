# Life in Adventure — Game Mechanics Reference

> **Status**: Researched via Tavily Web Search + Exa verification — v1.1 (reviewed)
> **Sources**: r/LifeInAdventure, Fandom Wiki (Stats, Epilogues, Life in Adventure Wiki), GameGrin Review, Reddit, App Store Reviews, LDPlayer Guide, Scribd Community Guide (607016681), Cobraknife Traits Guide
> **Game Version**: 1.2.42 (February 2026)
> **Last Updated**: 2026-07-06 (post-review patch)
> **Revision History**: v1.1 fixed EXP cap, alignment model, stat threshold (27), §14 numbering per REVIEW_REPORT.md C1/C2/C3/M1

---

## 1. Overview

Life in Adventure adalah text-based RPG dengan mechanics yang terinspirasi D&D tapi dengan simplifikasi signifikan. Semua mechanics ultimately mengarah ke dua hal: **(1) mengisi EXP bar** dan **(2) memilih keputusan yang menghasilkan ending epilogue terbaik**.

> ⚠️ **CRITICAL META MEKANIK**: Game punya 2 strategi play-style berlawanan — *"EXP farming"* (gabung semua event untuk rank cepat) dan *"EXP fasting"* (hindari EXP-generating event untuk naik stat tinggi sebelum ending trigger). Tool ini WAJIB mengakomodasi kedua strategi, jangan asumsikan high-reward choice selalu terbaik. Lihat §4.

---

## 2. Character Stats

### 2.1 The Six Stats

Game menggunakan 6 stats klasik D&D. Setiap stat range dari **1-27+** (average manusia = 10; threshold Super skill unlock di 27). Verified via Fandom Wiki `life-in-adventure.fandom.com/wiki/Stats`:

| Stat | Full Name | Primary Uses | Stat Bonus at 10 |
|-------|-----------|-------------|-------------------|
| **STR** | Strength | Combat damage, breaking things, physical checks; inventory slot +1 per 3 STR; at 18 Super Strength +1, at 27 Super Strength +2 | +0 modifier |
| **DEX** | Dexterity | Sneaking, traps, initiative, acrobatics, dodge; at 18 Acrobatic +1, at 27 Acrobatic +2 | +0 modifier |
| **INT** | Intelligence | Magic damage, knowledge checks, spell success | +0 modifier |
| **CHA** | Charisma | Persuasion, deception, bartering, crowd control; at 18 + alignment Moral/Good → Grace +1/+2; at 18 + alignment Impure/Evil → Intimidating +1/+2 | +0 modifier |
| **CON** | Constitution | HP, poison resistance, endurance | +0 modifier |
| **WIS** | Wisdom | Perception, insight, survival, wisdom saves | +0 modifier |

**Stat Modifier Formula**: `(stat - 10) // 2`
- Stat 10 → modifier +0
- Stat 12 → modifier +1
- Stat 14 → modifier +2
- Stat 16 → modifier +3
- Stat 18 → modifier +4
- Stat 20 → modifier +5

### 2.2 Stat Thresholds & Bonuses

Stats di atas threshold tertentu memberikan **passive bonuses**. Verified via Fandom Wiki Stats page + Cobraknife traits guide:

| Threshold | Bonus | Source |
|-----------|-------|--------|
| **Any stat ≥ 10** | +1 bonus to related ability checks (%) | Fandom Wiki |
| **STR + DEX ≥ 13 each** | Weapon Mastery +1 (physical damage +10%) | Fandom Wiki |
| **STR + DEX ≥ 20 each** | Weapon Mastery +2 (physical damage +20%) | Fandom Wiki |
| **STR ≥ 13** | +2 combat power per 1 pt STR | Reddit |
| **DEX + WIS ≥ 13 each** | Survival +1 (trap detection, nature checks) | Fandom Wiki |
| **DEX + WIS ≥ 20 each** | Survival +2 | Fandom Wiki |
| **CHA ≥ 10** | CHA bonus to vendor discount: -10% per 10 CHA | AppGamer |
| **CHA ≥ 10** | CHA bonus to persuasion checks (%) | AppGamer |
| **INT ≥ 10** | Intelligence bonus to %-chance ability checks | AppGamer |
| **STR + CON ≥ 13 each** | Toughness +1 (Defense +10%, HP/consecutive wins bonus) | Fandom Wiki |
| **STR + CON ≥ 20 each** | Toughness +2 (Defense +20%) | Fandom Wiki |
| **STR ≥ 18** | Super Strength +1 (physical attack +10%) | Fandom Wiki |
| **STR ≥ 27** | Super Strength +2 (physical attack +20%) | Fandom Wiki |
| **DEX ≥ 18** | Acrobatic +1 (agility checks up, evasion up) | Fandom Wiki |
| **DEX ≥ 27** | Acrobatic +2 | Fandom Wiki |
| **CHA ≥ 18 + Moral/Good** | Grace +1 / +2 (alignment-locked skill) | Fandom Wiki |
| **CHA ≥ 18 + Impure/Evil** | Intimidating +1 / +2 | Fandom Wiki |
| **Any stat ≥ 25** | Achievement unlocked | Exophase achievements |

> ⚠️ **Note**: Threshold 27 (Super +2 tier) NOT tercantum di dokumen sebelumnya. APK extraction wajib verify exact unlock behavior dan apakah ada tier berikutnya (>30, etc.).

### 2.3 Starting Stats

Pemain mendapatkan stats awal untuk di-distribute. Stat points per level-up **berubah seiring level** — pemain dapat kurang poin per level tapi lebih sering level up, menghasilkan **total stats lebih tinggi di endgame** (confirmed dari Reddit patch note).

### 2.4 Stat Check Formula (D20-based, hybrid with Power Points)

Game menggunakan **hybrid dice + power points** formula (bukan D&D pure DC). Verified via GameGrin review:

```
Roll: 1d20 (visible) + stat_modifier + power_points_from_equipment
vs Effective DC (combination of enemy stat + equipment)
```
- Roll 20 = Critical Success (instant win, one-shot enemy)
- Roll 1 = Critical Fail (worst outcome)
- Roll > 10 → Player gains power (better odds)
- Roll < 10 → Player loses power (worse odds)
- DC/threshold varies: 5-20 tergantung difficulty pilihan + enemy equipment

**Contoh**:
| DC | Stat Needed | Modifier | Roll Required |
|----|-----------|----------|---------------|
| 5 | DEX 10+ | +0 | Roll ≥ 5 |
| 10 | DEX 14+ | +2 | Roll ≥ 8 |
| 15 | CHA 18+ | +4 | Roll ≥ 11 |

---

## 3. Combat System

### 3.1 Overview

Combat adalah **D20 roll + stat modifier + equipment power** melawan enemy stats. Dice roll langsung terlihat pemain (1-20).

```
Enemy HP → 0 = Victory
Player HP → 0 = Defeat / Game Over
```

### 3.2 Combat Flow

```
1. Roll 1d20 (visible to player)
   ├─ Roll < 10 → Player loses power (worse odds)
   └─ Roll > 10 → Player gains power (better odds)
   └─ Roll = 20 → CRITICAL HIT (one-shot kill)
   └─ Roll = 1 → CRITICAL FAIL (worst outcome)

2. Power Points (from equipment) determine battle odds
3. Both sides exchange damage based on stats + equipment
4. Continue until one side reaches 0 HP
```

**Confirmed dari GameGrin review**: "Combat is simple...you get power points by gearing up with good equipment...these power points dictate how probable you are to win a match against opponents but are also a die involved that rolls from 1-20. If it's less than 10 you lose power and if it's greater than you gain instead."

### 3.3 Combat Power Calculation

```
Combat Power = Base (from stats) + Equipment Bonus + Trait Bonus
```

**Per stat contribution** (from Reddit guide):
- 1 STR → +2 combat power
- 1 DEX → +1 combat power
- 1 INT → Spellcasting power (separate track)

### 3.4 Enemy Scaling

- Enemy strength scales dengan level area
- Boss encounters (Balor, Blue Dragon, Red Dragon, White Dragon) memerlukan specific strategies
- Confirmed: "To beat blue dragon have high charisma and two Tiny golems. They give you lightning resistance and stun enemies." (Reddit)

### 3.5 Initiative & Turn Order

- Initiative based on DEX modifier
- Higher DEX = faster/act first
- No explicit turn order display in text — flow determined by choices

---

## 4. Leveling & Experience

> ⚠️ **CRITICAL untuk tool ini**: C1 dari REVIEW_REPORT menandai area ini sebagai load-bearing untuk AI decision engine. Tanpa modeling EXP management, tool akan merekomendasi high-reward choices yang merusak strategi player.

### 4.1 EXP Bar System

```
Choices → EXP gained → Bar fills (max 100) → Level up at rank milestones
                       ↓ full bar (100)
                       Ending terpicu (epilogue)
```

- **EXP source**: Setiap pilihan memberikan EXP:
  - Enemy encounter victory → **1 EXP**
  - Random event → **1-2 EXP**
  - Major event → **2-3 EXP**
  - Some choices give **0 EXP** (dialogue-only, merchant-style)
- **EXP cap**: **100** (verified via LDPlayer guide + Scribd comprehensive guide + Fandom Wiki Epilogues page)
- **Progress bar** terlihat di UI game; tap progress bar = view EXP + Alignment
- **Rank up milestones** di EXP: **10 / 20 / 35 / 55 / 80** (5 rank-up total per playthrough)
- Each rank up → **4 attribute points** untuk distribute
- **Post-full-bar**: Adventure end (epilogue triggered). Bila target epilogue belum unlocked → "early ending" undesirable untuk completionist

### 4.2 Level-Up Stats

Setiap level up memberikan **4 stat points** untuk didistribusikan (confirmed dari review). Total stat points per playthrough tetap tergantung jumlah rank achieved (max 5 rank = 20 AP).

### 4.3 EXP Fasting Strategi (CRITICAL untuk AI reasoning)

**"EXP Fasting"** adalah meta strategi verified via LDPlayer guide dan Scribd community guide:

> "EXP Fasting is one that allows players to select every chance they can and avoid their events or the combats. These avoiding events and the combats are ones that will offer players the EXPs. Life in Adventure is a game that comes with a lot of range specs, and since it is always settled down with luck, there is only one method to have best progression in the game."

**Mechanic**: Beberapa choices/event memberi **0 EXP** (merchant encounters, dialogue-only events, "skip/avoid" options). Player yang pakai EXP Fasting menghindari EXP-generating event untuk dapat:
1. Farm merchant untuk dapat items/elixirs tanpa pushing bar EXP
2. Naik stat tinggi via favorable random events sebelum bar penuh
3. Target specific epilogue yang butuh alignment/stat combo, requires multiple ranks worth of AP, requires avoiding EXP

**Implikasi tool**: AI decision engine WAJIB track:
- `current_exp: int` (0-100, dari OCR atau input user)
- `exp_remaining: int = 100 - current_exp`
- Untuk setiap available choice, label `exp_cost: int` (default 0)
- Bila player pakai EXP Fasting strategy (config flag), prioritaskan `exp_cost=0` choices

### 4.4 EXP & Stat Points Per Level (Post-Patch)

Post-patch update (confirmed dari Reddit): stat points per level berkurang TAPI level up lebih sering → **total stats endgame LEBIH BANYAK**. Ini tradeoff yang signifikan. APK extraction wajib verify exact stat-per-level curve.

---

## 5. Alignment System

> ⚠️ **CRITICAL untuk tool ini**: C2 dari REVIEW_REPORT menandai area ini sebagai salah model. Dokumen sebelumnya pakai linear -100..+100 inferred dari D&D. Web verification (Scribd + Cobraknife + Fandom) menemukan game punya **5 discrete tier**, bukan linear gauge.

### 5.1 Alignment Tiers (5 Discrete)

Game menggunakan 5 tier diskrit (verified via Scribd community guide + Cobraknife traits guide):

| Tier | Affected Range (inferensi via trait sum) | How to Obtain |
|------|------------------------------------------|---------------|
| **Good** | alignment ≥ +60 (approx) | Buy Bright trait (+20), Innately Good (+20), Savior (+20), make only good choices |
| **Moral** | +20 ≤ alignment < +60 | Buy Bright trait, make more good choices than evil |
| **Neutral** | -20 < alignment < +20 | Mixture of choices that considered good or evil |
| **Impure** | -60 < alignment ≤ -20 | Buy Dark trait (-20), make more evil choices than good |
| **Evil** | alignment ≤ -60 (approx) | Buy Dark trait, Innately Evil trait (-20), Butcher trait (Evil alignment -20 + Intimidating +2), make only evil choices |

> ⚠️ **Note**: Range threshold tier adalah INFERENSI dari sum trait deltas (Bright +20, Dark -20, dst). APK extraction WAJIB verify threshold exact angka. Trait deltas sendiri sudah verified dari Cobraknife.

### 5.2 Alignment Shift Mechanics

- Alignment shift berdasarkan pilihan di event. Trait-driven diketahui:
  - **Bright trait** → alignment +20 (purchase dari shop)
  - **Innately Good** → +20
  - **Savior** → +20
  - **Dark trait** → alignment -20 (purchase)
  - **Innately Evil** → -20
  - **Butcher** → alignment -20
- **Per-event shift magnitude**: tidak secara explicit disebut range. Open Question (§14 Q8): APakah range per event -10..+10 atau lebih besar?

### 5.3 Alignment Affects Outcomes

Dari Fandom Wiki epilogues page, alignment affects:

| Condition | Epilogue Type |
|-----------|--------------|
| Die with Good alignment + <35 EXP | "Remembered" |
| Die with Good alignment + 35-80 EXP | "Friendly Neighbourhood Adventurer" |
| Die with Good alignment + ≥80 EXP | "Heroic Memories" |
| Die with Neutral alignment + ≥80 EXP | "Famous Adventurer" |
| Die with Evil alignment + ≥80 EXP | "Celebrated" (verify) |
| High INT + Good alignment | Canon ending requirements |
| Die with Evil alignment + <35 EXP | (specific epilogue, verify di Fandom) |

### 5.4 Alignment in Combat

Tidak ada mention explicit alignment check dalam combat, tapi alignment mempengaruhi **quest outcomes**, **aligned-skill unlocks** (Grace untuk Good, Intimidating untuk Evil), dan **epilogue unlocks**.

### 5.5 Alignment Trait Combinations

Verified via Cobraknife traits guide:
- CHA ≥ 18 + **Moral/Good** alignment → Grace +1/+2 skill
- CHA ≥ 18 + **Impure/Evil** alignment → Intimidating +1/+2 skill
- **Faithful** trait → Holiness +1, Blessing +1 → upgrade ke **Blessed** (Holiness +2) atau **Satanist** (Holiness -2, Curse of Blood +1)

---

## 6. Content Systems

### 6.1 Backgrounds

Background adalah **paid DLC / gem purchase** yang mengubah main storyline.

| Background | Cost | Effect |
|-----------|-------|--------|
| Adventurer's Dream | Free (default) | Starting stat modifier: STR +1 |
| Others | 100 gems each | Different storylines + stat modifiers |

**Confirmed**: "You can also purchase different backgrounds with gems! The category's title is a bit misleading as they affect the main story rather than just your past" (GameGrin review).

Background affects:
- Quest text variations
- Available events
- Unique story paths
- Different epilogues (exclusive_epilogues)
- Starting conditions (items, stats, gold)

### 6.2 Traits

Traits adalah **permanent bonuses** yang dipilih saat character creation atau unlock via gameplay.

**Trait Examples** (from GameGrin + community):
| Trait | Effect |
|-------|--------|
| "Magically Talented" | Use magic without magic equipment |
| "Educated" | Bonus for mages/priests |
| "Talented" | +20 growth per attribute, +50 per talent (very rare, very powerful) |
| "Kind" / "Rational" | Bonus for priests |
| "+10% gold" | Gain 10% more money |
| "Survivor" | Various survival bonuses |

**Trait Mechanics** (from Steam guide):
- Some traits provide stat growth AND stat increases
- Some traits provide unique bonuses
- "Talented" is described as "very powerful" and "very rare"
- Traits affect endgame stats significantly due to growth bonuses

### 6.3 Tales (Alternate Storylines)

Tales adalah **DLC side quests** yang muncul random dalam gameplay.

**Known Tales** (from version history):
| Tale | Added In | Type |
|------|----------|------|
| Forest's Invitation | Early version | Random side quest |
| Demon of the Mine | v1.2.33+ | Random side quest |
| Dance with the Demon | v1.2.34+ | Random side quest |
| Devil's Blood | Community guide | Random side quest |
| The Plague | Community guide | Random side quest |
| Refugees in Rixhelm | Community guide | Random side quest |
| In Search of The Merfolk | Community guide | Random side quest |

**Confirmed**: "Aside from the traits and background, you can also purchase new tales, which are side quests that you will encounter at random in your playthroughs" (GameGrin).

### 6.4 Paths (Cosmetic Rewards)

Path system ditambahkan di v1.2.33+. Mostly **cosmetic rewards** dengan scoring system overhaul.

### 6.5 Rank System

Rank/Score system ditambahkan di v1.2.33+ dengan overhaul besar:
- Leave play as a **score** and compare rankings
- Higher score = better performance
- Score affected by: choices made, battles won/lost, epilogues unlocked

---

## 7. Item & Equipment System

### 7.1 Equipment Stats

Items memiliki stats yang berkontribusi ke combat power:

**Item Example** (from Fandom Wiki):
```
Lemegeton Amulet (One-Handed)
- Stats: 444
- CHA requirement
- Sorcery
- Spellcasting +1
- Requires 100 INT
```

### 7.2 Weapon Types & Scaling

**Weapon scaling dengan stats** (confirmed from Fandom Wiki):
| Weapon Type | Primary Stat | Secondary |
|------------|-------------|-----------|
| Melee weapons | STR | DEX |
| Ranged weapons | DEX | STR |
| Spellcasting | INT | WIS |

### 7.3 Item Properties

- **Attack Type**: Slash, Thrust, Projectile (from item data)
- **Elemental properties**: Fire, Ice, Lightning (based on achievements)
- **Set bonuses**: Unknown, need more data
- **Buy/Sell**: CHA affects vendor prices (-10% per 10 CHA)

---

## 8. Collection & Progression Systems

### 8.1 Diagram/Collection System

**Gems sebagai currency** untuk collection progression:
- Gem per new item/equipment discovered
- Gem per new epilogue unlocked
- Gem per new monster journal entry
- Total: 1 gem each

**Collection rewards**:
- Gacha-like reward system
- Helps afford DLC content (backgrounds, tales)
- No paywall for core gameplay

### 8.2 Monster Journal

Track monster encounters. Each unique monster killed = entry + potential gem reward.

### 8.3 Achievements

**Confirmed achievements** (from Exophase):
- Stat milestones: Reach any stat 25+
- Combat: 30 victories vs strong enemies, 30 vs weak
- Boss kills: Blue Dragon, Red Dragon, White Dragon, Kior, Anton, Erele, Aranea, Berserk
- Events: First fishing, first marriage, first propose fail, first swimming
- Special: Betray Viyork, Battra Tournament win, hatch egg, equip Ganjang/Makya
- DLC-specific: Demon Touch good alignment ending, sneak with elixir

---

## 9. Game Flow & Ending

### 9.1 Run Structure

```
Character Creation → Random Events → Quests → EXP Bar Fills → EPILOGUE → Game Over
                              ↑
                   Choices affect:
                   - Alignment
                   - Stats
                   - Items
                   - Available events
                   - Unlocked epilogues
```

### 9.2 Endings / Epilogues

**Confirmed epilogue categories**:
1. Death endings
2. Success endings
3. Special/secret endings
4. Neutral endings
5. Failure endings

**Example epilogues** (from Fandom Wiki):
| Epilogue | Category | Requirement |
|----------|----------|------------|
| Famous Adventurer | Success | Neutral + ≥80 EXP at death |
| Remembered | Neutral | Good alignment + <35 EXP at death |
| Ghost Hunter | Success | Complete Haunted Manor quest |
| The Last Druid | Success | Complex choice chain in Druid storyline |
| Fruit of Forgiveness | Special | Good alignment + High INT + specific choices |
| Exile | Failure | Specific choice chain in main story |

**Canon endings** (from community consensus):
- "If you get baptized by the cultists eventually Halad will appear to apologize for what she did hinting at 3-13 fruit of forgiveness as the canon ending." (Reddit r/LifeInAdventure)

### 9.3 Game Over Conditions

- **HP reaches 0**: Die → epilogue triggered based on alignment + EXP
- **EXP bar full**: Story ends regardless of quest completion
- **No save scumming** in mobile — each run is permanent

---

## 10. Character Creation

### 10.1 Customization Options

| Option | Description | Cost |
|--------|-------------|------|
| Gender | Minimal effect (some events may differ) | Free |
| Name | Player choice | Free |
| Portrait | Multiple options | Free (or 2 gems for custom) |
| Background | Changes main story | Free + DLC |
| Trait | Permanent bonus | Free (from pool) |
| Stats | 4 points to distribute | Free |
| Starting Equipment | Choose gear | Free |

### 10.2 Character Randomization

- Free random character option
- Custom character costs 2 gems

---

## 11. Monetization & IAP

### 11.1 Free Content

- Full game story is free
- All core quests and events accessible
- Random encounters available

### 11.2 Paid Content (Gems)

| Item | Cost |
|------|------|
| 30 Gems | $0.99 |
| 150+15 Gems | $4.99 |
| 300+45 Gems | $8.99 |
| 900+180 Gems | $26.99 |
| 1500+375 Gems | $44.99 |
| Join Adventurer's Guild | $4.99 (skip fights, 1 revive, no ads) |
| Forest's Invitation | $4.99 (Tale DLC) |
| Dance with the Demon | $4.99 (Tale DLC/Path) |
| Backgrounds | 100 gems each |

### 11.3 Free Gems Sources

- Watch ads
- Collect new items/equipment
- Unlock new epilogues
- Monster journal entries

---

## 12. Difficulty Levels

Added in v1.2.33+:
- **Normal Mode**: Default difficulty
- **Hard Mode**: Higher difficulty + new scoring system

---

## 13. Multiplayer / Social

- **Game Center** (iOS): Leaderboards
- **Google Play Games** (Android): Leaderboards, achievements
- **No multiplayer combat** — purely single player

---

## 14. Language Support

| Language | Status |
|----------|--------|
| English | Full |
| Korean | Full |
| Indonesian | Added v1.2.42 |
| Spanish | Supported |
| Italian | Supported |
| Portuguese | Supported |

---

## 15. Summary: Mechanics That Affect AI Recommendations

Dari semua research, berikut mechanics yang **PALING KRUSIAL** untuk AI decision engine:

### Critical (Must Model)
1. **Stat checks**: D20 + stat_modifier + power_points vs effective DC → success/fail outcomes (§2.4, hybrid bukan D&D pure)
2. **EXP bar**: Pilihan mengisi EXP → **max 100** → adventure end. **EXP Fasting** adalah meta strategi utama yang harus di-support (§4)
3. **Alignment**: 5 discrete tier (Good/Moral/Neutral/Impure/Evil) → menentukan epilogue unlock + aligned-skill unlock (§5)
4. **Background**: Mengubah quest text + available events + exclusive epilogues
5. **Equipment power**: Power points menentukan combat odds range + minimum/maximum achievable roll outcome

### Important (Should Model)
6. **Trait bonuses**: Passive bonuses dari traits (Bright/Dark/Faithful/etc affects alignment + skills)
7. **Stat thresholds**: +bonuses di 13, 20, 27 (verified via Fandom Wiki Stats page)
8. **Gold economy**: CHA affects prices (-10% per 10 CHA)
9. **Tales**: Random DLC quests
10. **Companions**: Fiana mentioned (specific strategies needed)

### Nice-to-Know (Can Model)
11. **Dice outcomes**: Roll 20 = instant win, Roll 1 = worst
12. **Collection/diagram**: Gem hunting progression
13. **Achievement milestones**: Stat 25+ unlock
14. **Hard mode**: Different scoring

---

## 16. Open Questions (Need APK Extraction to Verify)

| # | Question | Priority | Verified? |
|---|----------|----------|-----------|
| Q1 | Exact damage formula — STR/DEX contribution? | High | ❌ |
| Q2 | CON → HP formula? | High | ❌ |
| Q3 | Spellcasting → INT formula? | Medium | ❌ |
| Q4 | Enemy AC/defense formula? | Medium | ❌ |
| Q5 | Level-up EXP curve? | Medium | ❌ |
| Q6 | Item drop rates? | Low | ❌ |
| Q7 | Random encounter weighted probability? | Medium | ❌ |
| Q8 | Alignment shift magnitude per choice? | High | ❌ |
| Q9 | Exact stat points per level (before/after patch)? | Medium | ❌ |
| Q10 | Companion Fiana mechanics — how does she help? | Medium | ❌ |
| Q11 | Alignment threshold exact angka per tier (Good ≥ 60? etc.) | High | ❌ (currently inferred from trait sum) |
| Q12 | Stat tier ceiling (>27) — ada bonus lebih tinggi? | Medium | ❌ |

### Already Verified via Tavily/Exa Web Search (2026-07-06)

| Claim | Verified Value | Source |
|-------|----------------|--------|
| EXP cap | 100 | LDPlayer guide, Scribd guide 607016681, Fandom Wiki Epilogues |
| Rank milestones | 10/20/35/55/80 | Scribd guide |
| EXP per event type | Enemy=1, random=1-2, major=2-3 | LDPlayer + Scribd |
| Stat range | 1-27+ (Super +2 unlock at 27) | Fandom Stats page |
| Stat threshold bonus combos | 13/20 for +1/+2 | Fandom Stats page |
| Alignment tiers | 5 discrete (Good/Moral/Neutral/Impure/Evil) | Scribd + Cobraknife |
| Alignment trait deltas | Bright +20, Dark -20, Innately Evil -20, Savior +20 | Cobraknife |
| Super Strength tier | STR 18 → +1 (Physical +10%), STR 27 → +2 (Physical +20%) | Fandom Wiki |
| Grace skill | CHA ≥ 18 + Moral/Good → Grace +1/+2 | Fandom |
| Intimidating skill | CHA ≥ 18 + Impure/Evil → Intimidating +1/+2 | Fandom |
| Toughness combo | STR + CON ≥ 13 → +1, ≥ 20 → +2 (Defense +10/20%) | Fandom |
| Weapon Mastery combo | STR + DEX ≥ 13 → +1, ≥ 20 → +2 (Physical Attack +10/20%) | Fandom |

---

*End of GAME_MECHANICS.md*
*v1.1 patched per REVIEW_REPORT.md C1 + C2 + C3 + M1*
