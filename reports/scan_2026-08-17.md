# Elliott Hybrid Scanner — 2026-08-17 09:04 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### LINK/USDT — largo sobre `impulse_1_2_3` (score 0.517, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-08-15 12:00 UTC (10 velas atrás)
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

## Cerca del umbral (11)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| SOL/USDT | `corrective_abc` | 0.345 | volume_profile | 75.5276–76.5106 | 70.5800 |
| BTC/USDT | `corrective_abc` | 0.341 | rsi_divergence, volume_profile | 64,355.95–64,839.62 | 62,742.47 |
| DOT/USDT | `corrective_abc` | 0.334 | rsi_divergence, volume_profile | 0.7909–0.8051 | 0.7430 |
| DOGE/USDT | `corrective_abc` | 0.305 | fibonacci, volume_profile | 0.0698–0.0707 | 0.0682 |
| ETH/USDT | `corrective_abc` | 0.281 | volume_profile | 1,898.99–1,918.75 | 1,853.62 |
| TRX/USDT | `impulse_1_2_3` | 0.258 | volume_profile, higher_timeframe_trend | 0.3408–0.3424 | 0.3376 |
| BNB/USDT | `impulse_1_2_3` | 0.204 | higher_timeframe_trend | 639.66–645.01 | 605.50 |
| PEPE/USDT | `corrective_abc` | 0.161 | volume_profile | 0.0000–0.0000 | 0.0000 |
| SUI/USDT | `impulse_1_2_3` | 0.150 | volume_profile | 0.7282–0.7389 | 0.7003 |
| ADA/USDT | `corrective_abc` | 0.145 | — | 0.1649–0.1689 | 0.1578 |
| XRP/USDT | `corrective_abc` | 0.000 | — | 1.0709–1.0826 | 1.0473 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
