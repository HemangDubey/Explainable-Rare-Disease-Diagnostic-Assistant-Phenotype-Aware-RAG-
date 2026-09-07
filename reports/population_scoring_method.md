# Population Prior Scoring Method

## Scientific Rationale & Interpretation Rule
Population frequency alone is **NOT** a direct measure of disease causality or probability. In rare disease diagnostics, population allele frequency serves as a population-aware prior signal to calibrate candidate disease prioritization across specific ancestry backgrounds (e.g. Indian population genomes).

## Mathematical Transformation
For a candidate disease $D$ with associated genes $G = \{g_1, g_2, \dots, g_m\}$:

1. **Missing Data Neutral Baseline**:
   If no variant frequency data is available for any associated gene ($G \cap \text{IndiGen} = \emptyset$), the engine sets:
   $$\text{status} = \text{'unavailable' / 'not\_found'}$$
   $$\text{indian\_population\_signal} = 0.50$$
   $$\text{global\_population\_signal} = 0.50$$
   *This ensures that missing population records never penalize or unfairly boost a candidate disease.*

2. **Population Enrichment Signal**:
   When variant frequencies are present, average IndiGen frequency $\text{AF}_{\text{IND}}$ and gnomAD global frequency $\text{AF}_{\text{GLOBAL}}$ are evaluated:
   $$\text{raw\_enrichment} = \log_{10}\left(1 + \frac{\text{AF}_{\text{IND}} + 10^{-7}}{\text{AF}_{\text{GLOBAL}} + 10^{-7}}\right)$$

3. **Bounded Sigmoid Normalization**:
   To ensure stability and interpretability in $[0.0, 1.0]$:
   $$\text{indian\_population\_signal} = \frac{1}{1 + e^{-2.0 \cdot (\text{raw\_enrichment} - 0.30)}}$$
   - Neutral baseline / equal frequencies: $\approx 0.50$
   - High relative population prevalence: $> 0.50$ to $1.0$
   - Depleted relative population prevalence: $< 0.50$
