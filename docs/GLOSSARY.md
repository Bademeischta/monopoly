# GLOSSARY – Begriffe (§0.4)

| Begriff | Bedeutung |
|---|---|
| MCR (Minimal Complete Result) | 2-Spieler-Agent, der Z3 (§8.4) auf TEST erfüllt. |
| Genuine Entscheidung | Entscheidungspunkt eines Lernsitzes mit mindestens 2 legalen Aktionen. |
| Forced Entscheidung | Entscheidungspunkt mit genau 1 legalen Aktion; bei Auto-Skip automatisch ausgeführt. |
| Makroschritt | Von einer genuinen Entscheidung eines Lernsitzes bis zu seiner nächsten genuinen Entscheidung oder seinem Episodenende. Dauer k = 1 + Anzahl automatisch ausgeführter forced Entscheidungen dieses Sitzes. |
| Lernsitz | Sitz, dessen Entscheidungen die aktuell trainierte Policy trifft und deren Transitionen als Trainingsdaten gesammelt werden. |
| Single-Agent RL (MCR) | Genau ein Lernsitz; alle anderen Sitze sind Umgebung. |
| Population Best Response (Self-Play 2P) | Ein Lernsitz, Gegner aus Snapshot-Pool und Baselines. |
| Shared-Policy-MARL (4P) | Mehrere Lernsitze pro Spiel mit derselben Policy (Parameter Sharing), individueller Reward je Sitz; alle Lernsitze liefern Trainingsdaten. Zentraler Critic und Population-Based Training sind Erweiterungen. |
| Delegation | Technische Policy (`delegation_v1`) für delegierte Entscheidungsarten eines Lernsitzes (Handel, Auktionen, Schulden; in N4 auch Kauf). |
| Benchmark-Policy | Vollständige Spielstrategie eines Referenzgegners (`random_legal`, `greedy_v1`, `roi_markov_v1`, `strong_a_v1`, `strong_b_v1`). Delegation und Benchmark-Policies teilen Bewertungsprimitive, nie die Gesamtstrategie. |
| TRAIN, SELECT, TEST, SMOKE | Disjunkte Seed-Mengen (§7.4, §8.1): Training, Auswahl/Tuning, einmalige finale Auswertung, Smoke-Modus. |
| Duplicate | Jeder Seed wird in allen Sitzbelegungen (2P) bzw. zyklischen Rotationen (4P) gespielt. |
| Safety-Horizon | Rundenzahl, ab der ein Spiel als abgeschnitten (truncated) gilt; kein Regelbestandteil. |
| PBRS | Potential-Based Reward Shaping, F = γ^k Φ(s') − Φ(s) mit Φ = β × (Equity-Anteil − 1/N_aktiv). |
| SMDP | Semi-Markov-Entscheidungsprozess: Diskontierung mit γ^k je Makroschritt. |
| Knappheitsauktion | Versteigerung knapper Häuser/Hotels nach P-19, wenn die Nachfrage den Bankbestand übersteigt. |
| Fenster | Managementphase (Pre-Roll, Post-Move, Out-of-Turn), in der gebaut, verkauft, belastet, abgelöst und gehandelt werden kann. |
| Equity (kanonisch) | Bargeld + Druckpreis unbelasteter bzw. halber Druckpreis belasteter Rechte + Baukosten der Gebäude (`engine/equity.py`). |
| Champion-Gate | Prüfung, ob ein Self-Play-Snapshot den aktuellen Champion auf zwei SELECT-Blöcken schlägt (§7.8). |
| PFSP | Prioritized Fictitious Self-Play: Gegnergewicht (1 − p)² mit p = Siegwahrscheinlichkeit gegen diesen Gegner. |
| Winner Sensitivity (WS) | Größte Totalvariationsdistanz der Siegerverteilung zwischen gewählter und alternativer Aktion eines aussichtslosen Spielers (§8.8). |
| Gate | Meilenstein mit prüfbaren Kriterien (G0–G8, `docs/ROADMAP.md`). |
| Smoke | Kleinformat-Durchlauf zum Funktionsnachweis, „SMOKE – keine Aussagekraft“. |
