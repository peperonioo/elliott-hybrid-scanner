# Elliott Hybrid Scanner — 2026-08-15 16:45 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (2)

### TRX/USDT — largo sobre `impulse_1_2_3` (score 0.520, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-08-13 16:00 UTC (11 velas atrás)
- **Precio en la señal**: 0.3341
- **Zona de interés**: 0.3404 – 0.3428
- **Invalidación de la señal**: 0.3376
- **Invalidación del conteo**: 0.3257
- **Hipótesis alternativas**: `corrective_abc` — el conteo es ambiguo

| factor | score | umbral | activo |
|---|---|---|---|
| fibonacci | 0.000 | 0.60 | — |
| rsi_divergence | 0.000 | 0.60 | — |
| market_structure | 0.950 | 0.60 | ✅ |
| volume_profile | 0.863 | 0.60 | ✅ |
| higher_timeframe_trend | 1.000 | 0.60 | ✅ |

<details><summary>detalle de factores</summary>

- **fibonacci**: precio 0.3341 lejos de todo nivel; el más próximo es extensión 1.618 en 0.3416 (4.77 ATR)
- **rsi_divergence**: un impulso 1-2-3 no tiene todavía dos extremos comparables
- **market_structure**: BOS alcista sobre 0.3335, cierre 0.3363, ruptura hace 1 velas
- **volume_profile**: vol 3/1 = 1.43; la onda 4 aún no existe
- **higher_timeframe_trend**: cierre 0.3363 contra EMA50 0.3287 (fuerza +1.00); señal bullish

> Impulso incompleto: faltarían las ondas 4 y 5. 'Onda 3 nunca la más corta' y el solape de la onda 4 todavía no son aplicables; que la onda 3 supere el final de la 1 sí, porque la onda 3 ya está terminada.

</details>

### LINK/USDT — largo sobre `impulse_1_2_3` (score 0.517, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-08-15 12:00 UTC (0 velas atrás)
- **Precio en la señal**: 9.5120
- **Zona de interés**: 8.5725 – 8.8455
- **Invalidación de la señal**: 8.4550
- **Invalidación del conteo**: 7.8880
- **Hipótesis alternativas**: `corrective_abc` — el conteo es ambiguo

| factor | score | umbral | activo |
|---|---|---|---|
| fibonacci | 0.000 | 0.60 | — |
| rsi_divergence | 0.000 | 0.60 | — |
| market_structure | 1.000 | 0.60 | ✅ |
| volume_profile | 0.777 | 0.60 | ✅ |
| higher_timeframe_trend | 1.000 | 0.60 | ✅ |

<details><summary>detalle de factores</summary>

- **fibonacci**: precio 9.5120 lejos de todo nivel; el más próximo es retroceso 0.618 en 8.7090 (4.41 ATR)
- **rsi_divergence**: un impulso 1-2-3 no tiene todavía dos extremos comparables
- **market_structure**: BOS alcista sobre 8.9160, cierre 8.9700, ruptura hace 0 velas
- **volume_profile**: vol 3/1 = 1.39; la onda 4 aún no existe
- **higher_timeframe_trend**: cierre 8.9700 contra EMA50 8.3402 (fuerza +1.00); señal bullish

> Impulso incompleto: faltarían las ondas 4 y 5. 'Onda 3 nunca la más corta' y el solape de la onda 4 todavía no son aplicables; que la onda 3 supere el final de la 1 sí, porque la onda 3 ya está terminada.

</details>

## Cerca del umbral (10)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| BTC/USDT | `corrective_abc` | 0.348 | rsi_divergence, volume_profile | 64,319.94–64,875.63 | 62,742.47 |
| DOT/USDT | `corrective_abc` | 0.334 | rsi_divergence, volume_profile | 0.7902–0.8058 | 0.7430 |
| DOGE/USDT | `corrective_abc` | 0.298 | fibonacci, volume_profile | 0.0697–0.0707 | 0.0682 |
| SUI/USDT | `corrective_abc` | 0.285 | volume_profile | 0.6809–0.6922 | 0.6643 |
| ETH/USDT | `corrective_abc` | 0.238 | volume_profile | 1,898.44–1,919.30 | 1,853.62 |
| BNB/USDT | `impulse_1_2_3` | 0.237 | higher_timeframe_trend | 638.73–645.94 | 605.50 |
| SOL/USDT | `corrective_abc` | 0.236 | volume_profile | 75.5174–76.5209 | 70.5800 |
| PEPE/USDT | `corrective_abc` | 0.195 | volume_profile | 0.0000–0.0000 | 0.0000 |
| ADA/USDT | `corrective_abc` | 0.174 | — | 0.1650–0.1689 | 0.1578 |
| XRP/USDT | `corrective_abc` | 0.000 | — | 1.0704–1.0832 | 1.0473 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
