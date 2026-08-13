# Elliott Hybrid Scanner — 2026-08-13 21:07 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### TRX/USDT — largo sobre `impulse_1_2_3` (score 0.670, 4/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-08-13 16:00 UTC (0 velas atrás)
- **Precio en la señal**: 0.3341
- **Zona de interés**: 0.3334 – 0.3357
- **Invalidación de la señal**: 0.3376
- **Invalidación del conteo**: 0.3257
- **Hipótesis alternativas**: `corrective_abc` — el conteo es ambiguo

| factor | score | umbral | activo |
|---|---|---|---|
| fibonacci | 0.601 | 0.60 | ✅ |
| rsi_divergence | 0.000 | 0.60 | — |
| market_structure | 0.950 | 0.60 | ✅ |
| volume_profile | 0.863 | 0.60 | ✅ |
| higher_timeframe_trend | 1.000 | 0.60 | ✅ |

<details><summary>detalle de factores</summary>

- **fibonacci**: precio 0.3341 sobre retroceso 0.786 en 0.3346
- **rsi_divergence**: un impulso 1-2-3 no tiene todavía dos extremos comparables
- **market_structure**: BOS alcista sobre 0.3335, cierre 0.3363, ruptura hace 1 velas
- **volume_profile**: vol 3/1 = 1.43; la onda 4 aún no existe
- **higher_timeframe_trend**: cierre 0.3363 contra EMA50 0.3287 (fuerza +1.00); señal bullish

> Impulso incompleto: faltarían las ondas 4 y 5. Las reglas de la onda 3 y del solape de la onda 4 todavía no son aplicables.

</details>

## Cerca del umbral (10)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| SOL/USDT | `corrective_abc` | 0.417 | fibonacci, volume_profile | 75.3612–76.6770 | 70.5800 |
| TRX/USDT | `impulse_1_2_3` | 0.397 | market_structure, higher_timeframe_trend | 0.3292–0.3313 | 0.3312 |
| SUI/USDT | `corrective_abc` | 0.388 | fibonacci, volume_profile | 0.6796–0.6935 | 0.6643 |
| ETH/USDT | `corrective_abc` | 0.363 | volume_profile | 1,895.62–1,922.12 | 1,853.62 |
| BTC/USDT | `corrective_abc` | 0.361 | rsi_divergence, volume_profile | 64,237.40–64,958.18 | 62,742.47 |
| DOGE/USDT | `corrective_abc` | 0.335 | fibonacci, volume_profile | 0.0696–0.0709 | 0.0682 |
| DOT/USDT | `corrective_abc` | 0.334 | rsi_divergence, volume_profile | 0.7905–0.8055 | 0.7430 |
| BNB/USDT | `impulse_1_2_3` | 0.320 | volume_profile, higher_timeframe_trend | 613.21–620.78 | 577.20 |
| ADA/USDT | `corrective_abc` | 0.186 | — | 0.1645–0.1694 | 0.1578 |
| LINK/USDT | `corrective_abc` | 0.180 | higher_timeframe_trend | 8.2757–8.4687 | 8.0680 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
