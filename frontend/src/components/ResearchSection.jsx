import React from 'react';

export default function ResearchSection() {
  return (
    <section className="w-full py-space-3xl" id="research">
      <div className="max-w-container-max mx-auto px-gutter-mobile lg:px-gutter-desktop">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-2xl items-center">
          <div className="lg:col-span-6 flex flex-col">
            <span className="font-label-sm text-label-sm text-secondary font-semibold uppercase tracking-wider block mb-space-2xs">
              Demographic Genome Variation
            </span>
            <h2 className="font-headline-lg text-headline-lg text-primary tracking-tight mb-space-md">
              Population-aware rare-disease prioritization.
            </h2>
            <p className="font-body-lg text-body-lg text-on-surface-variant mb-space-md">
              Global genomic frequency data may not fully represent the rich genetic variation observed across Indian populations. The platform introduces population-aware priors as an additional ranking signal alongside phenotype and evidence matching.
            </p>
            <p className="font-body-md text-body-md text-on-surface-variant mb-space-lg">
              By harmonizing allele frequency data from the IndiGen initiative and regional cohort archives, our Bayesian re-weighting layer suppresses false-positive pathogenic classifications caused by benign Indian founder mutations.
            </p>
            <div className="flex flex-col gap-space-sm">
              <div className="flex items-start gap-space-sm">
                <div className="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-secondary shrink-0">
                  <span className="material-symbols-outlined text-[18px]">strikethrough_s</span>
                </div>
                <div>
                  <span className="block font-title-md text-title-md text-primary">IndiGen &amp; GenomeAsia Integration</span>
                  <span className="font-body-sm text-body-sm text-on-surface-variant">Calibrated against whole-genome sequences spanning hundreds of distinct ethno-linguistic groups.</span>
                </div>
              </div>
              <div className="flex items-start gap-space-sm">
                <div className="w-8 h-8 rounded-full bg-surface-container flex items-center justify-center text-secondary shrink-0">
                  <span className="material-symbols-outlined text-[18px]">calculate</span>
                </div>
                <div>
                  <span className="block font-title-md text-title-md text-primary">Calibrated Bayesian Re-Weighting</span>
                  <span className="font-body-sm text-body-sm text-on-surface-variant">Prior shifts occur smoothly without eclipsing direct phenotypic and functional validation.</span>
                </div>
              </div>
            </div>
          </div>

          {/* Right Side: Frequency Matrix Comparison Graphic */}
          <div className="lg:col-span-6">
            <div className="bg-surface-container-lowest p-space-xl rounded-2xl shadow-[0_4px_24px_rgba(9,30,58,0.04)]">
              <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider font-semibold block mb-space-md">
                Allele Frequency Prior Shift Comparison
              </span>
              <div className="flex flex-col gap-space-sm">
                {/* Row 1 */}
                <div className="p-space-md rounded-xl bg-surface-container-low flex flex-col sm:flex-row items-start sm:items-center justify-between gap-space-sm">
                  <div>
                    <span className="font-title-md text-title-md text-primary">Variant c.1268G&gt;A (SLC25A20)</span>
                    <span className="block font-body-sm text-body-sm text-on-surface-variant">Carnitine-acylcarnitine translocase deficiency</span>
                  </div>
                  <div className="flex items-center gap-space-md">
                    <div className="text-right">
                      <span className="block font-code-metric text-label-sm text-on-surface-variant">gnomAD Global</span>
                      <span className="font-code-metric text-body-md text-primary">0.00004</span>
                    </div>
                    <span className="material-symbols-outlined text-secondary text-[20px]">trending_up</span>
                    <div className="text-right bg-secondary-fixed/40 px-space-xs py-space-2xs rounded">
                      <span className="block font-code-metric text-label-sm text-on-secondary-fixed-variant font-bold">IndiGen Prior</span>
                      <span className="font-code-metric text-body-md text-secondary font-bold">0.00310</span>
                    </div>
                  </div>
                </div>

                {/* Row 2 */}
                <div className="p-space-md rounded-xl bg-surface-container-low flex flex-col sm:flex-row items-start sm:items-center justify-between gap-space-sm">
                  <div>
                    <span className="font-title-md text-title-md text-primary">Variant c.845G&gt;A (HFE)</span>
                    <span className="block font-body-sm text-body-sm text-on-surface-variant">Hereditary Hemochromatosis</span>
                  </div>
                  <div className="flex items-center gap-space-md">
                    <div className="text-right">
                      <span className="block font-code-metric text-label-sm text-on-surface-variant">gnomAD Global</span>
                      <span className="font-code-metric text-body-md text-primary">0.06200</span>
                    </div>
                    <span className="material-symbols-outlined text-on-surface-variant text-[20px]">trending_down</span>
                    <div className="text-right bg-surface-container px-space-xs py-space-2xs rounded">
                      <span className="block font-code-metric text-label-sm text-on-surface-variant font-bold">IndiGen Prior</span>
                      <span className="font-code-metric text-body-md text-on-surface font-bold">0.00120</span>
                    </div>
                  </div>
                </div>

                {/* Row 3 */}
                <div className="p-space-md rounded-xl bg-surface-container-low flex flex-col sm:flex-row items-start sm:items-center justify-between gap-space-sm">
                  <div>
                    <span className="font-title-md text-title-md text-primary">Variant c.1444C&gt;T (GJB2)</span>
                    <span className="block font-body-sm text-body-sm text-on-surface-variant">Autosomal Recessive Sensorineural Deafness</span>
                  </div>
                  <div className="flex items-center gap-space-md">
                    <div className="text-right">
                      <span className="block font-code-metric text-label-sm text-on-surface-variant">gnomAD Global</span>
                      <span className="font-code-metric text-body-md text-primary">0.00012</span>
                    </div>
                    <span className="material-symbols-outlined text-secondary text-[20px]">trending_up</span>
                    <div className="text-right bg-secondary-fixed/40 px-space-xs py-space-2xs rounded">
                      <span className="block font-code-metric text-label-sm text-on-secondary-fixed-variant font-bold">IndiGen Prior</span>
                      <span className="font-code-metric text-body-md text-secondary font-bold">0.01420</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-space-md pt-space-sm border-t-0 flex items-center justify-between text-on-surface-variant font-label-sm text-label-sm">
                <span>Cohort reference: IndiGen 1,029 WGS samples &amp; 1000G South Asian</span>
                <span className="font-code-metric font-semibold text-secondary">MAF Threshold: 0.01</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
