# Tutorial — cómo usar el Elliott Hybrid Scanner

Guía de uso para el día a día. Para las decisiones técnicas y los resultados
del backtest, ver el [README](README.md).

---

## 1. Qué es (y qué no es)

**Es** un scanner que cada día revisa 9 criptomonedas (BTC, ETH, SOL, BNB,
XRP, ADA, AVAX, LINK, DOT) buscando estructuras de ondas de Elliott apoyadas
por confluencia técnica, y publica un informe con lo que encuentra.

**No es** un bot de trading. No ejecuta órdenes, no se conecta a tu cuenta de
ningún exchange, no tiene API keys. Solo lee precios públicos y escribe un
informe. La decisión de operar —o no— es siempre tuya y manual.

**Estado de validación**: el backtest con periodo reservado dio resultados
prometedores (+0,58% por operación en desarrollo, p=0,035 contra azar;
positivo también en el holdout), pero el holdout tenía solo 20 operaciones.
La prueba de verdad es el *forward test*: dejar que el sistema publique
señales durante meses y comprobar qué pasa. Este tutorial explica cómo
llevar ese registro.

---

## 2. El informe diario: dónde y cuándo

Cada día, poco después de la medianoche UTC (~01:20–02:20 hora española), el
workflow de GitHub descarga las velas nuevas, escanea y commitea el informe.

**Para verlo**, la forma cómoda es la web (guárdala en favoritos del móvil):

> **https://peperonioo.github.io/elliott-hybrid-scanner/**

Muestra las señales de compra activas, el radar con los niveles de cada par
(zona de compra y stop) y la guía de lectura, y se regenera cada noche.

La versión en texto vive en el repo: carpeta `reports/` → `latest.md`. Cada
día queda además archivado como `scan_<fecha>.md`, así que el historial
completo se conserva — ese historial es el registro del forward test.

También puedes generarlo a mano en tu Mac en cualquier momento:

```bash
cd ~/Documents/CLAUDE/Notion/elliott-hybrid-scanner
.venv/bin/python scripts/daily_report.py
open reports/latest.md
```

**La mayoría de los días dirá "Señales activas (0)".** Es normal y es buena
señal: el sistema emite unas 4 señales al mes en todo el universo. Un scanner
que dispara cada día no está filtrando nada.

---

## 3. Cómo leer una señal

Cuando haya una, tendrá esta pinta:

> ### BTC/USDT — largo sobre `corrective_abc` (score 0.712, 4/5 factores)
> - **Timeframe**: 4h, señal confirmada el 2026-08-10 08:00 UTC (2 velas atrás)
> - **Precio en la señal**: 61,240.00
> - **Zona de interés**: 59,800.00 – 60,900.00
> - **Invalidación de la señal**: 58,100.00
> - **Hipótesis alternativas**: `impulse_1_2_3` — el conteo es ambiguo

Campo a campo:

| Campo | Qué significa |
|---|---|
| **largo** | El sistema solo emite largos (compras). Los cortos se eliminaron: perdían dinero de forma consistente en el backtest. |
| **`corrective_abc`** | La estructura detectada. `corrective_abc` = una corrección A-B-C que parece completa (se espera que se reanude la subida). `impulse` = cinco ondas completas. `impulse_1_2_3` = impulso a medias, se espera onda 4 y 5. |
| **score, 4/5 factores** | Cuántos de los 5 factores de confluencia (Fibonacci, divergencia RSI, estructura de mercado, volumen, tendencia diaria) superan su umbral. Mínimo 3 para que la señal exista. |
| **Zona de interés** | Banda de precio alrededor del nivel de Fibonacci relevante. Si el precio vuelve ahí, es la zona teóricamente favorable. |
| **Invalidación de la señal** | El nivel que, si el precio lo pierde, mata la tesis. Es donde iría el stop si operaras. |
| **Hipótesis alternativas** | Elliott es ambiguo a veces y el sistema no lo disimula: si la estructura admite dos lecturas, te da las dos. |

Debajo de cada señal hay una tabla con el score de cada factor y un
desplegable con el detalle en texto de por qué puntúa lo que puntúa.

La sección **"Cerca del umbral"** lista pares con 2 factores activos — a uno
de disparar. No son señales; son lo que conviene vigilar.

---

## 4. Validar una señal en TradingView (5 minutos)

1. Abre TradingView → busca el par con sufijo Binance (ej. `BINANCE:BTCUSDT`)
   → gráfico de **4 horas**. Importante que sea Binance: es la fuente de
   datos del scanner, otros exchanges difieren un poco.
