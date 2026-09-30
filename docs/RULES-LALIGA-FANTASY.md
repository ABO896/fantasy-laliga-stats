# Official LaLiga Fantasy Rules

**Retrieved:** 2026-08-06
**Status:** current
**Applies to:** LALIGA Fantasy (DAZN) — public and private leagues, standard mode

> This document is the **single source of truth** for every squad rule the app enforces.
> The rule engine loads its caps, quotas and formation list from here (or from a machine-readable
> file derived from here) — never from constants scattered through validation code.
>
> **A mid-season rules change must be a dated edit to this file**, recorded in the Change log at
> the bottom, not a silent constant change somewhere in the codebase.

---

## Which game this is

**There are several unrelated games called some variant of "LaLiga Fantasy".** This app targets
**the official one operated by LaLiga itself** — the app branded *LALIGA Fantasy* (currently
sponsored by DAZN, previously by MARCA). Fantasy MARCA, Biwenger, Comunio, Futmondo and the rest are
different games with different rules, and none of their values belong in this document.

Identity is confirmed by LaLiga's own legal terms, which govern *"the LALIGA Fantasy game in its app
and web versions"*, declare it *"the exclusive property of LaLiga Group International, S.L."*, and
name **`support@laligafantasy.zendesk.com`** as the support address
([laliga.com — Conditions of Use, Fantasy](https://www.laliga.com/en-GB/legal/laliga-fantasy/conditions-of-use?slug=condiciones-de-uso-fantasy)).
That is LaLiga's own site naming the exact help centre this document quotes, which is what makes it
the operator's documentation rather than a fan or competitor site.

DAZN describes the same game as *"el juego oficial de mánager de fútbol de LALIGA EA Sports"*. DAZN
is a **sponsor**, not a separate game — LaLiga's terms list DAZN Spain among the partners running
sponsored leagues, alongside Mahou, Cadena SER and others. So "LaLiga Fantasy DAZN" and "LaLiga
Fantasy" are the same product, and a rule found under either name applies here.

### Two modes inside the official app — a sharper discriminator than any above

**Recorded 2026-08-08, from the owner.** Distinguishing this game from Fantasy MARCA or Biwenger is
the easy half. The harder half is that **the operator ships more than one mode under its own brand**,
and signing up presents a choice between them:

- **LALIGA Fantasy *Manager*** — the traditional season-long game: you own a squad, buy and sell on a
  market, hold a cash balance, and field an XI each jornada. **This is the game this app targets, and
  every value in this document belongs to it.**
- **LALIGA Fantasy** (and the *Ligas Fantásticas* mode) — a separate, lighter format that does not
  share the squad-and-market model.

This matters more than the competitor-game distinction because **the two modes share one help
centre**, so a "Reglas del juego" article is not automatically about our game. A confirmed instance:
[¿Cómo elegir jugadores para mi alineación en cada jornada?](https://laligafantasy.zendesk.com/hc/es/articles/360013997060)
sits in the same category and describes **Ligas Fantásticas**, a daily-reset format — it is *not*
evidence about lineup rules in Manager, and reading it as such would import a wrong deadline model.

Supporting evidence that the values here are Manager's: the Premium article this document quotes
throughout has the slug `How-do-I-create-a-Premium-League-in-**Fantasy-Manager**`, and the squad cap,
debt limit and formation set all come from that same help centre.

**Sanity check before trusting a help-centre article:** does it describe owning a squad, a market and
a cash balance? If it describes picking players fresh each day, or says nothing about a market, it is
probably the other mode.

**Sanity check before trusting any future source:** does it trace back to
`laligafantasy.zendesk.com`, `fantasy.laliga.com`, or `laliga.com`? If it describes a different
budget, a different squad cap, or leagues of a different size, the likeliest explanation is that it
documents a *different game*, not that the rules changed.

---

## Source

The owner locked the source of squad rules to the **official game**, not to third-party analytics
sites such as analiticafantasy.com (PROJECT-BRIEF "Hard constraints"; squad-builder spec D-10).

**`https://fantasy.laliga.com/` itself carries no rules.** It was checked on 2026-08-06 and is an
app-download / promotional landing page: no rules, no help section, no `/normas`, `/como-jugar` or
`/ayuda` route (all return 404). The same is true of `https://www.laliga.com/en-GB/apps/laligafantasy`.

The official rules are published in the game's own **help centre**, operated by the game itself and
linked from inside the app:

**`https://laligafantasy.zendesk.com/hc/es/categories/360000715714-Reglas-del-juego`** — the
"Reglas del juego" category, 45 articles.

This is the operator's own documentation, not a competitor or fan site, so it satisfies the locked
constraint. Every value below is quoted from it, with the exact article URL and that article's own
last-updated date.

> **Read the Spanish (`es`) locale, not English.** Spanish is the source language — the articles
> carry `"source_locale": "es"` and the English versions are translations. They are not merely
> stale, they are sometimes *shorter*: the English formations article omits the sentence
> *"Si perteneces a una Liga Fantasy Premium, tendrás a tu disposición más esquemas estratégicos
> exclusivos"* entirely, which is precisely the sentence that would have flagged the Premium
> formation set on the first pass. Several Spanish articles also carry newer `updated_at` dates
> than their English counterparts. Always verify in `es`.

> Retrieval note: the Zendesk web UI returns HTTP 403 to non-browser clients. The articles were read
> through the public help-centre JSON API:
> `https://laligafantasy.zendesk.com/api/v2/help_center/es/articles/<id>.json`, and the category
> listing at `.../es/categories/360000715714/articles.json?per_page=100`.
> Re-verify with the same method.

### Corroboration against non-official sources

Third-party write-ups were consulted afterwards **only to find gaps in the official docs**, never as
a source of values. Doing so surfaced two things the first pass had missed, both then confirmed
against operator articles and recorded below: the **Premium-league formations**, and a **conflicting
squad-size figure**.

One conflict is **resolved against DAZN**. Its 2025/26 rules article states *"Plantillas con un
mínimo de 14 y un máximo de 25 jugadores"*
([dazn.com](https://www.dazn.com/es-ES/news/f%C3%BAtbol/laliga-fantasy-normas-reglas-sistema-puntuacion/1r2zkzqr0aocp1x1vnxx6zzym6)),
i.e. **25**, not 24. The operator says **24** in three independent Spanish articles, the most recent
updated **2026-08-01** and describing it as a limit the system actively enforces on bidding:

> "…o porque con todas las ofertas que tienes realizadas superarías **el límite de 24 jugadores
> permitido**."
> — [¿Por qué no puedo hacer una oferta o una puja por un jugador?](https://laligafantasy.zendesk.com/hc/es/articles/115002401934) (updated 2026-08-01)

DAZN is a sponsor publishing a journalistic summary, not the operator. **24 is correct**; the DAZN
figure is wrong or describes an earlier season.

The **minimum of 14** in that same DAZN sentence is not stated anywhere in the operator's docs — the
help centre only says 14 players are *assigned* at league start, not that you may never hold fewer.
**Unconfirmed, therefore not enforced.**

A note on why the operator's docs get the benefit of the doubt but not blind trust: they contradict
themselves elsewhere. The [Coach](https://laligafantasy.zendesk.com/hc/en-us/articles/6607113048978-Coach)
article scores a coach +3/+1/−1 for win/draw/loss, while the
[Premium League](https://laligafantasy.zendesk.com/hc/en-us/articles/4415018495890-How-do-I-create-a-Premium-League-in-Fantasy-Manager)
article says 5/2/0. Coaches are out of scope here, so it costs nothing — but it is a concrete reason
this app consumes scraped points rather than recomputing scoring from published rules.

---

## The rules the app enforces

### Squad size

| Rule | Value |
|---|---|
| **Maximum players in a squad** | **24** |
| Starting squad when joining a league | 14 players, assigned automatically |
| Players fielded per matchday | exactly 11 |

> "You can have a maximum of 24 players per team."
> — [How many players can I have in my squad?](https://laligafantasy.zendesk.com/hc/en-us/articles/115002390493-How-many-players-can-I-have-in-my-squad) (updated 2025-03-18)

> "The bench will be made up of those players from your squad that have not been included in your
> starting eleven, bearing in mind that your squad will consist of a maximum of **24** players."
> — [Premium leagues](https://laligafantasy.zendesk.com/hc/en-us/articles/4414999058450-Premium-leagues) §3.2 (updated 2026-02-27)

> "…superarías el límite de **24** jugadores permitido." … "tienes en plantilla **24** jugadores que
> habrás hecho por clausulazos mientras esa puja estaba activa, por lo tanto superas el límite máximo
> de jugadores."
> — [¿Por qué no puedo hacer una oferta o una puja por un jugador?](https://laligafantasy.zendesk.com/hc/es/articles/115002401934) (updated 2026-08-01)

Three independent operator statements, the newest describing 24 as an actively enforced limit, is
why 24 wins over DAZN's 25. See "Corroboration" above.

That same article is also direct confirmation that **the two constraints this app checks before an
add are the two the real game checks before a bid** — nothing else:

> "Si no te deja hacer una puja el sistema es porque: o has superado el límite de endeudamiento
> permitido, o porque con todas las ofertas que tienes realizadas superarías el límite de 24
> jugadores permitido."

(The real game additionally counts *pending bids* toward the 24. This app models a squad, not a bid
book, so it counts only owned players — a deliberate, documented simplification.)

> "You start LaLiga with a budget of 100 million and 14 random players."
> — [How do I create my team to start playing?](https://laligafantasy.zendesk.com/hc/en-us/articles/115002401874-How-do-I-create-my-team-to-start-playing)

> "Only the 11 players featuring in your saved line-up will be awarded points." … "If you have a
> negative balance or do not have 11 players on the pitch when the system registers your saved
> information, you will not receive the points that your players amass."
> — [Rulebook](https://laligafantasy.zendesk.com/hc/en-us/articles/360025679853-Rulebook) (updated 2025-07-03)

**Coaches** are a separate allowance and do **not** consume the 24 player slots: max 2 per squad
([Coach](https://laligafantasy.zendesk.com/hc/en-us/articles/6607113048978-Coach) §1.3). Coaches are
out of scope for this app — the scraper does not ingest them (`positionId` 5 is excluded, see
PROJECT-BRIEF).

**Loaned-in players** also do not occupy squad places (max 3 loans;
[Loans](https://laligafantasy.zendesk.com/hc/en-us/articles/7416404956434-Loans) §2.5, §2.8).
Loans are out of scope for v1 of the squad builder.

### Valid formations

Written **DEF-MID-FWD**. The goalkeeper is implicit in the official notation and is always exactly 1.
There are **two sets**, and which apply depends on the league.

**Standard — always available, in every league:**

| Formation | GK | DEF | MID | FWD |
|---|---|---|---|---|
| 3-4-3 | 1 | 3 | 4 | 3 |
| 3-5-2 | 1 | 3 | 5 | 2 |
| 4-3-3 | 1 | 4 | 3 | 3 |
| 4-4-2 | 1 | 4 | 4 | 2 |
| 4-5-1 | 1 | 4 | 5 | 1 |
| 5-3-2 | 1 | 5 | 3 | 2 |
| 5-4-1 | 1 | 5 | 4 | 1 |

> "LALIGA FANTASY te permite optar por algunos de los esquemas tácticos más habituales del fútbol
> internacional… 3-5-2 / 3-4-3 / 4-4-2 / 4-3-3 / 4-5-1 / 5-4-1 / 5-3-2. **Si perteneces a una Liga
> Fantasy Premium, tendrás a tu disposición más esquemas estratégicos exclusivos.**"
> — [¿Puedo jugar con cualquier esquema estratégico?](https://laligafantasy.zendesk.com/hc/es/articles/115002390733) (updated 2025-05-28)

That final sentence **does not exist in the English translation** of the same article. It is the
pointer to the premium set, and missing it is what made the first pass of this document incomplete.

**Premium — five additional shapes, available only in a Premium league with the feature switched on:**

| Formation | GK | DEF | MID | FWD |
|---|---|---|---|---|
| 3-3-4 | 1 | 3 | 3 | 4 |
| 3-6-1 | 1 | 3 | 6 | 1 |
| 4-2-4 | 1 | 4 | 2 | 4 |
| 4-6-0 | 1 | 4 | 6 | 0 |
| 5-2-3 | 1 | 5 | 2 | 3 |

> "Premium Leagues enable you to select from the following new formations: 3-6-1 / 3-3-4 / 4-2-4 /
> 4-6-0 / 5-2-3"
> — [How do I create a Premium League?](https://laligafantasy.zendesk.com/hc/en-us/articles/4415018495890-How-do-I-create-a-Premium-League-in-Fantasy-Manager) (updated 2025-07-03)

> "A playing system considered as premium will be valid as long as the administrator has this feature
> configured in the league settings. If this option has been deactivated, any user with a Premium
> formation selected will not be able to score points."
> — [Premium leagues](https://laligafantasy.zendesk.com/hc/en-us/articles/4414999058450-Premium-leagues) §1.2

A Premium league is a paid upgrade of a private league, its features are individually toggleable by
the league admin, and it cannot be converted back. So premium formations are **a property of the
owner's league, not of the game** — the app must be told, not assume. See "Decisions this forces"
below.

**Formations are not the only Premium feature.** The same upgrade also gates **captain** (doubles a
player's matchday points), **bench** (up to four substitutes, one per position the formation fields),
coach, loans and the Ideal XI bonus. And they are toggled *separately*:

> "Can I deactivate Premium League features? Yes, you can activate or deactivate features of your
> Premium League whenever you wish."
> — [How do I create a Premium League?](https://laligafantasy.zendesk.com/hc/en-us/articles/4415018495890-How-do-I-create-a-Premium-League-in-Fantasy-Manager)

So the app needs **a setting per feature**, not one master "premium" switch — a league can have the
extra formations on and the captain off. Captain and bench matter from Phase 3 (lineup recording);
coach, loans and Ideal XI remain out of scope.

Mapped onto the app's normalized position vocabulary (`storage/models.py`): `POR` = GK, `DEF` = DEF,
`MED` = MID, `DEL` = FWD.

### Position quotas

**The official rules publish no squad-level per-position quota.** There is no stated minimum or
maximum number of goalkeepers, defenders, midfielders or forwards you may *own* — only the 24-player
squad cap and the constraint that you must be able to field one of the allowed formations.

Everything below is therefore **derived from the formation tables above**, not invented, and applies
to the **starting XI**, not to squad ownership. The two columns differ because the premium set is
strictly wider at both ends:

| Position | Min in XI (standard) | Max in XI (standard) | Min in XI (+premium) | Max in XI (+premium) |
|---|---|---|---|---|
| POR (GK) | 1 | 1 | 1 | 1 |
| DEF | 3 | 5 | 3 | 5 |
| MED | 3 | 5 | 2 | 6 |
| DEL | 1 | 3 | **0** | 4 |

The **minimum squad composition able to field any legal XI** is the union of the minima:

- **Standard only:** 1 POR, 3 DEF, 3 MED, 1 DEL (8 players)
- **Premium enabled:** 1 POR, 3 DEF, 2 MED, 0 DEL (6 players) — because `4-6-0` fields no forward at
  all and `4-2-4` needs only two midfielders

This is exactly why the premium set cannot be quietly ignored: with it enabled, a squad holding zero
forwards is perfectly able to field a legal XI, and an app hardcoded to the standard seven would tell
the owner the opposite.

> This is exactly the split the squad-builder spec's D-07 requires: *squad legality* (size ≤ 24,
> budget) and *starting-XI feasibility* (which of the seven formations are still reachable) are
> genuinely different questions, because the official rules constrain the XI and not the squad.
> Do not collapse them into one check.

### Lineups, deadline, captain and bench

**Retrieved 2026-08-08**, Spanish locale, for Phase 3 (lineup recording). All 66 Spanish help-centre
articles were swept for `alineaci` / `once inicial` / `banquillo` / `capitán`, so the articles cited
here are the complete set that says anything on these topics.

#### The deadline — one per jornada, not one per player

| Rule | Value |
|---|---|
| When the lineup locks | At the **start of the jornada** — the kickoff of its first match |
| Granularity | **One instant for the whole lineup.** Players do *not* lock individually when their own club kicks off |
| Exact clock time | **Not published.** The docs say "before the jornada starts" and nothing more precise |
| If you never change it | The **last saved** lineup carries over and scores normally |

> "Los futbolistas de tu equipo que suman puntos durante la jornada en activo son aquellos que
> aparecen en **la última alineación guardada justo antes del inicio de dicha jornada**, te
> recomendamos guardar dicha alineación al menos una hora antes del inicio del primer partido de la
> jornada."
> — [¿Qué futbolistas de mi equipo suman puntos durante la jornada?](https://laligafantasy.zendesk.com/hc/es/articles/115002390473) (updated 2026-02-27)

> "**Antes del comienzo de cada jornada, el juego registrará la alineación y los datos guardados por
> cada manager.** … Si tu saldo es negativo o no tienes 11 jugadores en el campo **en el momento en
> el que el sistema registra los datos guardados**, no recibirás los puntos que tus jugadores
> consigan durante el transcurso de toda la jornada."
> — [Reglamento](https://laligafantasy.zendesk.com/hc/es/articles/360025679853) (updated 2025-07-03)

The lineup is therefore a **snapshot taken at one instant**. Corroborating that the jornada is a
single boundary rather than a per-match one: the release-clause market "se cierra 24 horas antes de
empezar una jornada", and loan offers close "hasta 24 horas antes del inicio de una jornada" — every
timing rule in the game keys off the same boundary.

⚠️ **The operator's two "save early" figures disagree, and neither is the lock.** The article titled
*¿Cuál es la fecha tope para guardar la alineación?*
([115002402014](https://laligafantasy.zendesk.com/hc/es/articles/115002402014), updated 2026-02-27)
says **30 minutes**; article 115002390473 above says **one hour**. Both are worded `te recomendamos`
— recommendations, not the cutoff. **This app does not adopt either as a deadline** (Phase 3 spec,
LN-08): inventing a stricter cutoff than the game enforces would refuse correct information.

#### Scoring zero for a jornada

Two conditions zero out a whole jornada, both evaluated at the registration instant:

> "**No se puede tener más de 11 jugadores. En el caso de tener 10 o menos no puntuarás en esa
> jornada.**"
> — [¿Puedo tener más de 11 jugadores…?](https://laligafantasy.zendesk.com/hc/es/articles/360014056059) (updated 2025-03-18)

> "…para puntuar en una jornada debes tener **saldo positivo y 11 jugadores alineados**."
> — [¿Qué necesito para puntuar cada jornada?](https://laligafantasy.zendesk.com/hc/es/articles/360025541414) (updated 2025-03-18)

The second is the *consequence* side of the 20% debt limit recorded under Budget below: debt inside
the allowance is legal, and it costs you the entire matchday if it is still negative when the
jornada registers.

#### The position-change trap

> "Si un manager no hace cambios en su alineación de ningún jugador, incluyendo el que cambió de
> posición y no le fichan a ningún jugador que tenga alineado, ese manager **puntuará la jornada
> correctamente con el jugador alineado en la posición antigua**, hasta que haga algún cambio en la
> alineación."
> — [Cambios de posición de jugadores](https://laligafantasy.zendesk.com/hc/es/articles/6594850326162) (updated 2026-02-27)

A player reclassified mid-season leaves a saved lineup scoring normally **only until you touch
anything**. Any edit — or a rival buying one of your XI — re-validates it, at which point it becomes
*alineación indebida* and scores **zero**, while the UI still shows eleven players. This app observes
position changes already (`Player.position` is upserted every scrape), so Phase 3 warns about it
(spec LN-27).

#### Captain — Premium only

| Rule | Value |
|---|---|
| Multiplier | **×2**, applied to positive **and negative** scores alike |
| Eligibility | Must be one of the **starting eleven** |
| Deadline | Before the jornada starts; a later selection is ignored |
| Mandatory? | **No** — optional |
| Only pays if | The captain actually plays minutes; a bench replacement does **not** inherit the ×2 |
| Lost when | You loan the player out, or the admin disables the captain feature before the jornada |

> "**2.3** …se podrá asignar el rol de capitán **a uno de los integrantes del once inicial**."
> "**2.6** …Un capitán **solo conseguirá doble puntuación, si disputa minutos en el encuentro. Si es
> sustituido por un jugador del banquillo, el nuevo jugador no conseguirá la doble puntuación.**"
> — [Ligas premium](https://laligafantasy.zendesk.com/hc/es/articles/4414999058450) (updated 2026-02-27)

> "…verá **multiplicada por dos (x2) su puntuación durante la jornada independientemente de los
> puntos que consiga, pudiendo ser positivos o negativos**."
> — [¿Cómo creo una liga Premium…?](https://laligafantasy.zendesk.com/hc/es/articles/4415018495890) (updated 2025-07-03)

No position restriction is stated — a goalkeeper captain is nowhere forbidden.

#### Bench — Premium only

| Rule | Value |
|---|---|
| Maximum substitutes | **4** — one per position, **and only positions the chosen formation fields** |
| Mandatory? | **No** — optional, and may be partial |
| Substitution rule | **Same position only.** A goalkeeper cannot replace a defender |
| Trigger | The starter **plays zero minutes** |
| Uncovered position | That starter simply cannot be substituted |
| Lost when | The admin disables the bench feature before the jornada |

> "**3.1** Se podrá disponer como **máximo de 4 jugadores en el banquillo, uno por cada una de las
> posiciones disponibles**: Portero, Defensa, Centrocampista, Delantero; **teniendo en cuenta la
> formación seleccionada** para tu equipo. Por ejemplo: **una formación 4-6-0 que no dispone de
> delanteros, no permitirá disponer de un delantero en el banquillo.**"
> "**3.4 ¿Puede un portero sustituir a un defensa que no ha puntuado?** **No.** …**sustituirán a
> aquellos jugadores de su misma posición**."
> "**3.5** No será necesario cubrir todas las posiciones del banquillo para puntuar…"
> — [Ligas premium](https://laligafantasy.zendesk.com/hc/es/articles/4414999058450) §3 (updated 2026-02-27)

> "**Banquillo** — Podrás elegir hasta un máximo de cuatro jugadores suplentes, uno por posición…
> los cuales **se utilizarán en el caso de que un jugador de tu alineación titular no dispute ningún
> minuto**."
> — [¿Cómo creo una liga Premium…?](https://laligafantasy.zendesk.com/hc/es/articles/4415018495890) (updated 2025-07-03)

⚠️ **The operator contradicts itself on the trigger.** §3.4's *heading* says
*"un defensa **que no ha puntuado**"* (who did not *score*), while its own body and article
4415018495890 both say **no minutes played**. Two of three statements say minutes, so minutes is the
better reading — recorded here as the adopted one, and recorded as *not self-consistent in the
source*, because Phase 7's regret analysis will depend on it and should not have to rediscover the
ambiguity. A player who plays and scores zero is **not** described as substitutable.

### Budget

| Rule | Value |
|---|---|
| Starting cash when joining a league | €100,000,000 |
| **Fixed squad-value cap** | **none — no such rule exists** |
| Debt limit | 20% of the value of your squad |
| Consequence of negative balance at matchday start | you score 0 points that matchday |
| Cash earned per Fantasy point | €100,000 |
| Immediate sale ("venta inmediata") proceeds | 50% of the player's market value |

> "each manager is assigned a full 14-strong squad and a budget of €100m." … "You may only incur
> debts of up to 20% of the value of your team." … "For every point you earn, you will receive
> €100,000 in your budget."
> — [Rulebook](https://laligafantasy.zendesk.com/hc/en-us/articles/360025679853-Rulebook)

> "The debt limit is 20% of the value of your squad. This means that the maximum offer you can make
> for a player is all of the money that you have in cash plus 20% of the total value of your squad.
> … It is not possible to take on debt to pay a release-clause swoop."
> — [Can I keep a negative balance?](https://laligafantasy.zendesk.com/hc/en-us/articles/360007533594-Can-I-keep-a-negative-balance)

**This is the most consequential finding for the builder.** LaLiga Fantasy has **no salary-cap-style
budget ceiling**. €100m is *opening cash*, not a cap on squad value, and it is not even constant —
managers whose 14 assigned players are worth less than the league average are given extra:

> "Should you receive a team with a market value that is considerably lower than the calculated
> average, you will be assigned a bigger budget so as to ensure that all players start on an equal
> footing. This additional budget is calculated by using specific formulas and criteria…"
> — [Rulebook](https://laligafantasy.zendesk.com/hc/en-us/articles/360025679853-Rulebook)

Cash thereafter moves with purchases, sales, release-clause swoops, and €100k per point earned.
There is no published formula that would let the app reconstruct a manager's true balance.

**Consequence:** ~~the app's budget model must be **user-entered cash balance**, not
`cap − Σ purchase prices`.~~ **No longer true as of 2026-08-21.** The budget ledger that stored a
user-entered cash balance was cut — the game-rule finding above (no fixed cap, an unpublished
per-manager opening figure, cash moving via an unobservable claimable daily reward) is exactly
why: it made the balance underivable by the app, not just inconvenient to derive, and a
one-directional drift was the *expected* state of a correctly-functioning ledger rather than a
bug. See `ROADMAP.md`'s Phase 2 tombstone. See "Decisions this forces" below for what replaced it.

#### Cash movements the app cannot observe

**Reported by the owner 2026-08-08 from the live app; not yet confirmed against an operator article.**
Recorded at this confidence deliberately — the ledger's whole design assumes movements it cannot see,
so an unverified movement is still actionable, but it must not be mistaken for a quoted rule.

| Movement | Direction | Notes |
|---|---|---|
| **Daily reward, €100,000** | **In**, *if claimed* | Claimable each day; **skipping it forfeits it**. Not automatic. |
| **Shielding** (*escudo* — protection from a release-clause swoop) | Out | Not mentioned anywhere in the operator's docs retrieved so far. |
| **Increasing a player's release clause** | Out | The clause mechanics themselves are already recorded as not enforced (below). |
| **Immediate sale** (*venta inmediata*) | In | 50% of market value — this one *is* quoted, in the Budget table above. |

**Why the daily reward is the worst of these for the ledger.** It is the highest-frequency movement
in the game — potentially 365 a season against roughly 38 points-income events — and it is
*underivable in principle*, because whether you claimed on a given day is a fact that exists nowhere
but in your own behaviour. Every other unobserved movement at least corresponds to an event with a
record. This makes a steady, one-directional drift the expected state of the ledger rather than a
symptom of a bug, which is a distinction BUDGET-05's drift warning currently cannot draw. See
`docs/superpowers/ROADMAP.md` → Known issues.

### Per-club cap

**None.** The official rules state no limit on how many players from the same real club a squad may
hold. The only stated eligibility limit is affordability and market availability:

> "You can sign any player who is on the MARKET and who you can afford."
> — [Can I sign any player?](https://laligafantasy.zendesk.com/hc/en-us/articles/115002390693-Can-I-sign-any-player)

Per the squad-builder spec: *"If they don't, do not invent one."* **Do not implement a per-club cap.**

---

## Rules deliberately not enforced by this app

Documented so nobody later mistakes their absence for an oversight.

| Official rule | Why not enforced |
|---|---|
| Bids may not be below market value | The app models a squad, not the transfer market. |
| Release clauses (1M floor; 166% of market value above 1M; 2:1 increase cost; 2-week lock; clause window closes 24h before matchday) | Market mechanics, out of the builder's scope. |
| Loans (max 3, one matchday, don't occupy squad places) | Out of scope for v1. |
| Coaches (max 2, don't occupy squad places, not scraped) | Out of scope; the scraper excludes them. |
| ~~Lineup save deadline, captain, bench, position-change invalidation~~ | **No longer true as of 2026-08-08.** This entry described spec D-07's original scope, where the app reported XI *feasibility* and never selected a lineup. Phase 3 reverses that scope — see "Lineups, deadline, captain and bench" above, and `docs/superpowers/specs/2026-08-08-phase-3-lineup-recording-design.md`. D-07's *architecture* is untouched: squad legality and XI legality remain separate layers. |
| Auto-substitution of a starter who played no minutes | Needs per-player **minutes**, which are not scraped. The bench is recorded as *selected*, never as *applied* (Phase 3 spec). |
| Shielding (*escudo*) and release-clause increases | Market mechanics, out of the builder's scope — but they move cash, so they are recorded above as out-of-band ledger movements. |
| Scoring system (full points table is in the Rulebook) | The app consumes scraped points; it does not recompute them. |

---

## Decisions this forces on the squad builder

These resolve open questions in `docs/superpowers/specs/2026-08-06-squad-builder-design.md`.

1. **Budget model → user-entered balance (spec open question 1).** A derived
   `cap − Σ purchase prices` model is not merely inferior here, it is *incoherent*: there is no cap,
   the €100m starting figure varies per manager by an unpublished formula, and cash accrues from
   points and sales. ~~The app stores a user-entered cash balance and validates a purchase against
   `cash + 0.20 × squad_market_value`.~~ **No longer true as of 2026-08-21** — the budget ledger
   that stored and validated against that balance was cut; see `ROADMAP.md`'s Phase 2 tombstone.
   Purchase price stays a stored column per D-02 — it is needed for profit/loss in the later trends
   work, just not as the basis of a budget check any more.

2. **"Over budget" means over the debt limit, not over a cap.** The refusal message (D-05) is
   framed as *"€2.1M beyond your debt limit (cash €4.0M + 20% of squad value €38.5M = €11.7M)"*,
   not *"over the €100M cap"*. There is no €100M cap.

3. **A negative balance is legal but costly.** The rules permit debt up to 20%; they penalise it by
   zeroing the matchday. So debt inside the limit is a **warning state**, not a violation — this is
   a third state alongside spec D-09's *incomplete* and *illegal*. Debt beyond 20% is a violation.

4. **No per-club cap** (spec open question 4) — resolved: not in scope, do not invent.

5. **Squad-level position quotas do not exist** — SQUAD-02's "position quotas" are enforced as
   *XI feasibility against the allowed formations*, plus the 24-player squad cap. This is the
   D-07 layering, and the official rules independently confirm it is the right shape.

6. **Premium formations are a setting, defaulting to off.** Which formation set applies is a property
   of the owner's league that no amount of reading the rules can settle. The engine therefore takes
   the enabled set as input, the rules file marks each formation `"premium": true|false`, and a
   single setting (`premium_formations_enabled`, default `false`) selects between them. Default off
   is the conservative direction: with premium wrongly *on*, the app would call a forward-less squad
   fieldable when the league would score it zero. With premium wrongly *off*, it under-reports
   reachable formations — visible, harmless, and one toggle away from correct.

---

## Change log

| Date | Change | By |
|---|---|---|
| 2026-08-06 | Initial retrieval from the official LaLiga Fantasy help centre. Recorded squad cap 24, starting 14 + €100m, seven formations, 20% debt limit, €100k/point; confirmed **no fixed budget cap**, **no per-club cap**, **no squad-level position quotas**. | — |
| 2026-08-07 | Cross-checked against non-official write-ups to find gaps. Added the **five Premium-league formations** (3-3-4, 3-6-1, 4-2-4, 4-6-0, 5-2-3) and the derived XI minima they change — notably `4-6-0` permitting zero forwards. Re-confirmed squad cap 24 from a second operator article, and recorded DAZN's conflicting "25" and unconfirmed "minimum 14" as explicitly not adopted. | — |
| 2026-08-08 | Retrieved the **lineup rules** for Phase 3, sweeping all 66 Spanish articles. Recorded: the deadline is **one instant per jornada** (the first match's kickoff), never per-player; the two "save early" figures (30 min / 1 h) are non-binding recommendations that disagree with each other; the two **zero-score conditions**; the **position-change trap**; and the **captain** and **bench** rules verbatim — the latter confirming the previously *derived* "one substitute per fielded position", including the operator's own `4-6-0` example, plus three facts not previously held (the bench is optional and may be partial, substitution is same-position only, and the trigger is zero *minutes*, on which the operator contradicts itself). Recorded that the app now **does** save lineups, retiring that row of the not-enforced table. | — |
| 2026-08-08 | Recorded the **two modes inside the official app** (*Manager* vs *LALIGA Fantasy* / *Ligas Fantásticas*) as a sharper identity discriminator than the competitor-game distinction — they share one help centre, and article 360013997060 is a confirmed instance of a "Reglas del juego" article describing the *other* mode. Added owner-reported, operator-unconfirmed **cash movements the app cannot observe**: the claimable daily €100k, shielding, and clause increases. | Owner |
| 2026-08-07 | Re-verified against the **Spanish** locale (the source language; English is a lossy translation). Established **which game this is** — the official LaLiga-operated app, confirmed via LaLiga's own legal terms naming this help centre's support address — and how to distinguish it from Fantasy MARCA and other games. Squad cap 24 **resolved decisively** against DAZN's 25 by a third operator statement (2026-08-01) describing it as an enforced bidding limit. Same article confirms the app's two add-checks (debt limit, squad cap) are the two the real game enforces. | — |
