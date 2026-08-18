# Elliott Hybrid Scanner — 2026-08-18 01:18 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### TRX/USDT — largo sobre `impulse_1_2_3` (score 0.520, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-08-13 16:00 UTC (6 velas atrás)
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

## Cerca del umbral (11)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| SOL/USDT | `corrective_abc` | 0.430 | fibonacci, volume_profile | 74.2619–75.4513 | 70.5800 |
| BTC/USDT | `corrective_abc` | 0.363 | rsi_divergence, volume_profile | 64,256.77–64,938.81 | 62,742.47 |
| DOT/USDT | `corrective_abc` | 0.334 | rsi_divergence, volume_profile | 0.7907–0.8053 | 0.7430 |
| ETH/USDT | `corrective_abc` | 0.242 | volume_profile | 1,895.87–1,921.87 | 1,853.62 |
| BNB/USDT | `impulse_1_2_3` | 0.237 | higher_timeframe_trend | 638.73–645.94 | 605.50 |
| DOGE/USDT | `corrective_abc` | 0.218 | volume_profile | 0.0696–0.0708 | 0.0682 |
| LINK/USDT | `corrective_abc` | 0.212 | higher_timeframe_trend | 8.2766–8.4677 | 8.0680 |
| PEPE/USDT | `corrective_abc` | 0.201 | volume_profile | 0.0000–0.0000 | 0.0000 |
| ADA/USDT | `corrective_abc` | 0.186 | — | 0.1647–0.1692 | 0.1578 |
| SUI/USDT | `impulse_1_2_3` | 0.177 | volume_profile | 0.7272–0.7399 | 0.7003 |
| XRP/USDT | `corrective_abc` | 0.000 | — | 1.0697–1.0839 | 1.0473 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