2. Localiza la estructura que el informe describe. Para un `corrective_abc`
   largo: una subida previa, luego una corrección en tres tramos (baja-sube-
   baja) que termina cerca de la zona de interés.
3. Pregúntate: **¿yo habría contado esto igual?** El detalle de factores te
   dice exactamente qué vio el sistema (en qué nivel de Fibonacci está el
   precio, entre qué valores divergió el RSI…). Si el conteo te parece
   forzado, anótalo — esa opinión también es dato.
4. Marca en el gráfico la zona de interés y la invalidación con dos líneas
   horizontales. Así ves de un vistazo cómo evoluciona los días siguientes.

---

## 5. El registro del forward test (lo más importante)

Durante los próximos 3–6 meses, **no operes con dinero: anota**. Una hoja de
cálculo con una fila por señal:

| fecha | par | precio señal | invalidación | objetivo (2R) | resultado | notas |
|---|---|---|---|---|---|---|
| 2026-08-10 | BTC | 61.240 | 58.100 | 67.520 | ? | conteo dudoso, B muy profunda |

- **Objetivo (2R)**: entrada + 2 × (entrada − invalidación). Es la regla que
  usó el backtest, así el registro es comparable.
- **Resultado**: qué tocó primero — objetivo (+2R), invalidación (−1R), o
  dónde estaba a las 30 velas (5 días) si no tocó ninguno.
- El historial de `reports/` en GitHub es tu comprobante: las señales quedan
  commiteadas con fecha, imposibles de reescribir a posteriori.

**Cuándo sacar conclusiones**: con ~30–40 señales (unos 8–10 meses). Si la
esperanza sigue positiva, tienes un sistema validado en datos que nadie pudo
mirar. Si no, has ahorrado el dinero que habrías perdido.

---

## 6. Comandos útiles en local

Todo se ejecuta desde la carpeta del proyecto:

```bash
cd ~/Documents/CLAUDE/Notion/elliott-hybrid-scanner
```

| Quiero… | Comando |
|---|---|
| Actualizar datos y generar el informe | `.venv/bin/python scripts/daily_report.py` |
| Solo el informe, sin descargar | `.venv/bin/python scripts/daily_report.py --no-fetch` |
| Ver el gráfico de swings de un par | `.venv/bin/python scripts/plot_swings.py --bases BTC` |
| Ver qué está evaluando ahora mismo y por qué | `.venv/bin/python scripts/scan.py --all --explain` |
| Re-ejecutar el backtest completo | `.venv/bin/python scripts/backtest.py` |
| Pasar los tests | `.venv/bin/python -m pytest` |

Los gráficos se escriben en `plots/` y los informes en `reports/`.

---

## 7. Qué se puede tocar y qué no

Todo lo ajustable vive en un único fichero: **`config.yaml`**. Cosas seguras
de cambiar:

- **`universe.bases`** — añadir o quitar monedas (deben cotizar en Binance
  contra USDT).
- **`report`** — cuántas entradas muestra el informe.

Cosas que **no** conviene tocar sin repensar la validación:

- **`swings.atr_threshold` (3.0)** — lo calibraste tú a ojo; cambiarlo cambia
  todos los conteos.
- **`confluence.*`** y **`backtest.filters`** — son la configuración que se
  validó contra el holdout. Retocarlas porque una semana fue mala invalida
  todo el trabajo estadístico. La regla: los parámetros se cambian por una
  razón previa, nunca por un resultado reciente.
- **El periodo de holdout ya está gastado.** No sirve re-ejecutar el backtest
  una y otra vez buscando un número mejor: cada pasada extra convierte el
  "out-of-sample" en "in-sample" un poco más.

---

## 8. Mantenimiento

- **El workflow falla** (recibirás email de GitHub): casi siempre es un fallo
  transitorio del exchange. Pestaña *Actions* → *daily-scan* → *Re-run*. Los
  reintentos con backoff ya cubren la mayoría de los casos.
- **Kraken/Binance cambian algo**: `pip install -U ccxt` en el venv y correr
  los tests suele bastar.
- **Añadir Telegram/Notion al informe**: está previsto — el informe es un
  Markdown que se puede reenviar a cualquier sitio. Las credenciales irían en
  GitHub Secrets, nunca en el código.

---

*Nada de esto es asesoramiento financiero. El sistema genera hipótesis para
que las evalúe un humano; los resultados pasados, incluso los del holdout, no
garantizan nada sobre los futuros.*
