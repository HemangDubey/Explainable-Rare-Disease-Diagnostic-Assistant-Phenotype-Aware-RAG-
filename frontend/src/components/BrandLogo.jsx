import React from 'react';

export default function BrandLogo({ className = "h-9 w-auto object-contain", alt = "Explainable Rare-Disease Diagnostic Assistant Brand Emblem" }) {
  return (
    <img 
      src="/logo.jpg" 
      alt={alt} 
      className={className} 
    />
  );
}


