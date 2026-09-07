import React from 'react';

const BRAND_LOGO_SRC = "https://lh3.googleusercontent.com/aida/AEtjO1WsvG4PmtCG5os6CRAflm_m7FddHjQ1303ktfydHJYjv73FM4gZdW8u-WsJuxbsBABuo5yixcrlsh4usHyJ1WM1hKOJ6Zb9GkurAKXxLYdnXVVhjoRkgWmx8A9C6MGG4mS3TN3aahW9_WiX8r03km6-YLg3AMyJ1gU0k-Xbi8sKH6RceS4hSiPgJN6baSnx3yGLjB7_Mxx9cDA8TAO1ltc5C60hM9RUr_z2u-6KCczeC4ccZYNNsweV_g";

export default function BrandLogo({ className = "h-9 w-auto object-contain", alt = "Explainable Rare-Disease Diagnostic Assistant Brand Emblem" }) {
  return (
    <img 
      src={BRAND_LOGO_SRC} 
      alt={alt} 
      className={className} 
    />
  );
}
