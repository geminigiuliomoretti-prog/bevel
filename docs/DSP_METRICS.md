# Motore DSP Fisiologico (Livello 4)

Questo documento descrive le formule matematiche e le euristiche implementate nel motore DSP in Dart puro (`app/lib/src/dsp/`) per il calcolo di metriche fisiologiche da record WHOOP 5.0 (V18 e R-R in millisecondi).

---

## 1. Filtro Artefatti R-R (`RrArtifactFilter`)

Gli intervalli R-R grezzi registrati possono contenere artefatti dovuti a movimento, disconnessioni ottiche o battiti ectopici isolati.

### Criteri di accettazione di un intervallo $RR_i$:
1. **Limiti fisiologici assoluti:**
   $$250\,\text{ms} \le RR_i \le 2500\,\text{ms} \quad (24\,\text{bpm} \le \text{HR} \le 240\,\text{bpm})$$
2. **Differenza relativa con il battito valido precedente $RR_{\text{prev}}$:**
   $$\frac{|RR_i - RR_{\text{prev}}|}{RR_{\text{prev}}} < 0.20 \quad (20\%)$$
3. **Differenza assoluta opzionale (configurabile):**
   $$|RR_i - RR_{\text{prev}}| \le \Delta_{\text{max}}$$

I battiti scartati vengono rimossi dalla sequenza. Il battito successivo viene valutato rispetto all'ultimo battito valido accettato.

---

## 2. Heart Rate Variability: RMSSD (`calculateRmssd`)

L'indice RMSSD (Root Mean Square of Successive Differences) quantifica l'attività parasimpatica (tono vagale) a livello cardiaco secondo lo standard internazionale Task Force 1996.

### Formula:
$$\text{RMSSD} = \sqrt{\frac{1}{N - 1} \sum_{i=1}^{N-1} (RR_i - RR_{i-1})^2}$$

Dove:
- $N$ è il numero di intervalli R-R filtrati ($N \ge 2$).
- $RR_i - RR_{i-1}$ rappresenta la differenza tra due intervalli consecutivi in millisecondi.
- Il risultato finale è espresso in millisecondi ($\text{ms}$).
- Se $N < 2$, la funzione restituisce `null` poiché non è possibile calcolare differenze successive.

---

## 3. Resting Heart Rate: RHR (`calculateRhr`)

La frequenza cardiaca a riposo (RHR) viene stimata analizzando i record notturni a 1 Hz (`V18Record.hrPrimary`).

### Algoritmo:
1. **Filtro di validità:** Vengono considerati solo i campioni con $0 < \text{HR} \le 240$ (escludendo campioni con $\text{HR} = 0$, indicativi di off-wrist).
2. **Finestra mobile (Sliding Window):** Viene calcolata la media cardiaca su una finestra scorrevole di 5 minuti ($W = 300\,\text{secondi}$ a 1 Hz):
   $$\overline{\text{HR}}_k = \frac{1}{W} \sum_{j=k}^{k + W - 1} \text{HR}_j$$
3. **Minimo notturno:**
   $$\text{RHR} = \text{round}\left( \min_k \overline{\text{HR}}_k \right)$$
4. Se il periodo disponibile contiene meno di 300 campioni validi, viene calcolata la media complessiva arrotondata all'intero più vicino.
