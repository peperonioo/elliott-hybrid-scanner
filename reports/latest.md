# Elliott Hybrid Scanner — 2026-11-05 22:06 UTC

> Informe generado automáticamente. **No es asesoramiento financiero y el
> sistema no ejecuta órdenes**: las señales están pensadas para validarse
> a mano (por ejemplo en TradingView) antes de decidir nada.

Universo: BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK, DOT, PEPE, DOGE, SUI, TRX | timeframe de estructura: 4h | mínimo de factores: 3

## Señales activas (1)

### BTC/USDT — largo sobre `corrective_abc` (score 0.469, 3/5 factores)

- **Timeframe**: 4h, señal confirmada el 2026-11-04 12:00 UTC (7 velas atrás)
- **Precio en la señal**: 80,296.01
- **Zona de interés**: 79,747.05 – 81,293.87
- **Invalidación de la señal**: 75,736.38
- **Hipótesis alternativas**: `impulse_1_2_3` — el conteo es ambiguo

| factor | score | umbral | activo |
|---|---|---|---|
| fibonacci | 0.710 | 0.60 | ✅ |
| rsi_divergence | 0.692 | 0.60 | ✅ |
| market_structure | 0.000 | 0.60 | — |
| volume_profile | 0.809 | 0.60 | ✅ |
| higher_timeframe_trend | 0.156 | 0.60 | — |

<details><summary>detalle de factores</summary>

- **fibonacci**: precio 80,296.0100 sobre retroceso 0.786 en 80,520.4633
- **rsi_divergence**: divergencia alcista: precio 79,220.7400→75,736.3800, RSI 29.0→35.9
- **market_structure**: sin ruptura a favor de bullish: cierre 77,453.8600 contra referencia 84,898.0000
- **volume_profile**: vol B/A = 0.76; en un zigzag la B se seca
- **higher_timeframe_trend**: cierre 77,453.8600 contra EMA50 80,133.5019 (fuerza -0.69); señal bullish

> Tres tramos no permiten distinguir una corrección completa de un impulso en curso. Ambas lecturas se devuelven a propósito.

</details>

## Cerca del umbral (12)

La mejor estructura alcista vigente de cada par, re-evaluada al precio actual. NO son señales (les faltan factores): son los niveles a vigilar.

| par | hipótesis | score | factores activos | zona de compra | stop |
|---|---|---|---|---|---|
| SUI/USDT | `corrective_abc` | 0.506 | fibonacci, rsi_divergence | 0.8981–0.9270 | 0.8277 |
| LINK/USDT | `corrective_abc` | 0.330 | fibonacci, volume_profile | 11.4713–11.8846 | 10.6310 |
| PEPE/USDT | `impulse_1_2_3` | 0.322 | volume_profile, higher_timeframe_trend | 0.0000–0.0000 | 0.0000 |
| ETH/USDT | `impulse_1_2_3` | 0.258 | volume_profile | 2,552.70–2,623.62 | 2,317.84 |
| TRX/USDT | `corrective_abc` | 0.257 | volume_profile | 0.3281–0.3320 | 0.3274 |
| ADA/USDT | `corrective_abc` | 0.256 | volume_profile | 0.2088–0.2151 | 0.1820 |
| XRP/USDT | `impulse_1_2_3` | 0.222 | volume_profile | 1.3844–1.4212 | 1.2914 |
| SOL/USDT | `corrective_abc` | 0.198 | — | 96.7957–100.22 | 89.8600 |
| AVAX/USDT | `impulse` | 0.194 | fibonacci | 8.7399–9.0450 | 8.2770 |
| DOGE/USDT | `corrective_abc` | 0.184 | volume_profile | 0.0783–0.0808 | 0.0774 |
| DOT/USDT | `corrective_abc` | 0.173 | rsi_divergence | 1.0554–1.0954 | 0.8690 |
| BNB/USDT | `corrective_abc` | 0.083 | — | 730.01–746.16 | 718.00 |

---
*Backtest de referencia: esperanza +0,58%/op en desarrollo (p=0,035 contra azar) y +0,66%/op en holdout con solo 20 operaciones — prometedor, no probado. Ver README.*
