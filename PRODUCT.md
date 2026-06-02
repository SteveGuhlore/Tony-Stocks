# Product

## Register

product

## Users

Today: Stephen, solo operator and author of the trading bot. He reviews the bot's scans, candidate snapshots, active research positions, and end-of-day outcomes during and after US market hours. He is technical, holds the full system in his head, and reads code-level detail as comfortably as the UI.

Soon: a wider audience of reviewers who did not build the bot. They will read the same screens to judge whether the bot's reasoning held up. They will not have the database schema in their head. They need every screen to explain itself without leaning on tribal knowledge.

The dashboard is read-only research. No one places trades from it. No one is meant to feel an impulse to act.

## Product Purpose

A window into a research-only trading bot. The bot scans roughly 350 symbols, scores setups, tracks candidate snapshots, and records what actually happened to each one. The dashboard shows the operator what the bot is currently watching, what it thinks, and how its past predictions have played out, with the data lineage intact at every step.

Success looks like: a reviewer who has never opened the codebase can sit down at the dashboard, understand what the bot is watching today, see which predictions have already been resolved, and form a judgment about the bot's research quality, without ever feeling pushed toward a trade.

## Brand Personality

Analytical, restrained, contemporary. Three words: **traceable, calm, dense.** The dashboard speaks in the voice of a careful research analyst writing for a peer, not a broker pitching a position. It does not celebrate wins, does not hide losses, and does not use urgency or color theatrics to manufacture engagement.

When live alerts fire during market hours, the interface stays composed. Sound and motion are functional, never decorative.

## Anti-references

- **Not Robinhood / consumer-broker UX.** No gamification, no oversized BUY/SELL affordances, no confetti, no streaks, no urgency-bait copy.
- **Not generic SaaS-cream (Linear / Vercel clones).** No pastel cards, no marketing-style hero metric panels, no decorative gradients, no "AI is here to help" tone.
- **Not nostalgia-LARP Bloomberg.** No skeuomorphic 1990s terminal cosplay, no orange-on-pure-black, no all-caps everywhere, no decorative function-key strips. Terminal density without the costume.
- **Not a TradingView clone.** No social feed, no copy-trade affordances, no 20-indicator chart wall as the front door.

## Design Principles

1. **Every number is traceable.** A metric on screen must point back to a row, a snapshot, or a stored event. If a number cannot be sourced, it does not appear. Reviewers must be able to ask "where did this come from" and the UI must answer.
2. **The unknown is a first-class state.** `insufficient_future_data`, `pending`, `still_open`, and `missing_real_data` are explicit, labeled, and visible. Hiding pending or stale rows to look more confident is forbidden.
3. **Density over decoration.** Information-per-pixel is a real budget. Dense tables, mono numerals, compact rows. Whitespace earns its place by improving scanning, not by aestheticizing the page.
4. **Calm during market hours.** Live updates, alerts, and toasts use the minimum motion and sound needed to register. No bouncing, no flashing, no red-screen panic states. Severity is communicated through color and position, not intensity.
5. **Research voice, never broker voice.** Copy describes what the bot observed and what happened next. It never recommends, congratulates, or warns the reader to act. "Target hit" is a fact, not a celebration.

## Accessibility & Inclusion

Target WCAG 2.2 AA across every product surface. Specific requirements:

- **Contrast.** All status colors (green, red, amber, cyan) and secondary text must meet 4.5:1 against the surface they sit on, including the dense table rows and the elevated card surfaces. The `--text-secondary: #666666` and `--text-muted: #2a2a2a` values against `--bg-base: #050505` are the highest-risk pairings and must be audited.
- **Color is never the only channel.** P/L sign, alert severity, market open/closed state, and pick lifecycle must each carry a non-color cue (icon, label, position, or weight). The reviewer audience may include color-blind users.
- **Reduced motion.** Honor `prefers-reduced-motion`. Live alert toasts, market clock animation, and any future chart transitions must collapse to instant state changes.
- **Keyboard.** All overlay drawers (`SymbolDrawer`, `NotificationDrawer`) must be reachable, dismissible, and focus-trapped from keyboard alone. Symbol clicks in dense tables must have keyboard equivalents.
- **Density vs touch.** Desktop density is the target, but live-alert affordances and primary navigation must meet 44x44 touch targets so the dashboard remains usable on a tablet during market hours.
