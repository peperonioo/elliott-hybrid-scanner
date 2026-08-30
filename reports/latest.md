# Elliott Hybrid Scanner — 2026-08-30 19:21 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### BTC/USDT — largo sobre `impulse_1_2_3` (score 0.470, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-08-28 16:00 UTC (11 velas atrás)
- **Precio en la señal**: 77,580.03
- **Zona de interés**: 68,923.95 – 70,619.46
- **Invalidación de la señal**: 65,474.46
- **Invalidación del conteo**: 62,275.00
- **Hipótesis alternativas**: `corrective_abc` — el conteo es ambiguo

| factor | score | umbral | activo |
|---|---|---|---|
| fibonacci | 0.000 | 0.60 | — |
| rsi_divergence | 0.000 | 0.60 | — |
| market_structure | 0.600 | 0.60 | ✅ |
| volume_profile | 1.000 | 0.60 | ✅ |
| higher_timeframe_trend | 1.000 | 0.60 | ✅ |

<details><summary>detalle de factores</summary>

- **fibonacci**: precio 77,580.0300 lejos de todo nivel; el más próximo es retroceso 0.618 en 69,771.7067 (6.91 ATR)
- **rsi_divergence**: un impulso 1-2-3 no tiene todavía dos extremos comparables
- **market_structure**: BOS alcista sobre 66,956.1500, cierre 80,249.5800, ruptura hace 8 velas
- **volume_profile**: vol 3/1 = 1.92; la onda 4 aún no existe
- **higher_timeframe_trend**: cierre 80,249.5800 contra EMA50 68,253.6203 (fuerza +1.00); señal bullish

> Impulso incompleto: faltarían las ondas 4 y 5. 'Onda 3 nunca la más corta' y el solape de la onda 4 todavía no son aplicables; que la onda 3 supere el final de la 1 sí, porque la onda 3 ya está terminada.

</details>

## Cerca del umbral (12)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| XRP/USDT | `impulse_1_2_3` | 0.463 | volume_profile, higher_timeframe_trend | 1.3889–1.4305 | 1.3441 |
| SOL/USDT | `impulse_1_2_3` | 0.429 | market_structure, higher_timeframe_trend | 120.32–124.68 | 102.74 |
| ETH/USDT | `impulse_1_2_3` | 0.350 | volume_profile, higher_timeframe_trend | 2,103.61–2,145.62 | 1,925.00 |
| BNB/USDT | `impulse_1_2_3` | 0.350 | volume_profile, higher_timeframe_trend | 643.07–653.25 | 620.55 |
| LINK/USDT | `impulse_1_2_3` | 0.350 | volume_profile, higher_timeframe_trend | 10.3755–10.6695 | 9.7460 |
| PEPE/USDT | `corrective_abc` | 0.338 | volume_profile, higher_timeframe_trend | 0.0000–0.0000 | 0.0000 |
| DOGE/USDT | `impulse_1_2_3` | 0.325 | volume_profile, higher_timeframe_trend | 0.0818–0.0841 | 0.0742 |
| TRX/USDT | `impulse_1_2_3` | 0.311 | volume_profile, higher_timeframe_trend | 0.3404–0.3428 | 0.3376 |
| AVAX/USDT | `impulse_1_2_3` | 0.307 | volume_profile, higher_timeframe_trend | 6.9373–7.1048 | 6.8770 |
| ADA/USDT | `impulse_1_2_3` | 0.289 | volume_profile, higher_timeframe_trend | 0.3091–0.3155 | 0.2117 |
| SUI/USDT | `impulse_1_2_3` | 0.268 | volume_profile | 0.7203–0.7468 | 0.7003 |
| DOT/USDT | `corrective_abc` | 0.140 | — | 0.7588–0.7847 | 0.7230 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
