# Elliott Hybrid Scanner — 2026-08-28 22:27 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### BTC/USDT — largo sobre `impulse_1_2_3` (score 0.470, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-08-28 16:00 UTC (0 velas atrás)
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
| SUI/USDT | `impulse_1_2_3` | 0.512 | fibonacci, volume_profile, higher_timeframe_trend | 0.7138–0.7533 | 0.7003 |
| TRX/USDT | `impulse_1_2_3` | 0.485 | fibonacci, volume_profile, higher_timeframe_trend | 0.3401–0.3431 | 0.3376 |
| SOL/USDT | `impulse_1_2_3` | 0.429 | market_structure, higher_timeframe_trend | 120.32–124.68 | 102.74 |
| XRP/USDT | `corrective_abc` | 0.378 | volume_profile, higher_timeframe_trend | 1.0374–1.1034 | 0.9862 |
| DOGE/USDT | `impulse_1_2_3` | 0.356 | volume_profile, higher_timeframe_trend | 0.0812–0.0847 | 0.0742 |
| ETH/USDT | `impulse_1_2_3` | 0.350 | volume_profile, higher_timeframe_trend | 2,091.00–2,158.24 | 1,925.00 |
| BNB/USDT | `impulse_1_2_3` | 0.350 | volume_profile, higher_timeframe_trend | 640.75–655.58 | 620.55 |
| LINK/USDT | `impulse_1_2_3` | 0.350 | volume_profile, higher_timeframe_trend | 10.3122–10.7328 | 9.7460 |
| PEPE/USDT | `corrective_abc` | 0.350 | volume_profile, higher_timeframe_trend | 0.0000–0.0000 | 0.0000 |
| AVAX/USDT | `impulse_1_2_3` | 0.333 | volume_profile, higher_timeframe_trend | 6.9016–7.1405 | 6.8770 |
| ADA/USDT | `impulse_1_2_3` | 0.333 | volume_profile, higher_timeframe_trend | 0.3075–0.3171 | 0.2117 |
| DOT/USDT | `corrective_abc` | 0.176 | higher_timeframe_trend | 0.7546–0.7889 | 0.7230 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
